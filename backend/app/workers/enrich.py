"""Worker RQ enrich_wikidata: arricchisce un topic con dati Wikidata.

Idempotente: se il topic ha già un `wikidata_qid` in `external_refs` non
fa nulla (a meno che `force=True`).
"""

from __future__ import annotations

import asyncio

import structlog

from app.db import get_session_factory
from app.queues import QUEUE_ENRICH_WIKIDATA, get_queue
from app.services import wikidata_service


log = structlog.get_logger()


async def _enrich_async(topic_id: int, force: bool) -> str:
    factory = get_session_factory()
    async with factory() as session:
        result = await wikidata_service.enrich_topic(
            session, topic_id=topic_id, force=force
        )
        await session.commit()
        return result.status


def enrich_wikidata_job(*, topic_id: int, force: bool = False) -> None:
    try:
        status = asyncio.run(_enrich_async(topic_id, force))
        log.info("yf.enrich.job_done", topic_id=topic_id, status=status)
    except Exception as e:
        log.error("yf.enrich.job_failed", topic_id=topic_id, error=str(e))
        raise


def enqueue_enrich_wikidata(topic_id: int, *, force: bool = False) -> None:
    queue = get_queue(QUEUE_ENRICH_WIKIDATA)
    queue.enqueue(
        enrich_wikidata_job,
        topic_id=int(topic_id),
        force=force,
        job_timeout="30s",
    )
