"""CLI per il retention sweep (Phase 1.2.G).

Da eseguire una volta a settimana (cron / systemd timer):

    python -m app.utils.retention_sweep                    # default 365 giorni
    python -m app.utils.retention_sweep --dry-run          # solo conta candidati
    python -m app.utils.retention_sweep --max-age-days 730 # tieni 2 anni
    python -m app.utils.retention_sweep --max-batches 2    # limita per primi run

Settings (defaults):
- max_age_days = 365
- batch_size = 500
- max_batches = None (cancella tutto in un colpo)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.db import dispose_engine, get_session_factory
from app.logging_setup import setup_logging
from app.services import retention_service


log = structlog.get_logger()


async def _main_async(args: argparse.Namespace) -> retention_service.SweepStats:
    factory = get_session_factory()
    async with factory() as session:
        stats = await retention_service.sweep(
            session,
            max_age_days=args.max_age_days,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            dry_run=args.dry_run,
        )
    await dispose_engine()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED retention sweep")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=retention_service.DEFAULT_MAX_AGE_DAYS,
        help="età massima (giorni) di un articolo prima del candidato drop",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=retention_service.DEFAULT_BATCH_SIZE,
        help="articoli per batch (default 500)",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="max batch da eseguire in questo run (default: nessun limite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="solo conta candidati, nessuna cancellazione",
    )
    args = parser.parse_args()

    setup_logging()
    log.info(
        "yf.retention.start",
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
    )
    try:
        stats = asyncio.run(_main_async(args))
        log.info(
            "yf.retention.done",
            candidates=stats.candidates,
            deleted=stats.deleted,
            manticore_failed=stats.manticore_failed,
            dry_run=stats.dry_run,
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
