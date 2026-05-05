"""Activity log middleware.

Per ogni richiesta accoda un evento JSON su lista Redis `yf:activity:queue`.
Un worker dedicato (vedi `app.workers.activity_log`) drena la lista in batch
e fa INSERT su `activity_log` (tabella partitioned daily).

Eventi taggati `event_type='http_request'`. Gli eventi client (impression,
click, dwell, scroll) arrivano dall'endpoint `POST /yf_track` e finiscono
sulla stessa coda con event_type diverso.

Esclusi:
  - probe sistema (/yf_health, /yf_version)
  - rotte statiche (Apache di solito non le inoltra, ma per sicurezza)
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.redis_client import get_redis

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


log = structlog.get_logger()

ACTIVITY_QUEUE_KEY = "yf:activity:queue"

EXEMPT_PATHS = frozenset({"/yf_health", "/yf_version", "/yf_openapi.json"})
EXEMPT_PREFIXES = ("/yf_docs", "/static/", "/assets/", "/images/", "/sw.js", "/favicon")


def _is_exempt(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class ActivityLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if _is_exempt(path):
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        settings = get_settings()
        redis = get_redis()

        session_id = request.cookies.get(settings.session_cookie_name)
        # user_id è popolato dal middleware/dependency auth quando arriverà.
        # Per ora resta None per anonimi e per chi ha solo il cookie.
        user_id: int | None = getattr(request.state, "user_id", None)

        event = {
            "user_id": user_id,
            "session_id": session_id,
            "fingerprint": request.headers.get("X-YF-Fingerprint"),
            "event_type": "http_request",
            "route": path,
            "method": request.method,
            "target_type": None,
            "target_id": None,
            "metadata": None,
            "ip": getattr(request.state, "client_ip", None),
            "country": getattr(request.state, "country", None),
            "asn": getattr(request.state, "asn", None),
            "ua": request.headers.get("User-Agent"),
            "status": response.status_code,
            "latency_ms": latency_ms,
            "ts": datetime.now(UTC).isoformat(),
        }

        try:
            await redis.lpush(ACTIVITY_QUEUE_KEY, json.dumps(event, default=str))
        except Exception as e:  # noqa: BLE001
            # Non bloccare la risposta se Redis non risponde; il log applicativo basta.
            log.warning("yf.activity_log.enqueue_failed", error=str(e))

        return response
