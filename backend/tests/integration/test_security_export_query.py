"""Query export blocklist: finestra 24h + ban ancora attivi."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.security import BlockedIp
from app.routers.security_export import recent_blocked_ips

pytestmark = pytest.mark.asyncio


async def test_recent_blocked_ips_window_and_expiry(db_session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            # recente + a tempo ancora attivo
            BlockedIp(ip="1.1.1.1", expires_at=now + timedelta(hours=5), created_at=now - timedelta(hours=1)),
            # recente + permanente
            BlockedIp(ip="2.2.2.2", expires_at=None, created_at=now - timedelta(hours=23)),
            # recente ma già scaduto
            BlockedIp(ip="3.3.3.3", expires_at=now - timedelta(minutes=1), created_at=now - timedelta(hours=2)),
            # attivo ma bannato oltre 24h fa
            BlockedIp(ip="4.4.4.4", expires_at=None, created_at=now - timedelta(hours=25)),
        ]
    )
    await db_session.flush()
    assert await recent_blocked_ips(db_session, now=now) == ["1.1.1.1", "2.2.2.2"]
