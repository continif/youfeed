"""Unit test per il parser dei comuni italiani.

Verifica:
  - parsing colonne per indice (l'header ISTAT ha newline embedded e by-name è fragile)
  - anti-collisione slug per nomi duplicati (es. "Castro" in BG e LE)
  - alias dal nome bilingue ("Aldino/Aldein" → alias "Aldein")
  - encoding multipli (CP1252 originale ISTAT + UTF-8 convertito)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Topic
from app.utils.seed_loader import load_municipalities_csv


# Header ridotto (15 colonne: senza i codici ISTAT in coda) — il loader usa
# csv.reader by-index e legge cols[0..14], quindi righe più corte di 15
# vengono saltate.
HEADER = (
    "Codice Regione;Codice UTS;Codice Provincia;Progressivo;Codice Alfanum;"
    "Denominazione (IT/altro);Denominazione IT;Denominazione altra lingua;"
    "Codice Ripart;Ripartizione;Regione;Provincia;Tipologia;Capoluogo;Sigla"
)


def _make_csv_row(*, name_full: str, name_it: str, regione: str,
                  provincia: str, sigla: str, name_alt: str = "") -> str:
    """Costruisce una riga CSV ISTAT-like con le colonne che il loader usa."""
    return ";".join([
        "01", "001", "001", "001", "001001",
        name_full, name_it, name_alt,
        "1", "Nord", regione, provincia, "1", "0", sigla,
    ])


@pytest.mark.asyncio
async def test_municipalities_basic_parsing(db_session, tmp_path: Path) -> None:
    """Comuni con nomi univoci: slug = slugify(name), display_name = name."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="Roma", name_it="Roma", regione="Lazio",
                      provincia="Roma", sigla="RM"),
        _make_csv_row(name_full="Milano", name_it="Milano",
                      regione="Lombardia", provincia="Milano", sigla="MI"),
    ])
    f = tmp_path / "comuni.csv"
    f.write_text(csv_text, encoding="utf-8")

    n = await load_municipalities_csv(db_session, f, encoding="utf-8")
    assert n == 2

    roma = (await db_session.execute(
        select(Topic).where(Topic.slug == "roma")
    )).scalar_one()
    assert roma.type == "location"
    assert roma.display_name == "Roma"
    assert roma.is_curated is True


@pytest.mark.asyncio
async def test_municipalities_collision_disambiguation(
    db_session, tmp_path: Path
) -> None:
    """Nomi duplicati (es. Castro in BG e LE): slug suffissato con sigla,
    display_name con sigla in parentesi."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="Castro", name_it="Castro",
                      regione="Lombardia", provincia="Bergamo", sigla="BG"),
        _make_csv_row(name_full="Castro", name_it="Castro",
                      regione="Puglia", provincia="Lecce", sigla="LE"),
    ])
    f = tmp_path / "comuni.csv"
    f.write_text(csv_text, encoding="utf-8")

    n = await load_municipalities_csv(db_session, f, encoding="utf-8")
    assert n == 2

    rows = (await db_session.execute(
        select(Topic).where(Topic.slug.in_(["castro-bg", "castro-le"]))
        .order_by(Topic.slug)
    )).scalars().all()
    assert len(rows) == 2
    assert rows[0].slug == "castro-bg"
    assert rows[0].display_name == "Castro (BG)"
    assert rows[1].slug == "castro-le"
    assert rows[1].display_name == "Castro (LE)"

    # nessun "castro" senza suffisso
    plain = (await db_session.execute(
        select(Topic).where(Topic.slug == "castro")
    )).scalar_one_or_none()
    assert plain is None


@pytest.mark.asyncio
async def test_municipalities_bilingual_aliases(
    db_session, tmp_path: Path
) -> None:
    """Comuni Alto Adige bilingue: 'Aldino/Aldein' → display 'Aldino' +
    alias 'Aldein'."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="Aldino/Aldein", name_it="Aldino",
                      regione="Trentino-Alto Adige", provincia="Bolzano",
                      sigla="BZ", name_alt="Aldein"),
    ])
    f = tmp_path / "comuni.csv"
    f.write_text(csv_text, encoding="utf-8")

    n = await load_municipalities_csv(db_session, f, encoding="utf-8")
    assert n == 1

    aldino = (await db_session.execute(
        select(Topic).where(Topic.slug == "aldino")
    )).scalar_one()
    assert aldino.display_name == "Aldino"
    assert "Aldein" in (aldino.aliases or [])


@pytest.mark.asyncio
async def test_municipalities_skip_when_missing_critical_fields(
    db_session, tmp_path: Path
) -> None:
    """Righe senza nome o sigla vengono ignorate (non rompono il batch)."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="", name_it="", regione="X",
                      provincia="X", sigla="XX"),  # no name
        _make_csv_row(name_full="Foo", name_it="Foo", regione="Y",
                      provincia="Y", sigla=""),    # no sigla
        _make_csv_row(name_full="Bar", name_it="Bar", regione="Z",
                      provincia="Z", sigla="ZZ"),  # ok
    ])
    f = tmp_path / "comuni.csv"
    f.write_text(csv_text, encoding="utf-8")

    n = await load_municipalities_csv(db_session, f, encoding="utf-8")
    assert n == 1


@pytest.mark.asyncio
async def test_municipalities_cp1252_encoding(
    db_session, tmp_path: Path
) -> None:
    """Il file ISTAT originale è in CP1252 (Windows-1252). Il loader deve
    leggerlo correttamente quando passi encoding='cp1252'."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="Forlì", name_it="Forlì",
                      regione="Emilia-Romagna",
                      provincia="Forlì-Cesena", sigla="FC"),
    ])
    f = tmp_path / "comuni-cp1252.csv"
    # Scriviamo intenzionalmente in CP1252 — è quello che farebbe Windows
    # quando salvi il file ISTAT.
    f.write_bytes(csv_text.encode("cp1252"))

    n = await load_municipalities_csv(db_session, f, encoding="cp1252")
    assert n == 1
    forli = (await db_session.execute(
        select(Topic).where(Topic.slug == "forli")
    )).scalar_one()
    assert forli.display_name == "Forlì"


@pytest.mark.asyncio
async def test_municipalities_idempotent_upsert(
    db_session, tmp_path: Path
) -> None:
    """Riapplicare lo stesso CSV non duplica righe (ON CONFLICT DO UPDATE)."""
    csv_text = "\n".join([
        HEADER,
        _make_csv_row(name_full="Roma", name_it="Roma", regione="Lazio",
                      provincia="Roma", sigla="RM"),
    ])
    f = tmp_path / "comuni.csv"
    f.write_text(csv_text, encoding="utf-8")

    n1 = await load_municipalities_csv(db_session, f, encoding="utf-8")
    n2 = await load_municipalities_csv(db_session, f, encoding="utf-8")
    assert n1 == 1 and n2 == 1

    count = len((await db_session.execute(
        select(Topic).where(Topic.slug == "roma")
    )).scalars().all())
    assert count == 1
