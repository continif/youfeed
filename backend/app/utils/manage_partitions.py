"""Manutenzione partizioni `activity_log` (RANGE BY ts daily).

Funzioni helper SQL già definite in `migrations/0004_activity_log.py`:
  - `yf_create_activity_partition(date)` — crea la partizione per il giorno target
  - `yf_drop_old_activity_partitions(retention_days)` — droppa partizioni più vecchie

Questa CLI viene eseguita daily (vedi `infra/systemd/yf-manage-partitions.timer`):

    python -m app.utils.manage_partitions --create-ahead 7 --retention-days 180
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import text

from app.db import dispose_engine, get_engine

log = structlog.get_logger()


async def _run(create_ahead_days: int, retention_days: int) -> None:
    engine = get_engine()
    today = datetime.now(UTC).date()

    async with engine.begin() as conn:
        # Crea partizioni per i prossimi N giorni (idempotente lato funzione SQL)
        for offset in range(create_ahead_days + 1):
            target: date = today + timedelta(days=offset)
            await conn.execute(
                text("SELECT yf_create_activity_partition(:d)").bindparams(d=target)
            )
            log.info("yf.partitions.create_ok", date=target.isoformat())

        # Droppa partizioni più vecchie del retention
        result = await conn.execute(
            text("SELECT yf_drop_old_activity_partitions(:n)").bindparams(
                n=retention_days
            )
        )
        dropped = result.scalar() if hasattr(result, "scalar") else None
        log.info(
            "yf.partitions.dropped",
            retention_days=retention_days,
            count=dropped,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage activity_log partitions")
    parser.add_argument(
        "--create-ahead",
        type=int,
        default=7,
        help="quanti giorni futuri creare in anticipo (default: 7)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=180,
        help="partizioni più vecchie di N giorni vengono droppate (default: 180)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.create_ahead, args.retention_days))
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        try:
            asyncio.run(dispose_engine())
        except RuntimeError:
            pass  # event loop già chiuso


if __name__ == "__main__":
    main()
