"""Test integration per snapshot Parquet dei topics curated.

Verifica:
  - round-trip: DB → Parquet → DB equivale all'originale
  - filtro per type
  - filtro is_curated (esclude di default)
  - external_refs JSON-encoded sopravvive al round-trip
  - aliases (list[str]) sopravvive
  - import idempotente (UPSERT su slug)
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest
from sqlalchemy import select

from app.models import Topic
from app.utils.topics_snapshot import SCHEMA, export_topics, import_topics


@pytest.mark.asyncio
async def test_snapshot_roundtrip_preserves_all_fields(
    db_session, tmp_path: Path
) -> None:
    """Inserisco topic, esporto, cancello, reimporto: deve essere identico."""
    db_session.add(
        Topic(
            type="location",
            slug="roma",
            display_name="Roma",
            aliases=["Caput Mundi", "Urbe"],
            description="Capitale d'Italia",
            external_refs={"wikidata": "Q220"},
            is_curated=True,
        )
    )
    await db_session.flush()

    out = tmp_path / "snap.parquet"
    n = await export_topics(db_session, out, topic_type="location")
    assert n == 1
    assert out.exists() and out.stat().st_size > 0

    # cancella e reimporta
    await db_session.execute(
        Topic.__table__.delete().where(Topic.slug == "roma")
    )
    n2 = await import_topics(db_session, out)
    assert n2 == 1

    roma = (await db_session.execute(
        select(Topic).where(Topic.slug == "roma")
    )).scalar_one()
    assert roma.display_name == "Roma"
    assert roma.aliases == ["Caput Mundi", "Urbe"]
    assert roma.description == "Capitale d'Italia"
    assert roma.external_refs == {"wikidata": "Q220"}
    assert roma.is_curated is True


@pytest.mark.asyncio
async def test_snapshot_filters_by_type(
    db_session, tmp_path: Path
) -> None:
    db_session.add_all([
        Topic(type="location", slug="milano", display_name="Milano",
              aliases=[], is_curated=True),
        Topic(type="brand", slug="apple", display_name="Apple",
              aliases=[], is_curated=True),
    ])
    await db_session.flush()

    out = tmp_path / "loc.parquet"
    n = await export_topics(db_session, out, topic_type="location")
    assert n == 1

    table = pq.read_table(out)
    assert table.num_rows == 1
    assert table.column("type").to_pylist() == ["location"]


@pytest.mark.asyncio
async def test_snapshot_no_type_filter_exports_all_types(
    db_session, tmp_path: Path
) -> None:
    """Senza --type, l'export prende tutti i type (location, brand, person,
    subject, model). È il caso d'uso del backup completo."""
    db_session.add_all([
        Topic(type="location", slug="bologna", display_name="Bologna",
              aliases=[], is_curated=True),
        Topic(type="brand", slug="ferrari", display_name="Ferrari",
              aliases=[], is_curated=True),
        Topic(type="person", slug="dante-alighieri",
              display_name="Dante Alighieri", aliases=[], is_curated=True),
        Topic(type="subject", slug="cronaca", display_name="Cronaca",
              aliases=[], is_curated=True),
        Topic(type="model", slug="ferrari-f40", display_name="Ferrari F40",
              aliases=[], is_curated=True),
    ])
    await db_session.flush()

    out = tmp_path / "all.parquet"
    n = await export_topics(db_session, out, topic_type=None)
    assert n == 5

    table = pq.read_table(out)
    types_in_snapshot = set(table.column("type").to_pylist())
    assert types_in_snapshot == {"location", "brand", "person", "subject", "model"}


@pytest.mark.asyncio
async def test_snapshot_excludes_uncurated_by_default(
    db_session, tmp_path: Path
) -> None:
    db_session.add_all([
        Topic(type="location", slug="curated-loc", display_name="Curated",
              aliases=[], is_curated=True),
        Topic(type="location", slug="uncurated-loc", display_name="Uncurated",
              aliases=[], is_curated=False),
    ])
    await db_session.flush()

    out = tmp_path / "curated.parquet"
    n = await export_topics(db_session, out, topic_type="location",
                            only_curated=True)
    assert n == 1

    out_all = tmp_path / "all.parquet"
    n_all = await export_topics(db_session, out_all, topic_type="location",
                                only_curated=False)
    assert n_all == 2


@pytest.mark.asyncio
async def test_snapshot_import_is_idempotent(
    db_session, tmp_path: Path
) -> None:
    db_session.add(
        Topic(type="location", slug="napoli", display_name="Napoli",
              aliases=[], is_curated=True)
    )
    await db_session.flush()

    out = tmp_path / "snap.parquet"
    await export_topics(db_session, out, topic_type="location")

    # Reimporto due volte: nessuna duplicazione (UPSERT su slug).
    await import_topics(db_session, out)
    await import_topics(db_session, out)

    rows = (await db_session.execute(
        select(Topic).where(Topic.slug == "napoli")
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_snapshot_schema_matches_declared(
    db_session, tmp_path: Path
) -> None:
    """Il file Parquet scritto rispetta lo SCHEMA dichiarato (per portabilità
    cross-versione: una versione futura non deve cambiarlo silenziosamente)."""
    db_session.add(
        Topic(type="location", slug="firenze", display_name="Firenze",
              aliases=["Florence"], is_curated=True)
    )
    await db_session.flush()

    out = tmp_path / "snap.parquet"
    await export_topics(db_session, out, topic_type="location")

    table = pq.read_table(out)
    # Confronta i nomi colonna e i tipi top-level (PyArrow è strict
    # sull'equality dello schema, ma non dipendiamo da metadata triviale).
    assert set(table.schema.names) == set(SCHEMA.names)
    for name in SCHEMA.names:
        assert table.schema.field(name).type == SCHEMA.field(name).type, (
            f"Tipo colonna '{name}' divergente"
        )
