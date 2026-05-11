"""Servizio search (v1.1.D).

Wrapper su `manticore_client.search_articles` con:
  - filter auth-aware: utente loggato → solo articoli da sue `user_sources`
    pubbliche o private. Anonimo → su tutto il corpus indicizzato.
  - hydrate: dopo la search Manticore (che ritorna hit base + highlight),
    arricchisce con Source + Topic da Postgres.
  - suggestion endpoint: ritorna top topic/sources che iniziano con `prefix`.

Manticore è la source-of-truth per relevance e snippet. Postgres riempie
metadati (source.title, topic.display_name, ecc.) che non viviamo come
duplicati in Manticore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ingestion import manticore_client
from app.models import (
    Article,
    Source,
    Topic,
    UserSource,
)

log = structlog.get_logger()


@dataclass
class SearchHit:
    """Risultato singolo arricchito dei metadati."""
    article: Article
    source: Source
    topics: list[Topic]
    highlights: dict[str, str]  # title / description / content_text snippets


async def _user_source_ids(session: AsyncSession, user_id: int) -> list[int]:
    """Restituisce gli id delle sources iscritte dall'utente."""
    rows = (
        await session.execute(
            select(UserSource.source_id).where(UserSource.user_id == user_id)
        )
    ).all()
    return [int(r[0]) for r in rows]


async def search(
    session: AsyncSession,
    *,
    query: str,
    user_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SearchHit], int]:
    """Esegue la search e ritorna `(hits, total)`.

    Se `user_id` è None: cerca su tutto il corpus indicizzato (modalità
    pubblica/anonima). Altrimenti restringe alle sources iscritte dell'utente
    (timeline-coherent).
    """
    query = (query or "").strip()
    if not query:
        return [], 0

    source_ids: list[int] | None = None
    if user_id is not None:
        source_ids = await _user_source_ids(session, user_id)
        if not source_ids:
            # Utente senza source iscritte → nessun risultato.
            return [], 0

    result = await manticore_client.search_articles(
        query, source_ids=source_ids, limit=limit, offset=offset, highlight=True,
    )
    total = int(result.get("total") or 0)
    hits_raw = result.get("hits") or []
    if not hits_raw:
        return [], total

    article_ids = [int(h["id"]) for h in hits_raw]
    arts_q = (
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.id.in_(article_ids))
        .where(Article.processing_status == "indexed")
    )
    arts_by_id: dict[int, Article] = {
        int(a.id): a for a in (await session.execute(arts_q)).scalars().all()
    }
    if not arts_by_id:
        return [], total

    # Hydrate topic per articolo (solo i top 12 per evitare payload pesante)
    from app.models import ArticleTopic
    topic_rows = (
        await session.execute(
            select(ArticleTopic.article_id, Topic)
            .join(Topic, Topic.id == ArticleTopic.topic_id)
            .where(ArticleTopic.article_id.in_(article_ids))
            .order_by(ArticleTopic.score.desc())
        )
    ).all()
    topics_by_article: dict[int, list[Topic]] = {}
    for art_id, topic in topic_rows:
        topics_by_article.setdefault(int(art_id), []).append(topic)

    out: list[SearchHit] = []
    for h in hits_raw:
        aid = int(h["id"])
        a = arts_by_id.get(aid)
        if a is None:
            continue  # articolo droppato/non-indexed → skip
        out.append(SearchHit(
            article=a, source=a.source,
            topics=topics_by_article.get(aid, []),
            highlights=h.get("highlights") or {},
        ))
    return out, total


async def suggest(
    session: AsyncSession,
    *,
    prefix: str,
    limit: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    """Autocomplete: ritorna {topics: [{id, slug, display_name, type}],
    sources: [{id, title, url_site}]} per `prefix`.

    Match: ILIKE 'prefix%' su display_name (topics) e title (sources).
    """
    prefix = (prefix or "").strip()
    if len(prefix) < 2:
        return {"topics": [], "sources": []}
    like = f"{prefix}%"
    ilike = f"%{prefix}%"

    topic_rows = (
        await session.execute(
            select(Topic.id, Topic.slug, Topic.display_name, Topic.type)
            .where(Topic.is_curated == True)  # noqa: E712
            .where(Topic.type != "invalid")
            .where(or_(
                Topic.display_name.ilike(like),
                Topic.display_name.ilike(ilike),
            ))
            .order_by(func.length(Topic.display_name).asc())
            .limit(limit)
        )
    ).all()
    src_rows = (
        await session.execute(
            select(Source.id, Source.title, Source.url_site)
            .where(Source.status == "active")
            .where(or_(
                Source.title.ilike(like),
                Source.title.ilike(ilike),
            ))
            .order_by(func.length(Source.title).asc())
            .limit(limit)
        )
    ).all()
    return {
        "topics": [
            {"id": r.id, "slug": r.slug, "display_name": r.display_name, "type": r.type}
            for r in topic_rows
        ],
        "sources": [
            {"id": r.id, "title": r.title, "url_site": r.url_site}
            for r in src_rows
        ],
    }
