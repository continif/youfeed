"""Integration test per app.services.auth_service (richiede Postgres)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.exceptions import ConflictError, UnauthorizedError
from app.models import EmailVerificationToken, User
from app.services import auth_service


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# register_user
# ---------------------------------------------------------------------------


async def test_register_creates_user_and_token(db_session) -> None:
    user, token = await auth_service.register_user(
        db_session,
        username="Pippo",
        email="pippo@example.com",
        password="..Pippo123Strong..",
    )
    await db_session.commit()

    assert user.id is not None
    assert user.username == "pippo"  # lowercased
    assert user.email == "pippo@example.com"
    assert user.email_verified is False
    assert user.password_hash and user.password_hash.startswith("$argon2")
    assert isinstance(token, str) and len(token) > 20

    # Token presente in DB e legato all'utente
    rec = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
    ).scalar_one()
    assert rec.user_id == user.id


async def test_register_duplicate_username_raises_conflict(db_session) -> None:
    await auth_service.register_user(
        db_session,
        username="dup",
        email="a@example.com",
        password="..Strong12345..",
    )
    await db_session.commit()

    with pytest.raises(ConflictError) as exc:
        await auth_service.register_user(
            db_session,
            username="DUP",
            email="b@example.com",
            password="..Strong12345..",
        )
    assert exc.value.code == "username_taken"


async def test_register_duplicate_email_raises_conflict(db_session) -> None:
    await auth_service.register_user(
        db_session,
        username="userone",
        email="same@example.com",
        password="..Strong12345..",
    )
    await db_session.commit()

    with pytest.raises(ConflictError) as exc:
        await auth_service.register_user(
            db_session,
            username="usertwo",
            email="SAME@example.com",
            password="..Strong12345..",
        )
    assert exc.value.code == "email_taken"


# ---------------------------------------------------------------------------
# verify_email_token
# ---------------------------------------------------------------------------


async def test_verify_email_token_flips_flag_and_consumes_token(db_session) -> None:
    user, token = await auth_service.register_user(
        db_session,
        username="vento",
        email="vento@example.com",
        password="..Strong12345..",
    )
    await db_session.commit()

    verified = await auth_service.verify_email_token(db_session, token)
    await db_session.commit()
    assert verified.email_verified is True

    # Il token deve essere stato consumato
    leftover = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
    ).scalar_one_or_none()
    assert leftover is None


# ---------------------------------------------------------------------------
# authenticate (login)
# ---------------------------------------------------------------------------


async def test_authenticate_rejects_unverified_user(db_session) -> None:
    await auth_service.register_user(
        db_session,
        username="nover",
        email="nover@example.com",
        password="..Strong12345..",
    )
    await db_session.commit()

    with pytest.raises(UnauthorizedError) as exc:
        await auth_service.authenticate(
            db_session,
            identifier="nover",
            password="..Strong12345..",
        )
    assert exc.value.code == "email_not_verified"


async def test_authenticate_rejects_wrong_password(db_session) -> None:
    user, token = await auth_service.register_user(
        db_session,
        username="wrong",
        email="wrong@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    await db_session.commit()

    with pytest.raises(UnauthorizedError) as exc:
        await auth_service.authenticate(
            db_session, identifier="wrong", password="..NotMyPwd99.."
        )
    assert exc.value.code == "invalid_credentials"


async def test_authenticate_returns_user_on_success(db_session) -> None:
    _, token = await auth_service.register_user(
        db_session,
        username="okuser",
        email="ok@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    await db_session.commit()

    user = await auth_service.authenticate(
        db_session, identifier="okuser", password="..Strong12345.."
    )
    assert user.email_verified is True


async def test_authenticate_works_with_email_identifier(db_session) -> None:
    _, token = await auth_service.register_user(
        db_session,
        username="byemail",
        email="byemail@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    await db_session.commit()

    user = await auth_service.authenticate(
        db_session,
        identifier="ByEmail@example.com",
        password="..Strong12345..",
    )
    assert user.username == "byemail"


# ---------------------------------------------------------------------------
# session lifecycle
# ---------------------------------------------------------------------------


async def test_create_and_load_session(db_session) -> None:
    _, token = await auth_service.register_user(
        db_session,
        username="sess",
        email="sess@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)

    user = (
        await db_session.execute(select(User).where(User.username == "sess"))
    ).scalar_one()

    auth = await auth_service.create_session(db_session, user=user, fingerprint="fp1")
    await db_session.commit()

    pair = await auth_service.load_active_session(db_session, auth.id)
    assert pair is not None
    loaded_session, loaded_user = pair
    assert loaded_session.id == auth.id
    assert loaded_user.id == user.id


async def test_revoked_session_is_not_loaded(db_session) -> None:
    _, token = await auth_service.register_user(
        db_session,
        username="rev",
        email="rev@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    user = (
        await db_session.execute(select(User).where(User.username == "rev"))
    ).scalar_one()
    auth = await auth_service.create_session(db_session, user=user, fingerprint=None)
    await auth_service.revoke_session(db_session, auth.id)
    await db_session.commit()

    pair = await auth_service.load_active_session(db_session, auth.id)
    assert pair is None
