"""Worker RQ: fetch RSS o WordPress API per una source.

Pattern come `workers/email.py`: funzioni top-level sync che dentro
chiamano `asyncio.run(...)` per fare I/O async.

Job principali:
- `fetch_rss_job(source_id)` -> coda QUEUE_FETCH_RSS
- `fetch_wp_job(source_id)`  -> coda QUEUE_FETCH_WP

Output: enqueue `process_article(article_id)` per ogni nuovo articolo.
"""

from __future__ import annotations

import asyncio

import structlog

from app.db import get_session_factory
from app.ingestion import feed_parser, wp_api
from app.models import Source
from app.queues import (
    QUEUE_FETCH_RSS,
    QUEUE_FETCH_WP,
    QUEUE_PROCESS_ARTICLE,
    get_queue,
)
from app.services import ingestion_service

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Async cores
# ---------------------------------------------------------------------------


async def _fetch_rss_async(source_id: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        source = await session.get(Source, source_id)
        if source is None or not source.url_feed:
            log.warning("yf.fetch_rss.source_missing", source_id=source_id)
            return

        result = await feed_parser.fetch_rss(
            source.url_feed,
            etag=source.etag,
            last_modified=source.last_modified,
        )

        if result.error:
            await ingestion_service.mark_source_failure(
                session, source=source, error=result.error
            )
            await session.commit()
            return

        if result.not_modified:
            await ingestion_service.mark_source_not_modified(session, source=source)
            await session.commit()
            return

        new_ids = await ingestion_service.ingest_candidates(
            session, source=source, candidates=result.articles
        )
        await ingestion_service.mark_source_success(
            session,
            source=source,
            new_etag=result.new_etag,
            new_last_modified=result.new_last_modified,
        )
        await session.commit()

    _enqueue_process(new_ids)


async def _fetch_wp_async(source_id: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        source = await session.get(Source, source_id)
        if source is None or not source.wp_api_root:
            log.warning("yf.fetch_wp.source_missing", source_id=source_id)
            return

        result = await wp_api.fetch_wp(
            source.wp_api_root,
            after=source.last_success_at,
        )

        if result.error:
            await ingestion_service.mark_source_failure(
                session, source=source, error=result.error
            )
            await session.commit()
            return

        new_ids = await ingestion_service.ingest_candidates(
            session, source=source, candidates=result.articles
        )
        await ingestion_service.mark_source_success(session, source=source)
        await session.commit()

    _enqueue_process(new_ids)


def _enqueue_process(article_ids: list[int]) -> None:
    if not article_ids:
        return
    # import locale per evitare ciclo workers.process -> workers.fetch
    from app.workers.process import process_article_job

    queue = get_queue(QUEUE_PROCESS_ARTICLE)
    for aid in article_ids:
        queue.enqueue(process_article_job, article_id=aid, job_timeout="3m")


# ---------------------------------------------------------------------------
# RQ entry points (sync)
# ---------------------------------------------------------------------------


def fetch_rss_job(*, source_id: int) -> None:
    try:
        asyncio.run(_fetch_rss_async(source_id))
    except Exception as e:
        log.error("yf.fetch_rss.failed", source_id=source_id, error=str(e))
        raise


def fetch_wp_job(*, source_id: int) -> None:
    try:
        asyncio.run(_fetch_wp_async(source_id))
    except Exception as e:
        log.error("yf.fetch_wp.failed", source_id=source_id, error=str(e))
        raise


# ---------------------------------------------------------------------------
# Enqueue helpers (chiamati dallo scheduler)
# ---------------------------------------------------------------------------


def enqueue_fetch_rss(source_id: int) -> None:
    queue = get_queue(QUEUE_FETCH_RSS)
    queue.enqueue(fetch_rss_job, source_id=source_id, job_timeout="2m")


def enqueue_fetch_wp(source_id: int) -> None:
    queue = get_queue(QUEUE_FETCH_WP)
    queue.enqueue(fetch_wp_job, source_id=source_id, job_timeout="2m")
