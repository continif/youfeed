"""CLI di smoke test per la pipeline ingestion.

Comandi:
    # Aggiungi una source da URL (passa per discovery)
    python -m app.utils.ingest_cli add-source https://www.ansa.it/sito/notizie/topnews/index.xml

    # Forza fetch+process di una source per id (sincrono, no RQ)
    python -m app.utils.ingest_cli run-source <source_id>

    # Lista sources con stato
    python -m app.utils.ingest_cli list-sources

Lo scopo è testare la pipeline end-to-end senza dipendere dal worker RQ.
In produzione la stessa pipeline gira come job nelle code RQ.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.db import dispose_engine, get_session_factory
from app.ingestion import classify, feed_parser, manticore_client, normalize, wp_api
from app.models import Source
from app.services import discovery_service, ingestion_service
from app.workers.image import _process_async as _process_image_async
from app.workers.process import _process_async

log = structlog.get_logger()


async def _add_source(url: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        result, source = await discovery_service.discover_and_persist(
            session, url=url
        )
        if source is None:
            print(f"[invalid] {url}: {result.reason}", file=sys.stderr)
            return
        await session.commit()
        print(f"[{result.kind}] source_id={source.id} title={source.title!r}")
        if result.candidates:
            for c in result.candidates:
                print(f"  feed: {c.url_feed} ({len(c.sample_articles)} sample)")


async def _run_source(source_id: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            print(f"source {source_id} non trovata", file=sys.stderr)
            return

        print(f"-> fetch source {source.id} kind={source.kind} title={source.title!r}")

        if source.kind == "rss":
            result = await feed_parser.fetch_rss(
                source.url_feed,  # type: ignore[arg-type]
                etag=source.etag,
                last_modified=source.last_modified,
            )
        elif source.kind == "wordpress_api":
            result = await wp_api.fetch_wp(
                source.wp_api_root,  # type: ignore[arg-type]
                after=source.last_success_at,
            )
        else:
            print(f"kind {source.kind} non supportato")
            return

        if result.error:
            print(f"errore fetch: {result.error}", file=sys.stderr)
            await ingestion_service.mark_source_failure(
                session, source=source, error=result.error
            )
            await session.commit()
            return

        if result.not_modified:
            print("304 not modified")
            await ingestion_service.mark_source_not_modified(session, source=source)
            await session.commit()
            return

        print(f"   trovati {len(result.articles)} articoli nel feed")
        new_ids = await ingestion_service.ingest_candidates(
            session, source=source, candidates=result.articles
        )
        print(f"   inseriti nuovi: {len(new_ids)}")
        await ingestion_service.mark_source_success(
            session,
            source=source,
            new_etag=getattr(result, "new_etag", None),
            new_last_modified=getattr(result, "new_last_modified", None),
        )
        await session.commit()

    # Processa ogni nuovo articolo (in process, niente RQ): normalize+classify+manticore
    for aid in new_ids:
        try:
            await _process_async(aid)
            await _process_image_async(aid)
            print(f"   processed article_id={aid} (+image)")
        except Exception as e:
            print(f"   FAIL article_id={aid}: {e}", file=sys.stderr)


async def _list_sources() -> None:
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(Source).order_by(Source.id))).scalars().all()
        for s in rows:
            ref = s.url_feed or s.wp_api_root or s.url_site or "?"
            print(
                f"  [{s.id:>4}] kind={s.kind:<14} status={s.status:<8} "
                f"poll={s.poll_interval}s last={s.last_fetched_at} {ref}"
            )


async def _main_async(args: argparse.Namespace) -> None:
    try:
        if args.cmd == "add-source":
            await _add_source(args.url)
        elif args.cmd == "run-source":
            await _run_source(args.source_id)
        elif args.cmd == "list-sources":
            await _list_sources()
        else:
            print("comando ignoto", file=sys.stderr)
            sys.exit(2)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED ingestion CLI di test")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add-source", help="Aggiungi una source via discovery")
    add.add_argument("url")

    run = sub.add_parser("run-source", help="Esegue fetch+process di una source")
    run.add_argument("source_id", type=int)

    sub.add_parser("list-sources", help="Lista sources nel DB")

    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
