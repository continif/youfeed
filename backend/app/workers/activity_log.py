"""Worker activity_log: drena la lista Redis e fa INSERT batch su Postgres.

Modalità di esecuzione: processo dedicato a sé (long-running), avviato come
servizio systemd. NON è un job RQ — usa BLPOP per drenare la lista finché
ci sono eventi.

Avvio manuale per dev:

    python -m app.workers.activity_log --batch 200 --max-wait 5

Per ogni batch:
1. BLPOP/LPOP fino a `batch` elementi (o timeout `max-wait`)
2. INSERT batch su `activity_log`
3. per gli eventi `event_type='preview_open'`/`'original_open'` su un articolo:
   UPDATE articles SET read_count = read_count + 1, last_read_at = NOW()
   (`'original_open'` aggiorna anche `open_count`)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import dispose_engine, get_session_factory
from app.middleware.activity_log import ACTIVITY_QUEUE_KEY
from app.models import ActivityLog, Article
from app.redis_client import dispose_redis, get_redis

log = structlog.get_logger()


_should_stop = False


def _setup_signals() -> None:
    def _on_signal(signum: int, _frame: object) -> None:  # noqa: ANN001
        global _should_stop
        log.info("yf.activity_log.signal", signum=signum)
        _should_stop = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)


async def _drain_batch(batch: int, max_wait_s: int) -> list[dict[str, Any]]:
    redis = get_redis()
    out: list[dict[str, Any]] = []

    # Primo elemento: BLPOP con timeout (blocca senza CPU spin)
    first = await redis.blpop([ACTIVITY_QUEUE_KEY], timeout=max_wait_s)
    if first is None:
        return out
    _, raw = first
    try:
        out.append(json.loads(raw))
    except json.JSONDecodeError:
        log.warning("yf.activity_log.parse_failed", raw=raw[:200])

    # Resto del batch: LPOP non bloccante finché c'è materiale
    for _ in range(batch - 1):
        raw = await redis.lpop(ACTIVITY_QUEUE_KEY)
        if raw is None:
            break
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            log.warning("yf.activity_log.parse_failed", raw=raw[:200])
    return out


def _to_row(event: dict[str, Any]) -> dict[str, Any]:
    """Mappa un evento JSON sulla riga `activity_log`."""
    ts = event.get("ts")
    if isinstance(ts, str):
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            ts_dt = datetime.now(UTC)
    else:
        ts_dt = datetime.now(UTC)

    sid = event.get("session_id")
    session_uuid = None
    if sid:
        try:
            import uuid as _uuid

            session_uuid = _uuid.UUID(str(sid))
        except (ValueError, TypeError):
            session_uuid = None

    # NB: il modello ActivityLog usa l'attributo Python `metadata_` perché
    # `metadata` è riservato su DeclarativeBase (= lo schema MetaData object).
    # Passando "metadata" qui, SQLAlchemy lo risolve contro Base.metadata e
    # crasha con "'MetaData' object has no attribute '_bulk_update_tuples'".
    return {
        "user_id": event.get("user_id"),
        "session_id": session_uuid,
        "fingerprint": event.get("fingerprint"),
        "event_type": str(event.get("event_type") or "http_request")[:32],
        "route": event.get("route"),
        "method": (event.get("method") or "")[:8] or None,
        "target_type": event.get("target_type"),
        "target_id": event.get("target_id"),
        "metadata_": event.get("metadata"),
        "ip": event.get("ip"),
        "country": (event.get("country") or "")[:8] or None,
        "asn": event.get("asn"),
        "ua": event.get("ua"),
        "status": event.get("status"),
        "latency_ms": event.get("latency_ms"),
        "ts": ts_dt,
    }


async def _flush_batch(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    rows = [_to_row(e) for e in events]

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(pg_insert(ActivityLog).values(rows))

        # Aggregati on-the-fly su `articles`: incrementa read/open_count
        # per gli eventi 'click' (lettura aperta in app) e 'open' (open in nuova tab).
        click_ids: list[int] = []
        open_ids: list[int] = []
        for e in events:
            if e.get("target_type") != "article":
                continue
            tid = e.get("target_id")
            try:
                article_id = int(tid) if tid is not None else None
            except (TypeError, ValueError):
                continue
            if article_id is None:
                continue
            # preview_open  = lettura aperta in app → conta come "read"
            # original_open = aperto nel sito originale → conta come "read" + "open"
            # (vedi PERSONALIZED.md per la semantica dei due contatori)
            etype = e.get("event_type")
            if etype == "preview_open":
                click_ids.append(article_id)
            elif etype == "original_open":
                click_ids.append(article_id)
                open_ids.append(article_id)

        # Increment in 1 query per id: usiamo un piccolo loop CASE — la quantità
        # di articoli distinti per batch è tipicamente < 30.
        for aid in set(click_ids):
            n_click = click_ids.count(aid)
            n_open = open_ids.count(aid)
            await session.execute(
                update(Article)
                .where(Article.id == aid)
                .values(
                    read_count=Article.read_count + n_click,
                    open_count=Article.open_count + n_open,
                    last_read_at=datetime.now(UTC),
                )
            )
        await session.commit()


async def _run(batch: int, max_wait_s: int) -> None:
    while not _should_stop:
        try:
            events = await _drain_batch(batch, max_wait_s)
            if events:
                await _flush_batch(events)
                log.info("yf.activity_log.flushed", count=len(events))
        except Exception as e:
            log.error("yf.activity_log.batch_failed", error=str(e))
            await asyncio.sleep(1.0)


async def _main_async(args: argparse.Namespace) -> None:
    _setup_signals()
    log.info("yf.activity_log.start", batch=args.batch, max_wait=args.max_wait)
    try:
        await _run(args.batch, args.max_wait)
    finally:
        await dispose_redis()
        await dispose_engine()
        log.info("yf.activity_log.stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED activity_log drainer")
    parser.add_argument("--batch", type=int, default=200, help="max eventi per flush")
    parser.add_argument(
        "--max-wait", type=int, default=5, help="secondi BLPOP wait per batch leader"
    )
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
