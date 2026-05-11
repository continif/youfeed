"""Integration test per app.services.ingestion_service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ingestion.feed_parser import ArticleCandidate, make_url_hash
from app.models import Article, Source
from app.services import ingestion_service

pytestmark = pytest.mark.integration


def _candidate(url: str, title: str = "Titolo X") -> ArticleCandidate:
    return ArticleCandidate(
        external_id=url,
        url_canonical=url,
        url_hash=make_url_hash(url),
        title=title,
        description="desc",
        content_html="<p>body</p>",
        author=None,
        published_at=datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC),
        updated_at=None,
        image_url=None,
    )


async def _make_source(db_session, **kwargs) -> Source:
    src = Source(
        kind=kwargs.get("kind", "rss"),
        url_feed=kwargs.get("url_feed", "https://example.com/feed.xml"),
        title="Source X",
        status=kwargs.get("status", "active"),
        poll_interval=kwargs.get("poll_interval", 1800),
        last_fetched_at=kwargs.get("last_fetched_at"),
        consecutive_failures=kwargs.get("consecutive_failures", 0),
    )
    db_session.add(src)
    await db_session.flush()
    return src


# ---------------------------------------------------------------------------
# ingest_candidates: ON CONFLICT DO NOTHING via url_hash
# ---------------------------------------------------------------------------


async def test_ingest_candidates_inserts_new_articles(db_session) -> None:
    src = await _make_source(db_session)
    cands = [_candidate("https://x.com/a"), _candidate("https://x.com/b")]
    inserted = await ingestion_service.ingest_candidates(
        db_session, source=src, candidates=cands
    )
    await db_session.commit()
    assert len(inserted) == 2

    rows = (await db_session.execute(select(Article))).scalars().all()
    assert len(rows) == 2


async def test_ingest_candidates_dedupes_on_url_hash(db_session) -> None:
    src = await _make_source(db_session)
    # Primo round: 2 articoli
    inserted_1 = await ingestion_service.ingest_candidates(
        db_session,
        source=src,
        candidates=[_candidate("https://x.com/a"), _candidate("https://x.com/b")],
    )
    await db_session.commit()
    assert len(inserted_1) == 2

    # Secondo round: 1 vecchio + 1 nuovo
    inserted_2 = await ingestion_service.ingest_candidates(
        db_session,
        source=src,
        candidates=[_candidate("https://x.com/a"), _candidate("https://x.com/c")],
    )
    await db_session.commit()
    assert len(inserted_2) == 1  # solo /c è nuovo

    total = (await db_session.execute(select(Article))).scalars().all()
    assert len(total) == 3


async def test_ingest_candidates_empty_list_returns_empty(db_session) -> None:
    src = await _make_source(db_session)
    out = await ingestion_service.ingest_candidates(
        db_session, source=src, candidates=[]
    )
    assert out == []


# ---------------------------------------------------------------------------
# mark_source_*
# ---------------------------------------------------------------------------


async def test_mark_source_success_resets_failures_and_promotes_pending(
    db_session,
) -> None:
    src = await _make_source(db_session, status="pending", consecutive_failures=3)
    await db_session.commit()

    await ingestion_service.mark_source_success(
        db_session, source=src, new_etag="W/abc", new_last_modified="Wed, 06 May 2026"
    )
    await db_session.commit()

    refreshed = await db_session.get(Source, src.id)
    assert refreshed is not None
    assert refreshed.status == "active"
    assert refreshed.consecutive_failures == 0
    assert refreshed.etag == "W/abc"
    assert refreshed.last_modified == "Wed, 06 May 2026"
    assert refreshed.last_success_at is not None


async def test_mark_source_failure_increments_counter(db_session) -> None:
    src = await _make_source(db_session, consecutive_failures=2)
    await db_session.commit()

    await ingestion_service.mark_source_failure(db_session, source=src, error="timeout")
    await db_session.commit()

    refreshed = await db_session.get(Source, src.id)
    assert refreshed is not None
    assert refreshed.consecutive_failures == 3
    assert refreshed.status == "active"  # < 5


async def test_mark_source_failure_marks_broken_after_5(db_session) -> None:
    src = await _make_source(db_session, consecutive_failures=4)
    await db_session.commit()

    await ingestion_service.mark_source_failure(db_session, source=src, error="x")
    await db_session.commit()

    refreshed = await db_session.get(Source, src.id)
    assert refreshed is not None
    assert refreshed.consecutive_failures == 5
    assert refreshed.status == "broken"


# ---------------------------------------------------------------------------
# select_due_sources
# ---------------------------------------------------------------------------


async def test_select_due_sources_returns_never_fetched(db_session) -> None:
    src = await _make_source(db_session, last_fetched_at=None)
    await db_session.commit()

    due = await ingestion_service.select_due_sources(db_session, limit=10)
    assert any(s.id == src.id for s in due)


async def test_select_due_sources_returns_old_enough(db_session) -> None:
    long_ago = datetime.now(UTC) - timedelta(seconds=3600)
    fresh = datetime.now(UTC) - timedelta(seconds=60)

    s_old = await _make_source(
        db_session,
        url_feed="https://x.com/old",
        last_fetched_at=long_ago,
        poll_interval=1800,
    )
    await _make_source(
        db_session,
        url_feed="https://x.com/fresh",
        last_fetched_at=fresh,
        poll_interval=1800,
    )
    await db_session.commit()

    due = await ingestion_service.select_due_sources(db_session, limit=10)
    due_ids = {s.id for s in due}
    assert s_old.id in due_ids
    # La source "fresh" è stata fetchata 60s fa con poll_interval=1800: NON due
    assert all(s.url_feed != "https://x.com/fresh" for s in due)


async def test_select_due_sources_respects_status_filter(db_session) -> None:
    s_broken = await _make_source(
        db_session, url_feed="https://x.com/broken", status="broken"
    )
    s_ok = await _make_source(db_session, url_feed="https://x.com/ok", status="active")
    await db_session.commit()

    due = await ingestion_service.select_due_sources(db_session, limit=10)
    ids = {s.id for s in due}
    assert s_ok.id in ids
    assert s_broken.id not in ids


# ---------------------------------------------------------------------------
# source_domain
# ---------------------------------------------------------------------------


def test_source_domain_uses_url_feed_first() -> None:
    src = Source(
        kind="rss",
        url_site="https://siteA.com",
        url_feed="https://siteB.com/feed.xml",
    )
    assert ingestion_service.source_domain(src) == "siteb.com"


def test_source_domain_falls_back_to_url_site() -> None:
    src = Source(kind="rss", url_site="https://siteA.com", url_feed=None)
    assert ingestion_service.source_domain(src) == "sitea.com"


def test_source_domain_returns_none_if_all_missing() -> None:
    src = Source(kind="invalid", url_site=None, url_feed=None, wp_api_root=None)
    assert ingestion_service.source_domain(src) is None
