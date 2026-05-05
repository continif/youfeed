"""Worker RQ per l'invio email.

I job sono funzioni top-level **sincrone**: RQ chiama queste, dentro avviamo
l'event loop con `asyncio.run(...)` per riusare il client `aiosmtplib`.

Per accodare un job dal codice applicativo:

    from app.workers.email import enqueue_verification, enqueue_password_reset
    enqueue_verification(to=user.email, username=user.username, token=token)
"""

from __future__ import annotations

import asyncio

import structlog

from app.queues import QUEUE_EMAIL, get_queue
from app.services import email_service

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Job functions (eseguite dal processo `rq worker email`)
# ---------------------------------------------------------------------------


def send_verification_email_job(*, to: str, username: str, token: str) -> None:
    """Job RQ: invia email di verifica."""
    try:
        asyncio.run(
            email_service.send_verification_email(to=to, username=username, token=token)
        )
    except Exception as e:
        log.error("yf.email.verification_failed", to=to, error=str(e))
        raise  # RQ farà retry secondo policy


def send_password_reset_email_job(*, to: str, username: str, token: str) -> None:
    """Job RQ: invia email di reset password (Phase 1.1)."""
    try:
        asyncio.run(
            email_service.send_password_reset_email(to=to, username=username, token=token)
        )
    except Exception as e:
        log.error("yf.email.reset_failed", to=to, error=str(e))
        raise


# ---------------------------------------------------------------------------
# Enqueue helpers (chiamati da FastAPI handler / service)
# ---------------------------------------------------------------------------


def enqueue_verification(*, to: str, username: str, token: str) -> None:
    """Accoda l'invio dell'email di verifica."""
    queue = get_queue(QUEUE_EMAIL)
    queue.enqueue(
        send_verification_email_job,
        to=to,
        username=username,
        token=token,
        retry=_default_retry(),
        job_timeout="1m",
    )


def enqueue_password_reset(*, to: str, username: str, token: str) -> None:
    queue = get_queue(QUEUE_EMAIL)
    queue.enqueue(
        send_password_reset_email_job,
        to=to,
        username=username,
        token=token,
        retry=_default_retry(),
        job_timeout="1m",
    )


def _default_retry():  # noqa: ANN202 — RQ Retry import-on-demand
    """Retry exponenziale: 30s → 2m → 10m → fail."""
    from rq import Retry

    return Retry(max=3, interval=[30, 120, 600])
