"""Endpoint Web Push (Phase 1.2.E).

    GET    /yf_push/vapid-key              (anon, ritorna applicationServerKey)
    GET    /yf_me/push/subscriptions       (list)
    POST   /yf_me/push/subscriptions       (register dopo PushManager.subscribe)
    DELETE /yf_me/push/subscriptions/{id}  (unsubscribe lato server)
    POST   /yf_me/push/test                (invia una push di test alle proprie subs)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Path, Request, status
from fastapi.responses import Response

from app.auth_deps import CurrentUser
from app.deps import DB
from app.exceptions import NotFoundError
from app.schemas.auth import MessageOut
from app.schemas.push import (
    PushSubscriptionCreateIn,
    PushSubscriptionOut,
    VapidKeyOut,
)
from app.services import push_service


log = structlog.get_logger()


public_router = APIRouter(prefix="/yf_push", tags=["push"])
me_router = APIRouter(prefix="/yf_me/push", tags=["push", "me"])


# ---------------------------------------------------------------------------
# Public: VAPID key
# ---------------------------------------------------------------------------


@public_router.get("/vapid-key", response_model=VapidKeyOut)
async def vapid_key() -> VapidKeyOut:
    return VapidKeyOut(
        public_key=push_service.public_key() or "",
        configured=push_service.is_configured(),
    )


# ---------------------------------------------------------------------------
# /yf_me/push/subscriptions
# ---------------------------------------------------------------------------


@me_router.get("/subscriptions", response_model=list[PushSubscriptionOut])
async def list_subs(user: CurrentUser, db: DB) -> list[PushSubscriptionOut]:
    rows = await push_service.list_subscriptions(db, user_id=int(user.id))
    return [PushSubscriptionOut.model_validate(r) for r in rows]


@me_router.post(
    "/subscriptions",
    response_model=PushSubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_sub(
    payload: PushSubscriptionCreateIn,
    user: CurrentUser,
    db: DB,
    request: Request,
) -> PushSubscriptionOut:
    sub = await push_service.register_subscription(
        db,
        user_id=int(user.id),
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        ua=request.headers.get("User-Agent"),
    )
    await db.commit()
    log.info("yf.push.subscribed", user_id=user.id, sub_id=sub.id)
    return PushSubscriptionOut.model_validate(sub)


@me_router.delete("/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sub(
    user: CurrentUser, db: DB, sub_id: int = Path(ge=1)
) -> Response:
    ok = await push_service.delete_subscription(
        db, user_id=int(user.id), sub_id=sub_id
    )
    await db.commit()
    if not ok:
        raise NotFoundError("Subscription non trovata.", code="sub_not_found")
    log.info("yf.push.unsubscribed", user_id=user.id, sub_id=sub_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.post("/test", response_model=MessageOut)
async def test_push(user: CurrentUser, db: DB) -> MessageOut:
    """Invia una push di test a tutte le sub dell'utente. Utile per verificare
    la pipeline VAPID dopo la prima subscribe."""
    result = await push_service.send_to_user(
        db,
        user_id=int(user.id),
        payload={
            "title": "Test notifica YouFeed",
            "body": "Le notifiche push funzionano. Puoi disattivarle da Impostazioni.",
            "link": "/me/notifications",
        },
    )
    return MessageOut(
        message=f"Push inviata: sent={result.sent}, dropped={result.dropped}, failed={result.failed}"
    )
