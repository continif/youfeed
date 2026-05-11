"""Integration test per la generazione dinamica della sitemap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Article, Category, Source, User, UserSource
from app.services import seo_service

pytestmark = pytest.mark.integration


async def _user_with_public_category(
    db_session, *, username: str, public: bool, with_source: bool = True
) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="$argon2id$dummy",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    cat = Category(
        user_id=user.id, name="C", slug=f"c-{username}", is_public=public, position=0
    )
    db_session.add(cat)
    await db_session.flush()

    if with_source:
        src = Source(
            kind="rss",
            url_feed=f"https://x.com/{username}.xml",
            title="S",
            status="active",
        )
        db_session.add(src)
        await db_session.flush()
        db_session.add(
            UserSource(user_id=user.id, source_id=src.id, category_id=cat.id)
        )
        await db_session.flush()
    return user


async def test_collect_public_profile_entries_includes_only_public(db_session) -> None:
    pub = await _user_with_public_category(db_session, username="pubuser", public=True)
    await _user_with_public_category(db_session, username="privuser", public=False)
    await db_session.commit()

    entries = await seo_service.collect_public_profile_entries(
        db_session, base_url="https://www.youfeed.it"
    )
    locs = [e.loc for e in entries]
    assert "https://www.youfeed.it/pubuser" in locs
    assert "https://www.youfeed.it/privuser" not in locs

    # priority 0.8 + changefreq hourly per i profili
    pub_entry = next(e for e in entries if e.loc.endswith("/pubuser"))
    assert pub_entry.priority == 0.8
    assert pub_entry.changefreq == "hourly"
    # lastmod fallback su user.created_at quando l'utente non ha articoli
    assert pub_entry.lastmod is not None


async def test_collect_public_profile_uses_max_published_at_as_lastmod(db_session) -> None:
    user = await _user_with_public_category(db_session, username="rich", public=True)
    src_id = (
        await db_session.execute(
            (
                __import__("sqlalchemy").select(Source.id)
                .where(Source.url_feed == "https://x.com/rich.xml")
            )
        )
    ).scalar_one()

    # 2 articoli con published_at distanti
    older = datetime.now(UTC) - timedelta(days=3)
    newer = datetime.now(UTC) - timedelta(hours=2)
    db_session.add_all(
        [
            Article(
                source_id=src_id,
                kind="rss",
                url_canonical="https://x.com/rich/a1",
                url_hash="hash-rich-a1",
                published_at=older,
                processing_status="indexed",
            ),
            Article(
                source_id=src_id,
                kind="rss",
                url_canonical="https://x.com/rich/a2",
                url_hash="hash-rich-a2",
                published_at=newer,
                processing_status="indexed",
            ),
        ]
    )
    await db_session.commit()

    entries = await seo_service.collect_public_profile_entries(
        db_session, base_url="https://www.youfeed.it"
    )
    rich_entry = next(e for e in entries if e.loc.endswith("/rich"))
    # lastmod ≈ newer (con eventuale rounding microsec)
    delta = abs((rich_entry.lastmod - newer).total_seconds())
    assert delta < 1


async def test_collect_public_profile_skips_user_without_sources(db_session) -> None:
    """Utente con categoria pubblica ma senza user_sources NON deve apparire."""
    await _user_with_public_category(
        db_session, username="empty", public=True, with_source=False
    )
    await db_session.commit()

    entries = await seo_service.collect_public_profile_entries(
        db_session, base_url="https://www.youfeed.it"
    )
    assert all(not e.loc.endswith("/empty") for e in entries)
