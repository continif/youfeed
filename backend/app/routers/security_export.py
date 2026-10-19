"""Export della blocklist IP per consumer esterni (firewall, fail2ban, ...).

`GET /yf_data/security/blocked-ips.txt` — un IP per riga, solo gli IP
bannati nelle ultime 24 ore e ancora attivi (permanenti o con scadenza futura).

Auth: `Authorization: Bearer <SECURITY_EXPORT_TOKEN>` (token in `.env`,
sola lettura, ruotabile senza toccare le credenziali admin). Senza token
configurato l'endpoint risponde sempre 401 (export disabilitato).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import DB
from app.models.security import BlockedIp

router = APIRouter(prefix="/yf_data/security", tags=["security-export"])

EXPORT_WINDOW = timedelta(hours=24)


def _check_token(authorization: str | None) -> None:
    expected = get_settings().security_export_token
    scheme, _, supplied = (authorization or "").partition(" ")
    if (
        not expected
        or scheme.lower() != "bearer"
        or not secrets.compare_digest(supplied.strip().encode(), expected.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def recent_blocked_ips(
    session: AsyncSession, *, now: datetime | None = None
) -> list[str]:
    """IP bannati nelle ultime 24h e ancora attivi, ordinati per IP."""
    now = now or datetime.now(UTC)
    res = await session.execute(
        select(BlockedIp.ip)
        .where(BlockedIp.created_at >= now - EXPORT_WINDOW)
        .where(or_(BlockedIp.expires_at.is_(None), BlockedIp.expires_at > now))
        .order_by(BlockedIp.ip)
    )
    return [r[0] for r in res.all()]


@router.get("/blocked-ips.txt", response_class=PlainTextResponse)
async def blocked_ips_txt(
    db: DB, authorization: str | None = Header(default=None)
) -> PlainTextResponse:
    _check_token(authorization)
    ips = await recent_blocked_ips(db)
    return PlainTextResponse(
        "".join(f"{ip}\n" for ip in ips),
        headers={"Cache-Control": "no-store"},
    )
