"""Integration test per app.topic_extractor.service (richiede Postgres)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Article, Entity, EntitySourceCount, Source, Topic
from app.topic_extractor import service

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_source(db_session, *, url_feed: str) -> Source:
    src = Source(kind="rss", url_feed=url_feed, title="S", status="active")
    db_session.add(src)
    await db_session.flush()
    return src


async def _make_article(
    db_session,
    *,
    source: Source,
    title: str,
    description: str,
    indexed: bool = True,
) -> Article:
    art = Article(
        source_id=source.id,
        kind="rss",
        url_canonical=f"https://x.com/{title[:20]}",
        url_hash=f"hash-{title}",
        published_at=datetime.now(UTC),
        processing_status="indexed" if indexed else "new",
        raw_meta_lite={"title": title, "description": description},
    )
    db_session.add(art)
    await db_session.flush()
    return art


# ---------------------------------------------------------------------------
# scan_articles
# ---------------------------------------------------------------------------


async def test_scan_extracts_persons_and_aggregates(db_session) -> None:
    src = await _make_source(db_session, url_feed="https://a.com/feed.xml")
    await _make_article(
        db_session,
        source=src,
        title="Donald J. Trump al G7",
        description="Il presidente Donald J. Trump è arrivato.",
    )
    await _make_article(
        db_session,
        source=src,
        title="JD Vance parla",
        description="Il senatore JD Vance ha votato sì.",
    )
    await db_session.commit()

    stats = await service.scan_articles(db_session)
    await db_session.commit()
    assert stats.articles_seen == 2

    surfaces = [
        e.surface_form
        for e in (await db_session.execute(select(Entity))).scalars().all()
    ]
    assert "Donald J. Trump" in surfaces
    assert "JD Vance" in surfaces


async def test_scan_increments_occurrence_count_across_articles(db_session) -> None:
    src = await _make_source(db_session, url_feed="https://b.com/feed.xml")
    for i in range(3):
        await _make_article(
            db_session,
            source=src,
            title=f"News {i}",
            description=f"Mario Rossi ha detto qualcosa nel giorno {i}.",
        )
    await db_session.commit()

    await service.scan_articles(db_session)
    await db_session.commit()

    e = (
        await db_session.execute(
            select(Entity).where(Entity.normalized == "mario rossi")
        )
    ).scalar_one()
    assert e.occurrence_count == 3
    assert e.ner_type == "REGEX_PER"


async def test_scan_populates_entity_source_counts(db_session) -> None:
    src1 = await _make_source(db_session, url_feed="https://s1.com/feed.xml")
    src2 = await _make_source(db_session, url_feed="https://s2.com/feed.xml")
    await _make_article(
        db_session, source=src1, title="X", description="Mario Rossi a Roma."
    )
    await _make_article(
        db_session, source=src2, title="Y", description="Mario Rossi parla ancora."
    )
    await _make_article(
        db_session, source=src2, title="Z", description="Anche Mario Rossi era lì."
    )
    await db_session.commit()

    await service.scan_articles(db_session)
    await db_session.commit()

    e = (
        await db_session.execute(
            select(Entity).where(Entity.normalized == "mario rossi")
        )
    ).scalar_one()
    rows = (
        await db_session.execute(
            select(EntitySourceCount).where(EntitySourceCount.entity_id == e.id)
        )
    ).scalars().all()
    counts = {int(r.source_id): r.count for r in rows}
    assert counts[int(src1.id)] == 1
    assert counts[int(src2.id)] == 2


async def test_scan_models_uses_known_brands(db_session) -> None:
    src = await _make_source(db_session, url_feed="https://c.com/feed.xml")
    await _make_article(
        db_session,
        source=src,
        title="Auto",
        description="La nuova Porsche 911 è arrivata.",
    )
    # Brand confermato: Porsche
    db_session.add(
        Topic(
            type="brand",
            slug="porsche",
            display_name="Porsche",
            aliases=[],
            is_curated=True,
        )
    )
    await db_session.commit()

    stats = await service.scan_articles(db_session, use_known_brands=True)
    await db_session.commit()
    assert stats.articles_seen == 1

    surfaces = [
        e.surface_form
        for e in (await db_session.execute(select(Entity))).scalars().all()
    ]
    # Pass-2 model con whitelist deve catturare "Porsche 911" come REGEX_MODEL
    assert "Porsche 911" in surfaces


# ---------------------------------------------------------------------------
# review_top
# ---------------------------------------------------------------------------


async def test_review_top_filters_by_min_count(db_session) -> None:
    """Solo entity con occurrence_count >= min_count sono mostrate."""
    src = await _make_source(db_session, url_feed="https://r.com/feed.xml")
    # Mario Rossi appare 6 volte (sopra soglia 5)
    for i in range(6):
        await _make_article(
            db_session, source=src, title=f"Mario Rossi {i}", description="."
        )
    # Luigi Verdi appare 2 volte (sotto soglia)
    for i in range(2):
        await _make_article(
            db_session, source=src, title=f"Luigi Verdi {i}", description="."
        )
    await db_session.commit()

    await service.scan_articles(db_session)
    await db_session.commit()

    items = await service.review_top(db_session, min_count=5, limit=10)
    surfaces = {it.surface_form for it in items}
    assert "Mario Rossi" in surfaces
    assert "Luigi Verdi" not in surfaces


async def test_review_top_subtoken_hint_when_part_is_known_topic(db_session) -> None:
    """Se 'Coca' è già un topic curato, 'Coca Cola' deve segnalarlo."""
    src = await _make_source(db_session, url_feed="https://h.com/feed.xml")
    # Coca Cola appare > min_count
    for i in range(5):
        await _make_article(
            db_session,
            source=src,
            title=f"Articolo {i}",
            description="La Coca Cola è popolare oggi.",
        )
    db_session.add(
        Topic(
            type="brand",
            slug="coca",
            display_name="Coca",
            aliases=[],
            is_curated=True,
        )
    )
    await db_session.commit()

    await service.scan_articles(db_session)
    await db_session.commit()

    items = await service.review_top(db_session, min_count=5, limit=10)
    coca_cola = next((i for i in items if i.surface_form == "Coca Cola"), None)
    assert coca_cola is not None
    assert ("coca", "brand") in coca_cola.subtoken_topics


# ---------------------------------------------------------------------------
# confirm + reject
# ---------------------------------------------------------------------------


async def test_confirm_creates_topic_and_links_entity(db_session) -> None:
    src = await _make_source(db_session, url_feed="https://k.com/feed.xml")
    for i in range(5):
        await _make_article(
            db_session,
            source=src,
            title=f"News {i}",
            description="Sergio Mattarella ha parlato oggi.",
        )
    await db_session.commit()

    await service.scan_articles(db_session)
    await db_session.commit()

    e = (
        await db_session.execute(
            select(Entity).where(Entity.normalized == "sergio mattarella")
        )
    ).scalar_one()
    assert e.topic_id is None

    topic = await service.confirm_entity(
        db_session, entity_id=int(e.id), as_type="person"
    )
    await db_session.commit()
    await db_session.refresh(e)

    assert topic.type == "person"
    assert topic.slug == "sergio-mattarella"
    assert topic.is_curated is True
    assert e.topic_id == topic.id


async def test_reject_sets_ignored_true(db_session) -> None:
    src = await _make_source(db_session, url_feed="https://j.com/feed.xml")
    await _make_article(
        db_session,
        source=src,
        title="Pippo Pluto nominato",
        description="Pippo Pluto è un nome inventato.",
    )
    await db_session.commit()
    await service.scan_articles(db_session)
    await db_session.commit()

    e = (
        await db_session.execute(
            select(Entity).where(Entity.normalized == "pippo pluto")
        )
    ).scalar_one()
    assert e.ignored is False

    await service.reject_entity(db_session, entity_id=int(e.id))
    await db_session.commit()
    await db_session.refresh(e)
    assert e.ignored is True


async def test_known_brand_names_from_curated_topics(db_session) -> None:
    db_session.add_all(
        [
            Topic(
                type="brand",
                slug="porsche",
                display_name="Porsche",
                aliases=["Porsche AG"],
                is_curated=True,
            ),
            Topic(
                type="brand",
                slug="not-curated-yet",
                display_name="Anonimo",
                aliases=[],
                is_curated=False,
            ),
            Topic(
                type="person",
                slug="mario-rossi",
                display_name="Mario Rossi",
                aliases=[],
                is_curated=True,
            ),
        ]
    )
    await db_session.commit()
    names = await service.known_brand_names(db_session)
    assert "Porsche" in names
    assert "Porsche AG" in names
    assert "Anonimo" not in names  # is_curated=False
    assert "Mario Rossi" not in names  # type=person
