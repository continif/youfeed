"""CLI per Wikidata enrichment dei topic (Phase 1.2.B).

Modi d'uso:

    # Singolo topic
    python -m app.utils.enrich_topics --topic-id 8116

    # Tutti i topic curati senza wikidata_qid (limite N)
    python -m app.utils.enrich_topics --missing --limit 50

    # Force overwrite di un topic già enriched
    python -m app.utils.enrich_topics --topic-id 8116 --force
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
import structlog
from sqlalchemy import select

from app.db import dispose_engine, get_session_factory
from app.logging_setup import setup_logging
from app.models import Topic
from app.services import wikidata_service


log = structlog.get_logger()


async def _enrich_one(client: httpx.AsyncClient, topic_id: int, force: bool) -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await wikidata_service.enrich_topic(
            session, topic_id=topic_id, force=force, client=client
        )
        await session.commit()
        log.info(
            "yf.enrich.cli_done",
            topic_id=topic_id,
            status=result.status,
            qid=result.qid,
            confidence=result.confidence,
            method=result.method,
        )


async def _select_missing(limit: int) -> list[int]:
    factory = get_session_factory()
    async with factory() as session:
        # Topic curati senza wikidata_qid, escluso type='invalid' (soft-blacklist)
        stmt = (
            select(Topic.id)
            .where(Topic.is_curated.is_(True))
            .where(Topic.type != "invalid")
            .where(
                (Topic.external_refs.is_(None))
                | (~Topic.external_refs.has_key("wikidata_qid"))  # noqa: E711
            )
            .order_by(Topic.id.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        return [int(r) for r in res.scalars().all()]


async def _main_async(args: argparse.Namespace) -> None:
    headers = {
        "User-Agent": wikidata_service.USER_AGENT,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(
        headers=headers, timeout=wikidata_service.TIMEOUT
    ) as client:
        if args.topic_id is not None:
            await _enrich_one(client, args.topic_id, args.force)
        elif args.missing:
            ids = await _select_missing(args.limit)
            log.info("yf.enrich.cli_batch_start", count=len(ids))
            for tid in ids:
                await _enrich_one(client, tid, args.force)
                # ratelimit cortese verso Wikidata API
                await asyncio.sleep(0.2)
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED Wikidata enrichment")
    parser.add_argument("--topic-id", type=int, default=None)
    parser.add_argument(
        "--missing",
        action="store_true",
        help="processa tutti i topic curati senza wikidata_qid",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="cap di topic per run quando si usa --missing (default 50)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="sovrascrivi anche topic già enriched",
    )
    args = parser.parse_args()

    if args.topic_id is None and not args.missing:
        parser.error("specifica --topic-id N oppure --missing")

    setup_logging()
    try:
        asyncio.run(_main_async(args))
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
