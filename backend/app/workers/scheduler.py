"""Scheduler ingestion: ogni `tick_seconds` controlla le sources "due" e
accoda i job fetch_rss/fetch_wp.

Lo scheduler è un processo a sé (vedi `infra/systemd/yf-scheduler.service`).
Avvio manuale per dev:

    python -m app.workers.scheduler --tick 60 --batch 50

Niente RQ Scheduler/cron: un loop semplice è sufficiente per v1.0 (1 nodo,
poche centinaia di sources). Quando passeremo a multi-nodo va sostituito
con APScheduler/Celery beat o con `rq-scheduler`.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys

import structlog

from app.db import dispose_engine, get_session_factory
from app.services import ingestion_service
from app.workers.fetch import enqueue_fetch_rss, enqueue_fetch_wp

log = structlog.get_logger()


_should_stop = False


def _setup_signals() -> None:
    def _on_signal(signum: int, _frame: object) -> None:  # noqa: ANN001
        global _should_stop
        log.info("yf.scheduler.signal", signum=signum)
        _should_stop = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)


async def _run(tick_seconds: int, batch: int, once: bool) -> None:
    factory = get_session_factory()

    while not _should_stop:
        try:
            async with factory() as session:
                due = await ingestion_service.select_due_sources(
                    session, limit=batch
                )

            if due:
                rss = 0
                wp = 0
                for source in due:
                    if source.kind == "rss":
                        enqueue_fetch_rss(int(source.id))
                        rss += 1
                    elif source.kind == "wordpress_api":
                        enqueue_fetch_wp(int(source.id))
                        wp += 1
                log.info("yf.scheduler.tick", enqueued_rss=rss, enqueued_wp=wp)
            else:
                log.debug("yf.scheduler.tick_idle")
        except Exception as e:
            log.error("yf.scheduler.tick_failed", error=str(e))

        if once:
            return

        for _ in range(tick_seconds):
            if _should_stop:
                break
            await asyncio.sleep(1)


async def _main_async(args: argparse.Namespace) -> None:
    _setup_signals()
    log.info("yf.scheduler.start", tick=args.tick, batch=args.batch, once=args.once)
    try:
        await _run(args.tick, args.batch, args.once)
    finally:
        await dispose_engine()
        log.info("yf.scheduler.stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED ingestion scheduler")
    parser.add_argument("--tick", type=int, default=60, help="secondi tra tick")
    parser.add_argument("--batch", type=int, default=50, help="max sources per tick")
    parser.add_argument("--once", action="store_true", help="esegui un solo tick e termina")
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
