"""Carica i seed YAML in Postgres (idempotente, basato su slug/word).

Esempio:
    python -m app.utils.seed_loader \\
        --reserved-words ../Claude/reserved-words.txt \\
        --topics ../infra/seed/topics.yaml \\
        --featured ../infra/seed/featured_sources.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# NB: questa utility legge DATABASE_URL direttamente da env per non dipendere
# da app.config — utile prima che config.py sia in stato definitivo.
import os
from pathlib import Path as _P

_env_file = _P(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            # strip commento inline (spazio + hash, per non spezzare valori con #)
            if " #" in _v:
                _v = _v.split(" #", 1)[0]
            os.environ.setdefault(_k.strip(), _v.strip())

from app.models import (  # noqa: E402
    FeaturedSource,
    ReservedUsername,
    Source,
    Topic,
)


async def load_reserved_words(session: AsyncSession, file_path: Path) -> int:
    """Carica `reserved_usernames` da file di testo (una parola per riga).

    Il file può legittimamente avere lo stesso termine in sezioni diverse
    (es. una parola "system" che è anche un brand). Facciamo dedup in
    memoria prima dell'INSERT — vince l'ultima sezione in cui appare.
    """
    if not file_path.exists():
        print(f"  [skip] {file_path} non esiste", file=sys.stderr)
        return 0

    seen: dict[str, str] = {}  # word → reason (ultima vince)
    current_reason = "system"
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            lower = line.lower()
            if "profanity" in lower or "slur" in lower:
                current_reason = "profanity"
            elif "brand" in lower or "copyright" in lower:
                current_reason = "brand"
            elif "sistema" in lower or "rotte" in lower or "system" in lower:
                current_reason = "system"
            continue
        seen[line.lower()] = current_reason

    if not seen:
        return 0

    stmt = pg_insert(ReservedUsername).values(
        [{"word": w, "reason": r} for w, r in seen.items()]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["word"], set_={"reason": stmt.excluded.reason}
    )
    await session.execute(stmt)
    return len(seen)


async def load_topics(session: AsyncSession, file_path: Path) -> int:
    """Carica `topics` da YAML."""
    if not file_path.exists():
        print(f"  [skip] {file_path} non esiste", file=sys.stderr)
        return 0

    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not raw:
        return 0

    by_slug: dict[str, dict[str, Any]] = {}
    for item in raw:
        external_refs: dict[str, Any] = {}
        if "wikidata" in item and item["wikidata"]:
            external_refs["wikidata"] = item["wikidata"]
        by_slug[item["slug"]] = {
            "type": item["type"],
            "slug": item["slug"],
            "display_name": item["display_name"],
            "aliases": item.get("aliases") or [],
            "description": item.get("description"),
            "external_refs": external_refs or None,
            "is_curated": True,
        }
    rows = list(by_slug.values())

    stmt = pg_insert(Topic).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "type": stmt.excluded.type,
            "display_name": stmt.excluded.display_name,
            "aliases": stmt.excluded.aliases,
            "description": stmt.excluded.description,
            "external_refs": stmt.excluded.external_refs,
            "is_curated": stmt.excluded.is_curated,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def load_featured_sources(session: AsyncSession, file_path: Path) -> int:
    """Carica `sources` (se assenti) + `featured_sources` da YAML.

    Se la fonte non esiste, viene creata con `status='pending'` e
    `kind` dedotto (rss se url_feed, wordpress_api se wp_api_root,
    invalid altrimenti). Sarà la pipeline discovery a confermare
    o correggere lo stato.
    """
    if not file_path.exists():
        print(f"  [skip] {file_path} non esiste", file=sys.stderr)
        return 0

    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not raw:
        return 0

    count = 0
    for item in raw:
        url_feed = item.get("url_feed")
        wp_api_root = item.get("wp_api_root")
        kind = "rss" if url_feed else ("wordpress_api" if wp_api_root else "invalid")

        # Trova fonte esistente (per url_feed o wp_api_root)
        existing = None
        if url_feed:
            existing = (
                await session.execute(select(Source).where(Source.url_feed == url_feed))
            ).scalar_one_or_none()
        if not existing and wp_api_root:
            existing = (
                await session.execute(
                    select(Source).where(Source.wp_api_root == wp_api_root)
                )
            ).scalar_one_or_none()

        if existing:
            source_id = existing.id
        else:
            new = Source(
                kind=kind,
                url_site=item.get("url_site"),
                url_feed=url_feed,
                wp_api_root=wp_api_root,
                title=item.get("display_name"),
                status="pending",
            )
            session.add(new)
            await session.flush()
            source_id = new.id

        # Upsert featured_sources
        fs_stmt = pg_insert(FeaturedSource).values(
            source_id=source_id,
            category_hint=item.get("category_hint"),
            display_name=item.get("display_name"),
            description=item.get("description"),
            position=item.get("position", 0),
        )
        fs_stmt = fs_stmt.on_conflict_do_update(
            index_elements=["source_id"],
            set_={
                "category_hint": fs_stmt.excluded.category_hint,
                "display_name": fs_stmt.excluded.display_name,
                "description": fs_stmt.excluded.description,
                "position": fs_stmt.excluded.position,
            },
        )
        await session.execute(fs_stmt)
        count += 1

    return count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed loader YOUFEED")
    parser.add_argument("--reserved-words", type=Path, default=None)
    parser.add_argument("--topics", type=Path, default=None)
    parser.add_argument("--featured", type=Path, default=None)
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Errore: DATABASE_URL non trovata", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        if args.reserved_words:
            n = await load_reserved_words(session, args.reserved_words)
            print(f"  reserved_usernames upserted: {n}")
        if args.topics:
            n = await load_topics(session, args.topics)
            print(f"  topics upserted: {n}")
        if args.featured:
            n = await load_featured_sources(session, args.featured)
            print(f"  featured_sources upserted: {n}")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
