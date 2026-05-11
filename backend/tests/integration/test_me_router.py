"""Integration test per `account_service.set_onboarding_completed`.

Testiamo direttamente il service (la logica HTTP del PATCH `/yf_me` è 4 righe
di binding). Per i test E2E sul router serve dependency override del DB,
postponed: il valore informativo qui è la corretta gestione di NOW()/NULL.
"""

from __future__ import annotations

import pytest

from app.services import account_service, auth_service

pytestmark = pytest.mark.integration


async def _make_user(db_session, *, username: str):
    user, token = await auth_service.register_user(
        db_session,
        username=username,
        email=f"{username}@example.com",
        password="..Strong12345..",
    )
    await auth_service.verify_email_token(db_session, token)
    await db_session.commit()
    return user


async def test_set_onboarding_completed_true_sets_timestamp(db_session) -> None:
    user = await _make_user(db_session, username="onboardyes")
    assert user.onboarding_completed_at is None

    await account_service.set_onboarding_completed(db_session, user=user, completed=True)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.onboarding_completed_at is not None


async def test_set_onboarding_completed_false_resets_to_null(db_session) -> None:
    user = await _make_user(db_session, username="onboardno")
    await account_service.set_onboarding_completed(db_session, user=user, completed=True)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.onboarding_completed_at is not None

    await account_service.set_onboarding_completed(db_session, user=user, completed=False)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.onboarding_completed_at is None
