"""CLI per generare i digest giornalieri.

Da eseguire una volta al giorno (cron / systemd timer):

    python -m app.utils.notify_digest

Idempotente: salta utenti che hanno già ricevuto un digest oggi (UTC).
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from app.db import dispose_engine, get_session_factory
from app.logging_setup import setup_logging
from app.services import notification_service


log = structlog.get_logger()


async def _main_async() -> int:
    factory = get_session_factory()
    async with factory() as session:
        created = await notification_service.generate_daily_digests(session)
    await dispose_engine()
    return created


def main() -> None:
    setup_logging()
    log.info("yf.notify_digest.start")
    try:
        created = asyncio.run(_main_async())
        log.info("yf.notify_digest.done", created=created)
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
