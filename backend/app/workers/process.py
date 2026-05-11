"""Worker RQ: process_article — normalize + classify + sync Manticore.

Pipeline per singolo articolo (dopo che fetch ha popolato `articles`):
1. carica Article + raw_meta_lite (title/description/content_html dal feed)
2. normalize -> content_text + content_html_safe + image_url
3. aggiorna `articles.image_url` se mancava
4. classify -> matches[topic_id, score, position]
5. apply_classification (delete+insert in article_topics)
6. manticore replace (articles_rt)
7. mark_article_indexed
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.ingestion import classify, manticore_client, normalize
from app.ingestion.feed_parser import ArticleCandidate, make_url_hash
from app.models import Article, Source, Topic
from app.services import ingestion_service

log = structlog.get_logger()


def _candidate_from_article(article: Article) -> ArticleCandidate:
    """Ricostruisce un ArticleCandidate dai dati salvati al fetch."""
    raw = article.raw_meta_lite or {}
    return ArticleCandidate(
        external_id=article.external_id,
        url_canonical=article.url_canonical,
        url_hash=article.url_hash or make_url_hash(article.url_canonical),
        title=str(raw.get("title") or ""),
        description=raw.get("description"),
        content_html=raw.get("content_html"),
        author=article.author,
        published_at=article.published_at,
        updated_at=article.updated_at,
        image_url=article.image_url,
        origin_taxonomy=article.origin_taxonomy,
        raw_meta={k: v for k, v in raw.items() if k not in ("title", "description", "content_html")},
    )


async def _process_async(article_id: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        article = await session.get(Article, article_id)
        if article is None:
            log.warning("yf.process.article_missing", article_id=article_id)
            return

        source = await session.get(Source, int(article.source_id))
        if source is None:
            await ingestion_service.mark_article_failed(
                session, article_id=article_id, error="source_missing"
            )
            await session.commit()
            return

        candidate = _candidate_from_article(article)

        try:
            normalized = await normalize.normalize(candidate)
        except Exception as e:
            await ingestion_service.mark_article_failed(
                session, article_id=article_id, error=f"normalize: {e!s}"
            )
            await session.commit()
            raise

        # Aggiorna immagine se mancava nel feed
        if not article.image_url and normalized.image_url:
            article.image_url = normalized.image_url
            article.image_status = "pending"
        if normalized.internal_links:
            article.internal_links = normalized.internal_links

        # Classify — title-only policy (vedi decisione T-018): il body produce
        # troppo rumore (citazioni di brand/personaggi non centrali al pezzo).
        # I topic vengono estratti SOLO dal titolo, che è la sintesi più densa
        # del tema dell'articolo.
        title = candidate.title
        matches = await classify.classify(
            session,
            title=title,
            body_text="",
            origin_taxonomy=None,
        )
        n_topics = await ingestion_service.apply_classification(
            session, article_id=article_id, matches=matches
        )

        # Risolvo gli slug per Manticore (utile per filtri client-side)
        topic_slugs: list[str] = []
        if matches:
            ids = [m.topic_id for m in matches]
            slugs_rows = (
                await session.execute(select(Topic.id, Topic.slug).where(Topic.id.in_(ids)))
            ).all()
            slug_by_id: dict[int, str] = {int(rid): s for rid, s in slugs_rows}
            topic_slugs = [slug_by_id[m.topic_id] for m in matches if m.topic_id in slug_by_id]

        ok = await manticore_client.replace_article(
            article_id=article_id,
            title=title,
            description=candidate.description,
            content_text=normalized.content_text,
            content_html=normalized.content_html_safe,
            source_id=int(source.id),
            source_domain=ingestion_service.source_domain(source),
            topic_ids=[m.topic_id for m in matches],
            topic_slugs=topic_slugs,
            published_at=article.published_at,
            kind=source.kind,
        )

        if ok:
            await ingestion_service.mark_article_indexed(
                session, article_id=article_id
            )
            await session.commit()
            log.info(
                "yf.process.indexed",
                article_id=article_id,
                topics=n_topics,
                used_full_fetch=normalized.raw_meta.get("used_full_fetch", False),
            )
        else:
            await ingestion_service.mark_article_failed(
                session, article_id=article_id, error="manticore_replace_failed"
            )
            await session.commit()
            return

    # Enqueue image processor se abbiamo un image_url da scaricare
    if article.image_url and article.image_status == "pending":
        from app.workers.image import enqueue_image

        try:
            enqueue_image(article_id)
        except Exception as e:
            log.debug("yf.process.image_enqueue_failed", error=str(e))

    # Enqueue alerts matcher (best-effort: se Redis è down i match si
    # perderanno per questo articolo, ma il pipeline procede).
    if n_topics:
        from app.workers.alerts import enqueue_alerts_match

        try:
            enqueue_alerts_match(article_id)
        except Exception as e:
            log.debug("yf.process.alerts_enqueue_failed", error=str(e))


def process_article_job(*, article_id: int) -> None:
    try:
        asyncio.run(_process_async(article_id))
    except Exception as e:
        log.error("yf.process.failed", article_id=article_id, error=str(e))
        raise
