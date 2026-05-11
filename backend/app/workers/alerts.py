"""Worker RQ alerts_match: alla fine di `process_article` viene accodato
un job che chiama `alert_service.match_article(article_id)`, creando
`alert_matches` + `notifications` per gli alert utente che matchano i topic
estratti.

Idempotente: la PK composita su `alert_matches` impedisce duplicati.

Accoda con:

    from app.workers.alerts import enqueue_alerts_match
    enqueue_alerts_match(article_id)
"""

from __future__ import annotations

import asyncio

import structlog

from app.db import get_session_factory
from app.queues import QUEUE_ALERTS_MATCH, get_queue
from app.services import alert_service


log = structlog.get_logger()


async def _match_async(article_id: int) -> int:
    factory = get_session_factory()
    async with factory() as session:
        return await alert_service.match_article(session, article_id=article_id)


def alerts_match_article_job(*, article_id: int) -> None:
    try:
        n = asyncio.run(_match_async(article_id))
        if n:
            log.info("yf.alerts.match_job_done", article_id=article_id, created=n)
    except Exception as e:
        log.error("yf.alerts.match_job_failed", article_id=article_id, error=str(e))
        raise


def enqueue_alerts_match(article_id: int) -> None:
    queue = get_queue(QUEUE_ALERTS_MATCH)
    queue.enqueue(
        alerts_match_article_job,
        article_id=int(article_id),
        job_timeout="30s",
    )
