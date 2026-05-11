"""Endpoint POST /yf_track: eventi client (impression, click, dwell, scroll).

Anonimi e autenticati possono entrambi tracciare eventi. Il payload viene
serializzato JSON e accodato sulla stessa Redis list usata dal middleware
HTTP, che il worker `activity_log` drena in batch.

Niente DB direttamente qui: l'endpoint deve restare leggerissimo (P95 < 5ms).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request, status

from app.auth_deps import CurrentUserOptional
from app.middleware.activity_log import ACTIVITY_QUEUE_KEY
from app.redis_client import get_redis
from app.schemas.articles import TrackEventIn

log = structlog.get_logger()

router = APIRouter(prefix="/yf_track", tags=["track"])

ALLOWED_EVENT_TYPES = frozenset(
    {"impression", "click", "open", "dwell", "scroll", "search", "share"}
)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def track_event(
    payload: TrackEventIn,
    request: Request,
    user: CurrentUserOptional,
) -> None:
    if payload.event_type not in ALLOWED_EVENT_TYPES:
        # Restiamo silenti su eventi sconosciuti (no 4xx — compatibilità futura)
        return

    redis = get_redis()
    event: dict[str, Any] = {
        "user_id": int(user.id) if user is not None else None,
        "session_id": request.cookies.get("yf_session"),
        "fingerprint": request.headers.get("X-YF-Fingerprint"),
        "event_type": payload.event_type,
        "route": str(request.url.path),
        "method": "TRACK",
        "target_type": payload.target_type,
        "target_id": payload.target_id,
        "metadata": payload.metadata,
        "ip": getattr(request.state, "client_ip", None),
        "country": getattr(request.state, "country", None),
        "asn": getattr(request.state, "asn", None),
        "ua": request.headers.get("User-Agent"),
        "status": None,
        "latency_ms": None,
        "ts": datetime.now(UTC).isoformat(),
    }

    try:
        await redis.lpush(ACTIVITY_QUEUE_KEY, json.dumps(event, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("yf.track.enqueue_failed", error=str(e))
    return None
