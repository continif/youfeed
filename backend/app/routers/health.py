"""Health & version endpoint trasversali."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.deps import DB, RedisDep

router = APIRouter(tags=["system"])


@router.get("/yf_health", status_code=status.HTTP_200_OK)
async def health(db: DB, redis: RedisDep) -> dict[str, object]:
    """Healthcheck completo: API + Postgres + Redis.

    Manticore non è verificato qui (driver dedicato non ancora montato);
    sarà aggiunto in Phase 6 ingestion.
    """
    checks: dict[str, str] = {}
    ok = True

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["postgres"] = f"error: {e!s}"
        ok = False

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {e!s}"
        ok = False

    return {
        "status": "ok" if ok else "degraded",
        "checks": checks,
        "ts": datetime.now(UTC).isoformat(),
    }


@router.get("/yf_version")
async def version() -> dict[str, str]:
    settings = get_settings()
    return {"version": __version__, "env": settings.yf_env}
