"""Elimina i topic usati da 0 articoli.

Di default tocca SOLO i topic auto (`is_curated=false`) e mai quelli
`type='invalid'`: sono il blocklist che impedisce all'extractor di ricrearli
(`on_conflict_do_nothing` su slug). I topic curated (dizionario seed: comuni,
brand, ecc.) hanno quasi tutti 0 articoli per natura, per questo restano
fuori salvo `--include-curated`. I topic seguiti da un alert non vengono mai
cancellati.

    python -m app.utils.prune_unused_topics                  # dry-run
    python -m app.utils.prune_unused_topics --apply
    python -m app.utils.prune_unused_topics --apply --include-curated
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.db import dispose_engine, get_session_factory
from app.models import ArticleTopic, Topic
from app.models.alerts import AlertTopic


async def _main_async(apply: bool, include_curated: bool) -> None:
    factory = get_session_factory()
    async with factory() as session:
        cond = [
            Topic.type != "invalid",
            ~select(ArticleTopic.topic_id).where(ArticleTopic.topic_id == Topic.id).exists(),
            ~select(AlertTopic.topic_id).where(AlertTopic.topic_id == Topic.id).exists(),
        ]
        if not include_curated:
            cond.append(Topic.is_curated == False)  # noqa: E712

        by_type = (
            await session.execute(
                select(Topic.type, func.count()).where(*cond).group_by(Topic.type)
            )
        ).all()
        total = sum(n for _, n in by_type)
        for t, n in sorted(by_type, key=lambda r: -r[1]):
            print(f"  {t:14} {n}")
        print(f"candidati: {total} ({'curated inclusi' if include_curated else 'solo non-curated'})")

        if not apply:
            print("(dry-run: nessuna cancellazione, usa --apply)")
        elif total:
            res = await session.execute(delete(Topic).where(*cond))
            await session.commit()
            print(f"eliminati: {res.rowcount}")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Elimina topic con 0 articoli")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--include-curated",
        action="store_true",
        help="include anche i topic curated (svuota il dizionario seed!)",
    )
    args = parser.parse_args()
    asyncio.run(_main_async(args.apply, args.include_curated))


if __name__ == "__main__":
    main()
