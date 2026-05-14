"""Cache in-memory delle liste `blocked_countries` / `blocked_asns`.

TTL fisso 60s + invalidazione esplicita (`invalidate()`) chiamata dai router
admin dopo add/remove. Thread-safe via lock asyncio (in pratica chiamata
solo dall'event loop di Uvicorn).
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlockedAsn, BlockedCountry


_TTL_SECONDS = 60.0

_lock = asyncio.Lock()
_countries: frozenset[str] = frozenset()
_asns: frozenset[int] = frozenset()
_loaded_at: float = 0.0


async def _refresh(session_factory) -> None:
    global _countries, _asns, _loaded_at
    async with session_factory() as session:
        countries = (await session.execute(select(BlockedCountry.iso_code))).scalars().all()
        asns = (await session.execute(select(BlockedAsn.asn))).scalars().all()
    _countries = frozenset(c.upper() for c in countries if c)
    _asns = frozenset(int(a) for a in asns)
    _loaded_at = time.monotonic()


async def get_blocked(session_factory) -> tuple[frozenset[str], frozenset[int]]:
    """Ritorna `(countries, asns)`. Reload se TTL scaduto."""
    if time.monotonic() - _loaded_at > _TTL_SECONDS:
        async with _lock:
            if time.monotonic() - _loaded_at > _TTL_SECONDS:
                await _refresh(session_factory)
    return _countries, _asns


async def invalidate(session_factory) -> None:
    """Forza ricarica immediata (chiamare dopo add/remove in admin)."""
    async with _lock:
        await _refresh(session_factory)
