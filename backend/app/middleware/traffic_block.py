"""TrafficBlockMiddleware: 403 per country/ASN nella blocklist admin.

Si appoggia a:
  - `request.state.country` / `.asn` popolati da `GeoIPMiddleware`
  - cache delle liste in `app.security.block_cache` (TTL 60s)
  - log eventi su SQLite in `app.security.events_store`

Posizione nello stack: subito dopo GeoIP (registrazione: PRIMA di GeoIP
in main.py, così Geo è outermost e Block lo vede già popolato). Vedi
`.claude/SECURITY.md` per il flusso completo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp

from app.db import get_session_factory
from app.security import block_cache, events_store

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


log = structlog.get_logger()


class TrafficBlockMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        country = getattr(request.state, "country", None)
        asn = getattr(request.state, "asn", None)

        # Niente country/asn → niente blocco possibile (es. client locale,
        # IP non risolto, MaxMind DB mancante).
        if country is None and asn is None:
            return await call_next(request)

        countries, asns = await block_cache.get_blocked(get_session_factory())

        reason: str | None = None
        if country and country.upper() in countries:
            reason = "country"
        elif asn is not None and int(asn) in asns:
            reason = "asn"

        if reason is None:
            return await call_next(request)

        # Blocco: log + 403. Non blocchiamo /yf_admin per decisione esplicita
        # (vedi SECURITY.md → "Admin NON è esente").
        await events_store.record_block(
            ip=getattr(request.state, "client_ip", None),
            country=country,
            asn=int(asn) if asn is not None else None,
            method=request.method,
            path=request.url.path,
            user_agent=request.headers.get("User-Agent"),
            reason=reason,
        )
        log.info(
            "yf.security.blocked",
            ip=getattr(request.state, "client_ip", None),
            country=country,
            asn=asn,
            reason=reason,
            path=request.url.path,
        )
        return PlainTextResponse("Forbidden", status_code=403)
