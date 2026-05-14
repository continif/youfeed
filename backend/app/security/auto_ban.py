"""Auto-ban: insert un IP in `blocked_ips` con `expires_at = now + 24h`.

Chiamato dal TrafficBlockMiddleware quando una richiesta NON autenticata
hit un path-scanner (vedi `scanner_paths.py`). Se l'IP è già bannato
permanentemente (`expires_at IS NULL`), l'INSERT è no-op (ON CONFLICT
DO NOTHING). Se è bannato con scadenza più corta, estendi a 24h.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text

from app.security import block_cache


log = structlog.get_logger()


AUTO_BAN_DURATION = timedelta(hours=24)


async def auto_ban_ip(session_factory, ip: str, *, reason: str, path: str) -> None:
    """Banna `ip` per `AUTO_BAN_DURATION`. Idempotente.

    Comportamento del conflict:
      - Se l'IP è già bannato con `expires_at IS NULL` (permanente) → no-op
      - Se l'IP è già bannato a tempo, estendi `expires_at` solo se la
        nuova scadenza è più tardi della corrente
    Nota: `note` viene preservata sui ban esistenti.
    """
    expires = datetime.now(UTC) + AUTO_BAN_DURATION
    note = f"auto-ban: {reason} on {path[:120]}"
    # Postgres-flavored upsert nativo via raw text. Niente CONFLICT su
    # SQLAlchemy core perché vogliamo logica condizionale sul nuovo
    # expires_at (estendi solo se sarebbe più lontano).
    sql = text(
        """
        INSERT INTO blocked_ips (ip, note, expires_at, created_at)
        VALUES (:ip, :note, :expires_at, now())
        ON CONFLICT (ip) DO UPDATE
        SET expires_at = CASE
            WHEN blocked_ips.expires_at IS NULL THEN NULL
            WHEN EXCLUDED.expires_at > blocked_ips.expires_at THEN EXCLUDED.expires_at
            ELSE blocked_ips.expires_at
        END
        """
    )
    async with session_factory() as session:
        await session.execute(sql, {"ip": ip, "note": note, "expires_at": expires})
        await session.commit()

    # Invalidate cache così tutti i prossimi request di questo worker
    # vedono subito il nuovo ban (gli altri worker aggiornano al prossimo TTL).
    await block_cache.invalidate(session_factory)
    log.info(
        "yf.security.auto_banned",
        ip=ip,
        reason=reason,
        path=path,
        expires_at=expires.isoformat(),
    )
