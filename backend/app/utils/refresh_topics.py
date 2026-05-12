"""Bulk refresh dei topic già presenti.

Cosa fa il tool — tre operazioni opzionali, scegliere via flag:

1. `--reenrich`: rilancia `wikidata_service.enrich_topic(force=True)` per
   ogni topic, popolando i campi nuovi (instance_of, country, owned_by,
   official_url) sui topic enrichati prima del commit 46353e7.

2. `--reclassify-type`: usa `infer_type_from_p31` sui Q-id `instance_of`
   per suggerire un type più accurato (es. "Apple Inc." passa da
   `brand` a `company`, "Linux" da `subject` a `software`). Per default
   è solo `--dry-run`; con `--apply` scrive in DB.

3. (default se nessun flag): mostra solo statistiche sul `type` corrente
   e su quanti topic mancano dei campi nuovi.

CLI esempi:

    # Quanti topic sono "incompleti" — niente scrittura
    python -m app.utils.refresh_topics

    # Re-enrich di tutti i topic con QID (popola i nuovi campi)
    python -m app.utils.refresh_topics --reenrich --all

    # Solo i location malposizionati: re-classify type (dry-run)
    python -m app.utils.refresh_topics --reclassify-type --type location

    # Riassegna type per davvero
    python -m app.utils.refresh_topics --reclassify-type --apply --all

    # Lotto di 100, partendo dall'inizio (utile per primo run su 10k+)
    python -m app.utils.refresh_topics --reenrich --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path as _P

import httpx
import structlog
from sqlalchemy import select

from app.db import dispose_engine, get_session_factory
from app.models import Topic
from app.services.wikidata_service import (
    TIMEOUT,
    USER_AGENT,
    enrich_topic,
    infer_type_from_p31,
)

# Carica .env come fanno gli altri utility CLI standalone (no FastAPI lifespan).
_env_file = _P(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if " #" in _v:
                _v = _v.split(" #", 1)[0]
            os.environ.setdefault(_k.strip(), _v.strip())


log = structlog.get_logger()


async def _list_topics(
    session,
    *,
    topic_type: str | None,
    limit: int | None,
    only_with_qid: bool,
) -> list[Topic]:
    stmt = select(Topic)
    if topic_type:
        stmt = stmt.where(Topic.type == topic_type)
    if only_with_qid:
        # external_refs ? 'wikidata_qid' — Postgres JSONB key existence
        stmt = stmt.where(Topic.external_refs.op("?")("wikidata_qid"))
    stmt = stmt.order_by(Topic.id)
    if limit:
        stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def cmd_stats(session) -> None:
    """Stampa solo statistiche, niente scritture."""
    all_topics = await _list_topics(
        session, topic_type=None, limit=None, only_with_qid=False
    )
    if not all_topics:
        print("Nessun topic.")
        return

    by_type: Counter[str] = Counter(t.type for t in all_topics)
    with_qid = 0
    missing_fields = 0  # topic con QID ma senza i nuovi campi (pre-46353e7)
    for t in all_topics:
        refs = t.external_refs or {}
        if refs.get("wikidata_qid"):
            with_qid += 1
            if not any(
                refs.get(k) for k in ("instance_of", "country", "owned_by", "official_url")
            ):
                missing_fields += 1

    print(f"Totale topic: {len(all_topics)}")
    print(f"  con QID Wikidata: {with_qid}")
    print(f"  con QID ma SENZA i nuovi campi (refresh utile): {missing_fields}")
    print("\nDistribuzione type:")
    for ttype, n in by_type.most_common():
        print(f"  {ttype:13s} {n:5d}")


async def cmd_reenrich(
    session,
    topics: list[Topic],
    *,
    skip_complete: bool,
) -> None:
    """Re-fetch da Wikidata. `skip_complete=True` salta i topic che hanno
    già i campi nuovi (utile per riprese dopo un'interruzione)."""
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    ) as client:
        ok = no_match = skipped = errors = 0
        for i, topic in enumerate(topics, 1):
            refs = topic.external_refs or {}
            if skip_complete and refs.get("wikidata_qid") and any(
                refs.get(k)
                for k in ("instance_of", "country", "owned_by", "official_url")
            ):
                skipped += 1
                continue
            try:
                res = await enrich_topic(
                    session,
                    topic_id=int(topic.id),
                    force=True,
                    client=client,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("yf.refresh.error", topic_id=topic.id, error=str(e))
                errors += 1
                continue
            if res.status == "enriched":
                ok += 1
            elif res.status in ("no_match", "low_confidence"):
                no_match += 1
            else:
                skipped += 1
            if i % 50 == 0:
                await session.commit()
                print(f"  …{i}/{len(topics)} processed", file=sys.stderr)
        await session.commit()
    print(
        f"reenrich completato: enriched={ok} no_match={no_match} "
        f"skipped={skipped} errors={errors}"
    )


async def cmd_reclassify_type(
    session, topics: list[Topic], *, apply: bool
) -> None:
    """Per ogni topic con instance_of popolato, calcola il `type` inferito
    da P31 e confronta col `type` corrente. In `apply=True` scrive il nuovo
    type in DB; altrimenti stampa solo un report."""
    changes: list[tuple[int, str, str, str]] = []
    no_p31 = 0
    same = 0
    for topic in topics:
        refs = topic.external_refs or {}
        instance_of = refs.get("instance_of") or []
        if not isinstance(instance_of, list) or not instance_of:
            no_p31 += 1
            continue
        p31_qids: set[str] = set()
        for item in instance_of:
            if isinstance(item, dict) and item.get("qid"):
                p31_qids.add(str(item["qid"]))
        suggested = infer_type_from_p31(p31_qids)
        if suggested is None or suggested == topic.type:
            same += 1
            continue
        changes.append((int(topic.id), topic.display_name, topic.type, suggested))

    print(f"\nReclassify report ({len(topics)} topic analizzati):")
    print(f"  invariati (type già coerente con P31): {same}")
    print(f"  senza instance_of (skip): {no_p31}")
    print(f"  da riassegnare: {len(changes)}\n")

    for tid, name, old, new in changes[:200]:
        marker = "→" if apply else "?"
        print(f"  {tid:6d}  {name[:40]:40s}  {old:13s} {marker} {new}")
    if len(changes) > 200:
        print(f"  …+{len(changes) - 200} altri")

    if apply and changes:
        for tid, _, _, new_type in changes:
            t = await session.get(Topic, tid)
            if t is not None:
                t.type = new_type
        await session.commit()
        print(f"\n{len(changes)} topic riassegnati in DB.")
    elif changes and not apply:
        print("\n[dry-run] Aggiungi --apply per scrivere in DB.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--reenrich", action="store_true", help="Re-fetch Wikidata su topic esistenti")
    p.add_argument(
        "--reclassify-type",
        action="store_true",
        help="Suggerisce un type più accurato basato su P31 (default: dry-run)",
    )
    p.add_argument("--apply", action="store_true", help="Scrive le modifiche in DB")
    p.add_argument("--all", action="store_true", help="Tutti i topic (no limit)")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max topic da processare (default: 100 in reenrich; ignorato con --all)",
    )
    p.add_argument(
        "--type",
        dest="topic_type",
        default=None,
        help="Filtra per Topic.type (es. 'brand', 'subject', …)",
    )
    p.add_argument(
        "--include-complete",
        action="store_true",
        help="Re-enrich anche i topic che hanno già i nuovi campi (forza retry)",
    )
    return p.parse_args()


async def _main_async(args: argparse.Namespace) -> None:
    factory = get_session_factory()
    try:
        async with factory() as session:
            # Default: stats
            if not args.reenrich and not args.reclassify_type:
                await cmd_stats(session)
                return

            limit = None if args.all else (args.limit or 100)
            only_with_qid = args.reclassify_type and not args.reenrich
            topics = await _list_topics(
                session,
                topic_type=args.topic_type,
                limit=limit,
                only_with_qid=only_with_qid,
            )
            print(
                f"Selezionati {len(topics)} topic (type={args.topic_type or 'qualsiasi'}, "
                f"limit={limit or 'nessuno'})"
            )

            if args.reenrich:
                await cmd_reenrich(
                    session, topics, skip_complete=not args.include_complete
                )

            if args.reclassify_type:
                # In modalità combinata, ricarico i topic così instance_of è fresh.
                if args.reenrich:
                    topics = await _list_topics(
                        session,
                        topic_type=args.topic_type,
                        limit=limit,
                        only_with_qid=True,
                    )
                await cmd_reclassify_type(session, topics, apply=args.apply)
    finally:
        await dispose_engine()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
