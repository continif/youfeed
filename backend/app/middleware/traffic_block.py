"""TrafficBlockMiddleware: 403 per country/ASN/IP/UA + auto-ban scanner.

Layer di blocco a livello applicativo. Si appoggia a:
  - `request.state.country` / `.asn` / `.client_ip` popolati da `GeoIPMiddleware`
  - cache delle blacklist in `app.security.block_cache` (TTL 60s)
  - log eventi su SQLite in `app.security.events_store`

Ordine di valutazione (short-circuit alla prima):
  1. IP (Postgres `blocked_ips`, expires_at filtrato lato cache)
  2. User-Agent (substring case-insensitive su `blocked_user_agents`)
  3. Country (`blocked_countries`)
  4. ASN (`blocked_asns`)
  5. Scanner-path su request non-autenticata → auto-ban dell'IP per 24h
     (vedi `scanner_paths.py`). Skip se c'è il cookie `yf_session`.

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

from app.config import get_settings
from app.db import get_session_factory
from app.security import auto_ban, block_cache, events_store, scanner_paths

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


log = structlog.get_logger()


class TrafficBlockMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    @staticmethod
    def _matches_ua(ua_lower: str, patterns: tuple[str, ...]) -> str | None:
        """Ritorna il pattern matchato (primo) o None."""
        for p in patterns:
            if p and p in ua_lower:
                return p
        return None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_ip = getattr(request.state, "client_ip", None)
        country = getattr(request.state, "country", None)
        asn = getattr(request.state, "asn", None)
        ua_raw = request.headers.get("User-Agent") or ""
        path = request.url.path

        countries, asns, ips, ua_patterns = await block_cache.get_blocked(
            get_session_factory()
        )

        reason: str | None = None
        if client_ip and client_ip in ips:
            reason = "ip"
        elif ua_patterns and (matched := self._matches_ua(ua_raw.lower(), ua_patterns)):
            reason = f"ua:{matched[:40]}"
        elif country and country.upper() in countries:
            reason = "country"
        elif asn is not None and int(asn) in asns:
            reason = "asn"

        if reason is not None:
            await events_store.record_block(
                ip=client_ip,
                country=country,
                asn=int(asn) if asn is not None else None,
                method=request.method,
                path=path,
                user_agent=ua_raw or None,
                reason=reason,
            )
            log.info(
                "yf.security.blocked",
                ip=client_ip, country=country, asn=asn, reason=reason, path=path,
            )
            return PlainTextResponse("Forbidden", status_code=403)

        # Auto-ban scanner-path su request anonime. La heuristica è "ha il
        # cookie di sessione?" — proxy economico per "utente loggato" senza
        # toccare il DB nel hot path. Cookie stale verrà sloggato altrove,
        # non ci interessa la sicurezza qui (i bot scanner non hanno cookie).
        if client_ip and scanner_paths.is_scanner_path(path):
            settings = get_settings()
            has_session = bool(request.cookies.get(settings.session_cookie_name))
            if not has_session:
                await auto_ban.auto_ban_ip(
                    get_session_factory(),
                    client_ip,
                    reason="scanner-path",
                    path=path,
                )
                await events_store.record_block(
                    ip=client_ip,
                    country=country,
                    asn=int(asn) if asn is not None else None,
                    method=request.method,
                    path=path,
                    user_agent=ua_raw or None,
                    reason="scanner-path",
                )
                return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)
