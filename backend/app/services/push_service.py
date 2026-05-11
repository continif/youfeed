"""Servizio Web Push (Phase 1.2.E).

Gestisce la registrazione delle PushSubscription e l'invio dei payload
via pywebpush. Le chiavi VAPID vivono in `.env` (private PEM con \\n
escapati nelle env var, public b64url).

API:
- `register_subscription(db, user_id, endpoint, p256dh, auth, ua)` —
  idempotente: ON CONFLICT su `endpoint` aggiorna user/keys/last_seen.
- `delete_subscription(db, user_id, sub_id)` — soltanto subs dell'utente.
- `list_subscriptions(db, user_id)` — per /yf_me/push/subscriptions.
- `send_to_user(db, user_id, payload)` — fetch subs, invia, drop 404/410.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PushSubscription


log = structlog.get_logger()


@dataclass(slots=True)
class PushSendResult:
    sent: int = 0
    dropped: int = 0  # 404/410 → subscription rimossa
    failed: int = 0   # altri errori (retry futuri possibili)


# ---------------------------------------------------------------------------
# Settings unpack
# ---------------------------------------------------------------------------


def _vapid_private_pem() -> str | None:
    """Recupera la PEM dalla env var, sblocca i \\n escapati."""
    raw = get_settings().vapid_private_key
    if not raw:
        return None
    # In .env le multi-line vengono salvate con \\n letterali
    return raw.replace("\\n", "\n")


def is_configured() -> bool:
    return bool(_vapid_private_pem()) and bool(get_settings().vapid_public_key)


def public_key() -> str:
    return get_settings().vapid_public_key


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def register_subscription(
    db: AsyncSession,
    *,
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    ua: str | None = None,
) -> PushSubscription:
    """Idempotente via UNIQUE(endpoint): se l'endpoint esiste lo aggiorna."""
    now = datetime.now(UTC)
    stmt = (
        pg_insert(PushSubscription)
        .values(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            ua=ua,
            last_seen_at=now,
        )
        .on_conflict_do_update(
            index_elements=["endpoint"],
            set_={
                "user_id": user_id,
                "p256dh": p256dh,
                "auth": auth,
                "ua": ua,
                "last_seen_at": now,
            },
        )
        .returning(PushSubscription)
    )
    res = await db.execute(stmt)
    return res.scalar_one()


async def delete_subscription(
    db: AsyncSession, *, user_id: int, sub_id: int
) -> bool:
    res = await db.execute(
        delete(PushSubscription)
        .where(PushSubscription.id == sub_id)
        .where(PushSubscription.user_id == user_id)
        .returning(PushSubscription.id)
    )
    return res.scalar_one_or_none() is not None


async def delete_subscription_by_endpoint(
    db: AsyncSession, *, user_id: int, endpoint: str
) -> bool:
    res = await db.execute(
        delete(PushSubscription)
        .where(PushSubscription.endpoint == endpoint)
        .where(PushSubscription.user_id == user_id)
        .returning(PushSubscription.id)
    )
    return res.scalar_one_or_none() is not None


async def list_subscriptions(
    db: AsyncSession, *, user_id: int
) -> list[PushSubscription]:
    res = await db.execute(
        select(PushSubscription)
        .where(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.last_seen_at.desc())
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def _send_one(sub_info: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, int | None]:
    """Sync send via pywebpush. Ritorna (ok, status_code_se_errore).

    pywebpush è sync; chiamato in run_in_executor da `send_to_user`.
    """
    settings = get_settings()
    pem = _vapid_private_pem()
    if not pem:
        log.warning("yf.push.no_vapid_key")
        return False, None
    try:
        webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=pem,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=86400,
        )
        return True, 200
    except WebPushException as e:
        status_code = getattr(e.response, "status_code", None) if e.response is not None else None
        log.warning(
            "yf.push.send_failed",
            status_code=status_code,
            message=str(e)[:200],
        )
        return False, status_code
    except Exception as e:  # noqa: BLE001
        log.error("yf.push.send_error", error=str(e))
        return False, None


async def send_to_user(
    db: AsyncSession, *, user_id: int, payload: dict[str, Any]
) -> PushSendResult:
    """Invia payload a TUTTE le subscriptions dell'utente. Drop 404/410."""
    if not is_configured():
        log.debug("yf.push.skipped_unconfigured", user_id=user_id)
        return PushSendResult()

    import asyncio

    subs = await list_subscriptions(db, user_id=user_id)
    if not subs:
        return PushSendResult()

    result = PushSendResult()
    loop = asyncio.get_event_loop()
    to_drop: list[int] = []
    for sub in subs:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        ok, status_code = await loop.run_in_executor(None, _send_one, sub_info, payload)
        if ok:
            result.sent += 1
        elif status_code in (404, 410):
            # Subscription gone — pulizia
            to_drop.append(int(sub.id))
            result.dropped += 1
        else:
            result.failed += 1

    if to_drop:
        await db.execute(
            delete(PushSubscription).where(PushSubscription.id.in_(to_drop))
        )
        await db.commit()
        log.info("yf.push.dropped_subs", user_id=user_id, count=len(to_drop))

    # Aggiorna last_seen_at per le subs raggiunte
    if result.sent > 0:
        await db.execute(
            update(PushSubscription)
            .where(PushSubscription.user_id == user_id)
            .where(PushSubscription.id.notin_(to_drop) if to_drop else True)
            .values(last_seen_at=datetime.now(UTC))
        )
        await db.commit()

    log.info(
        "yf.push.send_complete",
        user_id=user_id,
        sent=result.sent,
        dropped=result.dropped,
        failed=result.failed,
    )
    return result
