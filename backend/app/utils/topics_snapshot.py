"""Snapshot Parquet dei `topics` curated.

Workflow:
  - **export**: serializza i topics curated (di un certo `--type` o tutti) in
    un file Parquet portabile. Pensato per dataset stabili e onerosi da
    rigenerare (province, comuni ISTAT con anti-collisione slug, brand
    confermati a mano, ...).
  - **import**: ricarica il Parquet via UPSERT su `slug`. Bootstrap del DB
    da zero in pochi secondi senza ripartire dai CSV grezzi.

CLI:
    # Export tutti i topics location (province + comuni)
    python -m app.utils.topics_snapshot export \\
        --type location --out ../data/locations.parquet

    # Import (idempotente)
    python -m app.utils.topics_snapshot import --in ../data/locations.parquet

Schema Parquet:
    type            string
    slug            string
    display_name    string
    aliases         list<string>
    description     string (nullable)
    external_refs   string (nullable, JSON-encoded — Parquet non ha JSONB)
    is_curated      bool
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from pathlib import Path as _P
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Carica .env come fa seed_loader (utility CLI standalone, no config dependency)
_env_file = _P(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if " #" in _v:
                _v = _v.split(" #", 1)[0]
            os.environ.setdefault(_k.strip(), _v.strip())

from app.models import Topic  # noqa: E402


SCHEMA = pa.schema(
    [
        pa.field("type", pa.string(), nullable=False),
        pa.field("slug", pa.string(), nullable=False),
        pa.field("display_name", pa.string(), nullable=False),
        pa.field("aliases", pa.list_(pa.string()), nullable=False),
        pa.field("description", pa.string(), nullable=True),
        pa.field("external_refs", pa.string(), nullable=True),
        pa.field("is_curated", pa.bool_(), nullable=False),
    ]
)


async def export_topics(
    session: AsyncSession,
    out_path: Path,
    *,
    topic_type: str | None = None,
    only_curated: bool = True,
) -> int:
    """Esporta topics in Parquet. Ritorna numero righe scritte."""
    stmt = select(Topic)
    if topic_type:
        stmt = stmt.where(Topic.type == topic_type)
    if only_curated:
        stmt = stmt.where(Topic.is_curated.is_(True))
    stmt = stmt.order_by(Topic.type, Topic.slug)

    rows = (await session.execute(stmt)).scalars().all()

    types: list[str] = []
    slugs: list[str] = []
    display_names: list[str] = []
    aliases: list[list[str]] = []
    descriptions: list[str | None] = []
    external_refs: list[str | None] = []
    is_curated: list[bool] = []
    for t in rows:
        types.append(t.type)
        slugs.append(t.slug)
        display_names.append(t.display_name)
        aliases.append(list(t.aliases or []))
        descriptions.append(t.description)
        external_refs.append(
            json.dumps(t.external_refs, ensure_ascii=False, sort_keys=True)
            if t.external_refs
            else None
        )
        is_curated.append(bool(t.is_curated))

    table = pa.table(
        {
            "type": types,
            "slug": slugs,
            "display_name": display_names,
            "aliases": aliases,
            "description": descriptions,
            "external_refs": external_refs,
            "is_curated": is_curated,
        },
        schema=SCHEMA,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # compression=zstd: ratio migliore di snappy su stringhe ripetitive
    # (es. description "Comune italiano (...)" ripetuta migliaia di volte).
    pq.write_table(table, out_path, compression="zstd", compression_level=9)
    return table.num_rows


async def import_topics(session: AsyncSession, in_path: Path) -> int:
    """Importa topics da Parquet via UPSERT su slug. Idempotente."""
    if not in_path.exists():
        print(f"  [skip] {in_path} non esiste", file=sys.stderr)
        return 0

    table = pq.read_table(in_path)
    # Validazione minima dello schema: campi indispensabili presenti.
    # Non confrontiamo l'intero schema per non rompere il restore in caso
    # di file vecchio con qualche colonna in più/meno opzionale.
    required = {"type", "slug", "display_name", "aliases", "is_curated"}
    missing = required - set(table.column_names)
    if missing:
        raise ValueError(f"Parquet snapshot manca colonne: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    pylist = table.to_pylist()
    for r in pylist:
        ext = r.get("external_refs")
        rows.append(
            {
                "type": r["type"],
                "slug": r["slug"],
                "display_name": r["display_name"],
                "aliases": r.get("aliases") or [],
                "description": r.get("description"),
                "external_refs": json.loads(ext) if ext else None,
                "is_curated": r.get("is_curated", True),
            }
        )

    if not rows:
        return 0

    # Insert a chunk per evitare statement giganti (vedi seed_loader).
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
                "external_refs": stmt.excluded.external_refs,
                "is_curated": stmt.excluded.is_curated,
            },
        )
        await session.execute(stmt)
        total += len(batch)
    return total


async def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot Parquet topics")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="DB → Parquet")
    p_export.add_argument("--out", type=Path, required=True)
    p_export.add_argument(
        "--type",
        dest="topic_type",
        default=None,
        help="Filtra per Topic.type (es. 'location', 'brand', ...). Default: tutti.",
    )
    p_export.add_argument(
        "--include-uncurated",
        action="store_true",
        help="Esporta anche topics non-curated (default: solo curated).",
    )

    p_import = sub.add_parser("import", help="Parquet → DB (UPSERT)")
    p_import.add_argument("--in", dest="in_path", type=Path, required=True)

    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Errore: DATABASE_URL non trovata", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        if args.cmd == "export":
            n = await export_topics(
                session,
                args.out,
                topic_type=args.topic_type,
                only_curated=not args.include_uncurated,
            )
            size = args.out.stat().st_size if args.out.exists() else 0
            print(f"  exported: {n} rows → {args.out} ({size:,} bytes)")
        else:
            n = await import_topics(session, args.in_path)
            print(f"  imported (upsert): {n} rows")
            await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
