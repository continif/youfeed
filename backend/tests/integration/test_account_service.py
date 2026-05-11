"""Integration test per app.services.account_service (export + delete cascade)."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import select

from app.models import (
    ActivityLog,
    AuthSession,
    Category,
    EmailVerificationToken,
    Source,
    User,
    UserSource,
)
from app.services import account_service, auth_service

pytestmark = pytest.mark.integration


async def _setup_user_with_data(db_session) -> tuple[User, dict]:
    """Crea utente verificato + 1 categoria + 1 user_source + 1 sessione."""
    user, token = await auth_service.register_user(
        db_session,
        username="datafull",
        email="datafull@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    await db_session.flush()

    cat = Category(
        user_id=user.id, name="News", slug="news", is_public=True, position=0
    )
    db_session.add(cat)
    await db_session.flush()

    src = Source(
        kind="rss",
        url_feed="https://x.com/feed.xml",
        title="Source X",
        status="active",
    )
    db_session.add(src)
    await db_session.flush()

    us = UserSource(user_id=user.id, source_id=src.id, category_id=cat.id)
    db_session.add(us)

    auth_sess = await auth_service.create_session(
        db_session, user=user, fingerprint="fp1", ip="1.2.3.4", ua="Mozilla/5.0"
    )

    await db_session.commit()
    return user, {"category_id": int(cat.id), "user_source_id": int(us.id), "session_id": auth_sess.id}


# ---------------------------------------------------------------------------
# build_export_archive
# ---------------------------------------------------------------------------


async def test_export_archive_contains_all_files(db_session) -> None:
    user, _ = await _setup_user_with_data(db_session)

    blob = await account_service.build_export_archive(db_session, user=user)
    assert blob[:2] == b"PK"  # magic number ZIP

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert {"user.json", "categories.json", "sources.json", "sessions.json", "README.txt"} <= names

        user_json = json.loads(zf.read("user.json").decode("utf-8"))
        assert user_json["username"] == "datafull"
        assert user_json["email"] == "datafull@example.com"
        # Niente password!
        assert "password" not in user_json
        assert "password_hash" not in user_json

        cats = json.loads(zf.read("categories.json").decode("utf-8"))
        assert len(cats) == 1
        assert cats[0]["name"] == "News"

        srcs = json.loads(zf.read("sources.json").decode("utf-8"))
        assert len(srcs) == 1
        assert srcs[0]["source"]["url_feed"] == "https://x.com/feed.xml"

        sessions = json.loads(zf.read("sessions.json").decode("utf-8"))
        assert len(sessions) == 1
        assert sessions[0]["ua"] == "Mozilla/5.0"


# ---------------------------------------------------------------------------
# delete_user_cascade
# ---------------------------------------------------------------------------


async def test_delete_user_cascade_removes_user_and_relateds(db_session) -> None:
    user, ids = await _setup_user_with_data(db_session)
    user_id = int(user.id)

    await account_service.delete_user_cascade(db_session, user_id=user_id)
    await db_session.commit()

    # User scomparso
    assert (await db_session.get(User, user_id)) is None

    # Categories cascade
    rows = (
        await db_session.execute(select(Category).where(Category.user_id == user_id))
    ).scalars().all()
    assert rows == []

    # UserSources cascade
    us_rows = (
        await db_session.execute(select(UserSource).where(UserSource.user_id == user_id))
    ).scalars().all()
    assert us_rows == []

    # Auth sessions cascade
    sess_rows = (
        await db_session.execute(select(AuthSession).where(AuthSession.user_id == user_id))
    ).scalars().all()
    assert sess_rows == []

    # Email verification tokens
    tok_rows = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
    ).scalars().all()
    assert tok_rows == []


async def test_delete_user_keeps_global_source(db_session) -> None:
    """Le sources sono globali: il delete utente NON le cancella."""
    user, _ = await _setup_user_with_data(db_session)
    src_id = (
        await db_session.execute(select(Source.id).where(Source.url_feed == "https://x.com/feed.xml"))
    ).scalar_one()

    await account_service.delete_user_cascade(db_session, user_id=int(user.id))
    await db_session.commit()

    src = await db_session.get(Source, src_id)
    assert src is not None  # globale, non eliminata


async def test_delete_user_anonymizes_activity_log(db_session) -> None:
    """Le righe activity_log dell'utente vengono anonimizzate (user_id=NULL)."""
    from datetime import UTC, datetime

    user, _ = await _setup_user_with_data(db_session)
    user_id = int(user.id)

    # Inserisci alcune righe activity_log per quell'utente
    db_session.add_all(
        [
            ActivityLog(
                user_id=user_id,
                event_type="http_request",
                route="/yf_me",
                method="GET",
                ts=datetime.now(UTC),
                fingerprint="fp1",
                ip="1.2.3.4",
                ua="Mozilla/5.0",
            ),
            ActivityLog(
                user_id=user_id,
                event_type="click",
                target_type="article",
                target_id="42",
                ts=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    # Pre-condizione: 2 righe legate all'utente
    pre = (
        await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == user_id))
    ).scalars().all()
    assert len(pre) == 2

    await account_service.delete_user_cascade(db_session, user_id=user_id)
    await db_session.commit()

    # Post: 0 righe legate, ma le righe esistono ancora con user_id=NULL e fingerprint/ip/ua puliti
    post = (
        await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == user_id))
    ).scalars().all()
    assert post == []

    anonymized = (
        await db_session.execute(
            select(ActivityLog).where(
                (ActivityLog.user_id.is_(None))
                & (ActivityLog.event_type.in_(("http_request", "click")))
            )
        )
    ).scalars().all()
    assert len(anonymized) >= 2
    for r in anonymized:
        assert r.fingerprint is None
        assert r.ua is None
        assert r.ip is None


# ---------------------------------------------------------------------------
# count_user_data
# ---------------------------------------------------------------------------


async def test_count_user_data(db_session) -> None:
    user, _ = await _setup_user_with_data(db_session)
    counts = await account_service.count_user_data(db_session, user_id=int(user.id))
    assert counts == {"categories": 1, "user_sources": 1, "sessions": 1}
