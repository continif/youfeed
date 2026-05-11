"""Worker RQ push: invia notifiche push agli utenti tramite Web Push.

Coda `QUEUE_PUSH` (già definita). Job accodati da `alert_service.match_article`
per gli alert che hanno `'push' in channels`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.db import get_session_factory
from app.queues import QUEUE_PUSH, get_queue
from app.services import push_service


log = structlog.get_logger()


async def _send_async(user_id: int, payload: dict[str, Any]) -> tuple[int, int, int]:
    factory = get_session_factory()
    async with factory() as session:
        result = await push_service.send_to_user(
            session, user_id=user_id, payload=payload
        )
        return result.sent, result.dropped, result.failed


def push_send_job(*, user_id: int, payload: dict[str, Any]) -> None:
    try:
        sent, dropped, failed = asyncio.run(_send_async(user_id, payload))
        log.info(
            "yf.push.job_done",
            user_id=user_id,
            sent=sent,
            dropped=dropped,
            failed=failed,
        )
    except Exception as e:
        log.error("yf.push.job_failed", user_id=user_id, error=str(e))
        raise


def enqueue_push(user_id: int, payload: dict[str, Any]) -> None:
    queue = get_queue(QUEUE_PUSH)
    queue.enqueue(
        push_send_job,
        user_id=int(user_id),
        payload=dict(payload),
        job_timeout="30s",
    )
