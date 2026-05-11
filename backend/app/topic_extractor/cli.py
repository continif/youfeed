"""CLI per il topic extractor.

Esempi:
    # Scan tutti gli articoli (PERSON+POPE+BRAND_ALPHA+BRAND_SINGLE)
    python -m app.topic_extractor.cli scan-generic

    # Scan limitato (debug)
    python -m app.topic_extractor.cli scan-generic --limit 200

    # Scan model usando i brand già confermati come whitelist (pass-2)
    python -m app.topic_extractor.cli scan-models

    # Top 50 candidati persona con count >= 5
    python -m app.topic_extractor.cli review --type REGEX_PER --top 50

    # Promuove l'entity 42 come brand
    python -m app.topic_extractor.cli confirm 42 --as-type brand

    # Marca come rumore
    python -m app.topic_extractor.cli reject 99
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.db import dispose_engine, get_session_factory
from app.topic_extractor import service


async def _cmd_scan(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        stats = await service.scan_articles(
            session,
            article_limit=args.limit,
            only_after_id=args.after_id,
            use_known_brands=False,
        )
        await session.commit()
    print(
        f"-> articles_seen={stats.articles_seen} "
        f"entities_processed={stats.entities_updated} "
        f"per_source_rows={stats.source_counts_updated}"
    )


async def _cmd_scan_models(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        brands = await service.known_brand_names(session)
        if not brands:
            print(
                "Nessun brand confermato. Esegui prima `confirm <id> --as-type brand`.",
                file=sys.stderr,
            )
            return
        print(f"-> brand whitelist: {len(brands)} elementi")
        stats = await service.scan_articles(
            session,
            article_limit=args.limit,
            only_after_id=None,
            use_known_brands=True,
        )
        await session.commit()
    print(
        f"-> articles_seen={stats.articles_seen} "
        f"entities_processed={stats.entities_updated}"
    )


async def _cmd_review(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        items = await service.review_top(
            session,
            ner_type=args.type,
            min_count=args.min_count,
            limit=args.top,
        )
    if not items:
        print("(nessun candidato sopra la soglia)")
        return
    print(
        f"{'id':>6}  {'count':>5}  {'src':>3}  {'type':<18}  surface_form  →  hint sub-token"
    )
    print("-" * 100)
    for it in items:
        hint = (
            ", ".join(f"{tok}={ttype}" for tok, ttype in it.subtoken_topics)
            if it.subtoken_topics
            else ""
        )
        print(
            f"{it.entity_id:>6}  "
            f"{it.occurrence_count:>5}  "
            f"{it.sources_count:>3}  "
            f"{it.ner_type:<18}  "
            f"{it.surface_form}"
            f"{('  →  ' + hint) if hint else ''}"
        )


async def _cmd_confirm(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        topic = await service.confirm_entity(
            session,
            entity_id=args.entity_id,
            as_type=args.as_type,
            display_name=args.display_name,
        )
        await session.commit()
    print(f"-> topic id={topic.id} slug={topic.slug} type={topic.type}")


async def _cmd_reject(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await service.reject_entity(session, entity_id=args.entity_id)
        await session.commit()
    print(f"-> entity {args.entity_id} marcata come ignored")


async def _main_async(args: argparse.Namespace) -> None:
    try:
        if args.cmd == "scan-generic":
            await _cmd_scan(args)
        elif args.cmd == "scan-models":
            await _cmd_scan_models(args)
        elif args.cmd == "review":
            await _cmd_review(args)
        elif args.cmd == "confirm":
            await _cmd_confirm(args)
        elif args.cmd == "reject":
            await _cmd_reject(args)
        else:
            print(f"comando ignoto: {args.cmd}", file=sys.stderr)
            sys.exit(2)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="YOUFEED topic extractor CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan-generic", help="Scan PERSON+POPE+BRAND_*")
    p_scan.add_argument("--limit", type=int, default=None)
    p_scan.add_argument(
        "--after-id",
        type=int,
        default=None,
        help="processa solo articoli con id > N (incrementale)",
    )

    p_models = sub.add_parser(
        "scan-models", help="Scan MODEL (richiede brand già confermati)"
    )
    p_models.add_argument("--limit", type=int, default=None)

    p_rev = sub.add_parser("review", help="Top candidati non risolti")
    p_rev.add_argument("--type", default=None, help="filtra per ner_type")
    p_rev.add_argument("--min-count", type=int, default=5)
    p_rev.add_argument("--top", type=int, default=50)

    p_conf = sub.add_parser("confirm", help="Promuovi entity → topic")
    p_conf.add_argument("entity_id", type=int)
    p_conf.add_argument(
        "--as-type",
        required=True,
        choices=("brand", "person", "location", "model", "subject"),
    )
    p_conf.add_argument("--display-name", default=None)

    p_rej = sub.add_parser("reject", help="Marca entity come rumore")
    p_rej.add_argument("entity_id", type=int)

    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
