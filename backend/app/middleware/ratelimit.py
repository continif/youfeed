"""Rate limit middleware con Redis (sliding window via INCR + EXPIRE).

Limiti tiered:
  - utente loggato (cookie sessione presente): RATE_LIMIT_USER_PER_MIN
  - anonimo: RATE_LIMIT_ANON_PER_MIN

Chiave: yf:rl:{tier}:{ip o session_id}:{minute_bucket}
TTL: 60s (allineato al bucket).

Esenzioni:
  - /yf_health, /yf_version (probe esterni)
  - file statici (gestiti da Apache, non arrivano qui in prod)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.config import get_settings
from app.redis_client import get_redis

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


EXEMPT_PATHS = frozenset({"/yf_health", "/yf_version"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit per IP (anonimo) o session_id (loggato)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        settings = get_settings()
        redis = get_redis()

        # Identifica il chiamante: cookie sessione → user tier; altrimenti IP → anon tier
        session_id = request.cookies.get(settings.session_cookie_name)
        if session_id:
            tier = "user"
            identifier = session_id
            limit = settings.rate_limit_user_per_min
        else:
            tier = "anon"
            ip = getattr(request.state, "client_ip", None) or "unknown"
            identifier = ip
            limit = settings.rate_limit_anon_per_min

        bucket = int(time.time() // 60)
        key = f"yf:rl:{tier}:{identifier}:{bucket}"

        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 65)  # un po' più del bucket per evitare race
        except Exception:
            # Se Redis non risponde non blocchiamo l'utente — fail-open.
            return await call_next(request)

        if count > limit:
            retry_after = 60 - int(time.time()) % 60
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Troppe richieste, riprova tra poco.",
                        "details": {"limit": limit, "tier": tier},
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        # Esponi header informativi (utile in debug, opzionale togliere in prod)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        response.headers["X-RateLimit-Tier"] = tier
        return response
