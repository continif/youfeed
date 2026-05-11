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


def _fix_mojibake(s: str) -> str:
    """Risolve UTF-8 letto come Windows-1252 (es. 'ForlÃ¬' → 'Forlì').
    Idempotente: se la stringa è già UTF-8 pulito, ritorna invariata."""
    if not s:
        return s
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


async def load_provinces_csv(session: AsyncSession, file_path: Path) -> int:
    """Carica le province italiane come `topics` con type='location' curated.

    Il CSV (vedi `infra/seed/raw/province-italiane.csv`) può contenere
    mojibake da copia-incolla; lo correggiamo in fase di parsing. Solo la
    colonna `Provincia` è usata per il `display_name`; il `slug` è derivato
    via `slugify`.
    """
    if not file_path.exists():
        print(f"  [skip] {file_path} non esiste", file=sys.stderr)
        return 0

    import csv

    from app.utils.slugify import slugify

    rows: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    with file_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            name_raw = (raw_row.get("Provincia") or "").strip()
            if not name_raw:
                continue
            display_name = _fix_mojibake(name_raw)
            slug = slugify(display_name)
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            rows.append(
                {
                    "type": "location",
                    "slug": slug,
                    "display_name": display_name,
                    "aliases": [],
                    "description": "Provincia italiana",
                    "external_refs": None,
                    "is_curated": True,
                }
            )

    if not rows:
        return 0

    stmt = pg_insert(Topic).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "type": stmt.excluded.type,
            "display_name": stmt.excluded.display_name,
            "description": stmt.excluded.description,
            "is_curated": stmt.excluded.is_curated,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def load_municipalities_csv(
    session: AsyncSession,
    file_path: Path,
    *,
    encoding: str = "utf-8",
) -> int:
    """Carica i comuni italiani come `topics` con type='location' curated.

    CSV ISTAT a 27+ colonne, separatore `;`. Indici colonne usati:
      5  Denominazione (Italiana e straniera)   es. "Aldino/Aldein"
      6  Denominazione in italiano              es. "Aldino"
      10 Denominazione Regione
      11 Denominazione provincia/città metropolitana
      14 Sigla automobilistica                  es. "BZ"

    Encoding: il file ISTAT originale è CP1252; supportiamo anche UTF-8.

    Strategia anti-collisione slug: alcuni nomi sono duplicati (es. "Castro"
    in BG e LE). Se il nome compare > 1 volta:
      - slug = "{base}-{sigla_lower}"   es. castro-bg, castro-le
      - display_name = "{nome} ({SIGLA})"   es. "Castro (BG)"
    Altrimenti slug = base.

    Aliases: nome bilingue se presente (es. "Aldein" come alias di "Aldino").
    """
    if not file_path.exists():
        print(f"  [skip] {file_path} non esiste", file=sys.stderr)
        return 0

    import csv
    from collections import Counter

    from app.utils.slugify import slugify

    raw_rows: list[dict[str, str]] = []
    with file_path.open(encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header_seen = False
        for cols in reader:
            if not cols or len(cols) < 15:
                continue
            # Salta header (riconosciuto da "Codice Regione" come prima cella,
            # eventualmente seguito dal continuum dell'header su righe seguenti
            # se sono presenti newline embedded nei nomi colonne quotati).
            if not header_seen:
                if cols[0].strip().lower().startswith("codice"):
                    header_seen = True
                    continue
                # se la prima riga non è header, processiamo subito
                header_seen = True
            name_full = (cols[5] or "").strip()
            name_it = (cols[6] or "").strip()
            regione = (cols[10] or "").strip()
            provincia = (cols[11] or "").strip()
            sigla = (cols[14] or "").strip().upper()
            if not name_it or not sigla:
                continue
            raw_rows.append(
                {
                    "name": name_it,
                    "name_full": name_full,
                    "regione": regione,
                    "provincia": provincia,
                    "sigla": sigla,
                }
            )

    if not raw_rows:
        return 0

    name_counts: Counter[str] = Counter(r["name"] for r in raw_rows)

    seen_slugs: set[str] = set()
    rows: list[dict[str, Any]] = []
    for r in raw_rows:
        base = slugify(r["name"])
        if not base:
            continue
        if name_counts[r["name"]] > 1:
            slug = f"{base}-{r['sigla'].lower()}"
            display_name = f"{r['name']} ({r['sigla']})"
        else:
            slug = base
            display_name = r["name"]
        # paranoia: collisione residua → suffisso progressivo
        if slug in seen_slugs:
            i = 2
            while f"{slug}-{i}" in seen_slugs:
                i += 1
            slug = f"{slug}-{i}"
        seen_slugs.add(slug)

        aliases: list[str] = []
        # Nome bilingue: "Aldino/Aldein" → alias "Aldein"
        if "/" in r["name_full"]:
            for part in r["name_full"].split("/"):
                p = part.strip()
                if p and p != r["name"] and p not in aliases:
                    aliases.append(p)

        rows.append(
            {
                "type": "location",
                "slug": slug,
                "display_name": display_name,
                "aliases": aliases,
                "description": f"Comune italiano ({r['provincia']}, {r['regione']})",
                "external_refs": None,
                "is_curated": True,
            }
        )

    # Insert a chunk per evitare statement giganti (Postgres regge ma
    # l'EXPLAIN diventa illeggibile se debugghi).
    chunk = 500
    total = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        stmt = pg_insert(Topic).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_={
                "type": stmt.excluded.type,
                "display_name": stmt.excluded.display_name,
                "aliases": stmt.excluded.aliases,
                "description": stmt.excluded.description,
                "is_curated": stmt.excluded.is_curated,
            },
        )
        await session.execute(stmt)
        total += len(batch)
    return total


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed loader YOUFEED")
    parser.add_argument("--reserved-words", type=Path, default=None)
    parser.add_argument("--topics", type=Path, default=None)
    parser.add_argument("--featured", type=Path, default=None)
    parser.add_argument(
        "--provinces",
        type=Path,
        default=None,
        help="CSV province italiane → topics(type=location, is_curated)",
    )
    parser.add_argument(
        "--municipalities",
        type=Path,
        default=None,
        help="CSV comuni italiani (ISTAT) → topics(type=location, is_curated)",
    )
    parser.add_argument(
        "--municipalities-encoding",
        default="utf-8",
        help="Encoding CSV comuni: 'utf-8' (default) o 'cp1252' per file ISTAT originale",
    )
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
        if args.provinces:
            n = await load_provinces_csv(session, args.provinces)
            print(f"  provinces (location topics) upserted: {n}")
        if args.municipalities:
            n = await load_municipalities_csv(
                session,
                args.municipalities,
                encoding=args.municipalities_encoding,
            )
            print(f"  municipalities (location topics) upserted: {n}")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
