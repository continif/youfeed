"""Cache in-memory delle blacklist (country / ASN / IP / User-Agent).

TTL fisso 60s + invalidazione esplicita (`invalidate()`) chiamata dai router
admin dopo add/remove. Thread-safe via lock asyncio (in pratica chiamata
solo dall'event loop di Uvicorn).

Gli IP con `expires_at` in passato non entrano nella cache, così non c'è
bisogno di filtrarli ad ogni request.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy import or_, select

from app.models import BlockedAsn, BlockedCountry, BlockedIp, BlockedUserAgent


_TTL_SECONDS = 60.0

_lock = asyncio.Lock()
_countries: frozenset[str] = frozenset()
_asns: frozenset[int] = frozenset()
_ips: frozenset[str] = frozenset()
# UA: tutti lowercase per evitare di rilowercaseare ad ogni request.
_ua_patterns: tuple[str, ...] = ()
_loaded_at: float = 0.0


async def _refresh(session_factory) -> None:
    global _countries, _asns, _ips, _ua_patterns, _loaded_at
    now = datetime.now(UTC)
    async with session_factory() as session:
        countries = (
            await session.execute(select(BlockedCountry.iso_code))
        ).scalars().all()
        asns = (await session.execute(select(BlockedAsn.asn))).scalars().all()
        ips = (
            await session.execute(
                select(BlockedIp.ip).where(
                    or_(BlockedIp.expires_at.is_(None), BlockedIp.expires_at > now)
                )
            )
        ).scalars().all()
        uas = (
            await session.execute(select(BlockedUserAgent.pattern))
        ).scalars().all()
    _countries = frozenset(c.upper() for c in countries if c)
    _asns = frozenset(int(a) for a in asns)
    _ips = frozenset(ip for ip in ips if ip)
    _ua_patterns = tuple(p.lower() for p in uas if p)
    _loaded_at = time.monotonic()


async def get_blocked(
    session_factory,
) -> tuple[frozenset[str], frozenset[int], frozenset[str], tuple[str, ...]]:
    """Ritorna `(countries, asns, ips, ua_patterns_lower)`. Reload se TTL scaduto."""
    if time.monotonic() - _loaded_at > _TTL_SECONDS:
        async with _lock:
            if time.monotonic() - _loaded_at > _TTL_SECONDS:
                await _refresh(session_factory)
    return _countries, _asns, _ips, _ua_patterns


async def invalidate(session_factory) -> None:
    """Forza ricarica immediata (chiamare dopo add/remove in admin)."""
    async with _lock:
        await _refresh(session_factory)
