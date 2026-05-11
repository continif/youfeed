"""Orchestrazione pipeline ingestion (lato DB).

Responsabilità:
- `ingest_candidates`: inserisce gli `ArticleCandidate` in `articles` con
  ON CONFLICT (url_hash) DO NOTHING. Ritorna gli id dei nuovi inseriti.
- `mark_source_fetched`: aggiorna `last_fetched_at` / `last_success_at` /
  `consecutive_failures` / `etag` / `last_modified` per la source.
- `select_due_sources`: query "fonti da pollare adesso" usata dallo scheduler.
- `apply_classification`: persiste i `TopicMatch` nella tabella `article_topics`.

Niente fetch HTTP qui dentro: quelle stanno in `app/ingestion/*`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable
from urllib.parse import urlparse

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.classify import TopicMatch
from app.ingestion.feed_parser import ArticleCandidate
from app.models import Article, ArticleTopic, Source

log = structlog.get_logger()


def _domain_of(source: Source) -> str | None:
    for url in (source.url_feed, source.url_site, source.wp_api_root):
        if not url:
            continue
        try:
            netloc = urlparse(url).netloc
        except Exception:
            continue
        if netloc:
            return netloc.lower()
    return None


async def ingest_candidates(
    session: AsyncSession,
    *,
    source: Source,
    candidates: Iterable[ArticleCandidate],
) -> list[int]:
    """Inserisce gli articoli nuovi e ritorna gli id appena creati."""
    rows = []
    for c in candidates:
        rows.append(
            {
                "source_id": int(source.id),
                "external_id": c.external_id,
                "kind": source.kind,
                "url_canonical": c.url_canonical,
                "url_hash": c.url_hash,
                "image_url": c.image_url,
                "image_status": "pending" if c.image_url else "skipped",
                "author": c.author,
                "published_at": c.published_at,
                "updated_at": c.updated_at,
                "processing_status": "new",
                "origin_taxonomy": c.origin_taxonomy,
                "raw_meta_lite": {
                    "title": c.title,
                    "description": c.description,
                    "content_html": c.content_html,
                    **(c.raw_meta or {}),
                },
            }
        )
    if not rows:
        return []

    stmt = (
        pg_insert(Article)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["url_hash"])
        .returning(Article.id)
    )
    result = await session.execute(stmt)
    inserted_ids = [int(r[0]) for r in result.all()]
    log.info(
        "yf.ingest.upsert",
        source_id=int(source.id),
        seen=len(rows),
        inserted=len(inserted_ids),
    )
    return inserted_ids


async def mark_source_success(
    session: AsyncSession,
    *,
    source: Source,
    new_etag: str | None = None,
    new_last_modified: str | None = None,
) -> None:
    now = datetime.now(UTC)
    source.last_fetched_at = now
    source.last_success_at = now
    source.consecutive_failures = 0
    if new_etag is not None:
        source.etag = new_etag
    if new_last_modified is not None:
        source.last_modified = new_last_modified
    if source.status in ("pending", "broken"):
        source.status = "active"


async def mark_source_failure(
    session: AsyncSession, *, source: Source, error: str
) -> None:
    now = datetime.now(UTC)
    source.last_fetched_at = now
    source.consecutive_failures = (source.consecutive_failures or 0) + 1
    if source.consecutive_failures >= 5:
        source.status = "broken"
    log.warning(
        "yf.ingest.fetch_failed",
        source_id=int(source.id),
        error=error,
        consecutive=source.consecutive_failures,
    )


async def mark_source_not_modified(
    session: AsyncSession, *, source: Source
) -> None:
    now = datetime.now(UTC)
    source.last_fetched_at = now
    source.last_success_at = now
    source.consecutive_failures = 0


async def select_due_sources(
    session: AsyncSession, *, limit: int = 100
) -> list[Source]:
    """Sources da pollare adesso: status in (active|pending) e
    (last_fetched_at IS NULL OR now - last_fetched_at >= poll_interval)."""
    now = datetime.now(UTC)
    grace = timedelta(seconds=1)
    stmt = (
        select(Source)
        .where(Source.kind.in_(("rss", "wordpress_api")))
        .where(Source.status.in_(("active", "pending")))
        .where(
            or_(
                Source.last_fetched_at.is_(None),
                # `now - last_fetched_at >= poll_interval` riscritto
                # come `last_fetched_at <= now - poll_interval seconds`.
                # SQLAlchemy non ha un modo carino per esprimerlo con
                # un Integer; usiamo func.now() - make_interval più sotto
                # via SQL letterale.
                and_(
                    Source.last_fetched_at.isnot(None),
                ),
            )
        )
        .order_by(Source.last_fetched_at.asc().nullsfirst())
        .limit(limit * 4)  # filtraggio finale in Python (semplice + corretto)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[Source] = []
    for s in rows:
        if s.last_fetched_at is None:
            out.append(s)
            continue
        elapsed = (now - s.last_fetched_at).total_seconds()
        if elapsed + grace.total_seconds() >= (s.poll_interval or 1800):
            out.append(s)
        if len(out) >= limit:
            break
    return out


async def apply_classification(
    session: AsyncSession,
    *,
    article_id: int,
    matches: list[TopicMatch],
) -> int:
    """Sostituisce le righe in `article_topics` per l'articolo."""
    # Strategia semplice: cancella e re-inserisci. v1.0 non ha update concorrenti
    # sullo stesso articolo (un solo worker process_article alla volta per id).
    from sqlalchemy import delete

    await session.execute(
        delete(ArticleTopic).where(ArticleTopic.article_id == article_id)
    )
    if not matches:
        return 0

    rows = [
        {
            "article_id": article_id,
            "topic_id": m.topic_id,
            "score": m.score,
            "source": m.source,
            "position": m.position,
        }
        for m in matches
    ]
    await session.execute(pg_insert(ArticleTopic).values(rows))
    return len(rows)


async def mark_article_indexed(
    session: AsyncSession, *, article_id: int
) -> None:
    article = await session.get(Article, article_id)
    if article is not None:
        article.processing_status = "indexed"
        article.processing_error = None


async def mark_article_failed(
    session: AsyncSession, *, article_id: int, error: str
) -> None:
    article = await session.get(Article, article_id)
    if article is not None:
        article.processing_status = "failed"
        article.processing_error = error[:500]


def source_domain(source: Source) -> str | None:
    """Helper pubblico per i worker (Manticore vuole la stringa)."""
    return _domain_of(source)
