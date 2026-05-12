"""Endpoint profilo utente loggato (/yf_me)."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.auth_deps import CurrentSession, CurrentUser
from app.config import get_settings
from app.deps import DB
from app.exceptions import NotFoundError
from app.models import AuthSession
from app.schemas.auth import (
    ChangePasswordIn,
    DeviceOut,
    MePatchIn,
    MessageOut,
    UserOut,
)
from app.schemas.alerts import (
    AlertCreateIn,
    AlertOut,
    AlertTopicOut,
    AlertUpdateIn,
)
from app.schemas.bookmarks import BookmarkAddIn, BookmarkIdsOut, BookmarkOut
from app.schemas.notifications import NotificationCountOut, NotificationOut
from app.services import (
    account_service,
    alert_service,
    articles_service,
    auth_service,
    bookmark_service,
    notification_service,
)

log = structlog.get_logger()

router = APIRouter(prefix="/yf_me", tags=["me"])


@router.get("", response_model=UserOut)
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("", response_model=UserOut)
async def patch_me(payload: MePatchIn, user: CurrentUser, db: DB) -> UserOut:
    """Patch parziale dell'utente loggato. Per ora supporta solo
    `onboarding_completed`."""
    if payload.onboarding_completed is not None:
        await account_service.set_onboarding_completed(
            db, user=user, completed=payload.onboarding_completed
        )
    await db.commit()
    await db.refresh(user)
    log.info(
        "yf.me.patch", user_id=user.id, onboarding=user.onboarding_completed_at is not None
    )
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=MessageOut, status_code=status.HTTP_200_OK)
async def change_password(payload: ChangePasswordIn, user: CurrentUser, db: DB) -> MessageOut:
    try:
        await auth_service.change_password(
            db, user, current=payload.current_password, new=payload.new_password
        )
    except auth_service.ValidationError as e:
        from app.exceptions import AppError

        raise AppError(e.message, code=e.code, status_code=422) from e

    await db.commit()
    log.info("yf.me.change_password", user_id=user.id)
    return MessageOut(message="Password aggiornata.")


@router.get("/export", status_code=status.HTTP_200_OK)
async def export_my_data(user: CurrentUser, db: DB) -> StreamingResponse:
    """GDPR Art. 20: scarica un ZIP con i dati dell'utente."""
    archive = await account_service.build_export_archive(db, user=user)
    log.info("yf.me.export", user_id=user.id, bytes=len(archive))
    filename = f"youfeed-export-{user.username}.zip"
    return StreamingResponse(
        iter([archive]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Device management (Phase 1.1.C)
# ---------------------------------------------------------------------------


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(user: CurrentUser, current: CurrentSession, db: DB) -> list[DeviceOut]:
    """Lista delle sessioni attive dell'utente, ordinate per last_seen_at DESC.

    La sessione corrente è marcata con `current=True`.
    """
    res = await db.execute(
        select(AuthSession)
        .where(AuthSession.user_id == user.id)
        .where(AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_seen_at.desc())
    )
    rows = res.scalars().all()
    out: list[DeviceOut] = []
    for s in rows:
        out.append(
            DeviceOut(
                id=str(s.id),
                client=s.client,
                ip=str(s.ip) if s.ip is not None else None,
                country=s.country,
                ua=s.ua,
                created_at=s.created_at,
                last_seen_at=s.last_seen_at,
                current=(s.id == current.id),
            )
        )
    return out


@router.delete("/devices/{device_id}", response_model=MessageOut)
async def revoke_device(
    user: CurrentUser,
    current: CurrentSession,
    db: DB,
    device_id: str = Path(min_length=8, max_length=64),
) -> MessageOut:
    """Revoca una sessione. Non si può revocare la sessione corrente da qui
    (per evitare confusione: il logout esplicito è in /yf_auth/logout)."""
    try:
        sid = uuid.UUID(device_id)
    except ValueError as e:
        raise NotFoundError("Dispositivo non trovato.", code="device_not_found") from e

    if sid == current.id:
        from app.exceptions import AppError

        raise AppError(
            "Per disconnettere il dispositivo corrente usa il pulsante 'Esci'.",
            code="cannot_revoke_current",
            status_code=400,
        )

    res = await db.execute(
        select(AuthSession).where(AuthSession.id == sid).where(AuthSession.user_id == user.id)
    )
    sess = res.scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        raise NotFoundError("Dispositivo non trovato.", code="device_not_found")

    await auth_service.revoke_session(db, sid)
    await db.commit()
    log.info("yf.me.device_revoked", user_id=user.id, session_id=str(sid))
    return MessageOut(message="Dispositivo disconnesso.")


# ---------------------------------------------------------------------------
# Notifiche in-app (Phase 1.1.E)
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: CurrentUser,
    db: DB,
    only_unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationOut]:
    rows = await notification_service.list_for_user(
        db, user_id=int(user.id), only_unread=only_unread, limit=limit, offset=offset
    )
    return [NotificationOut.model_validate(n) for n in rows]


@router.get("/notifications/unread-count", response_model=NotificationCountOut)
async def notifications_unread_count(
    user: CurrentUser, db: DB
) -> NotificationCountOut:
    n = await notification_service.count_unread(db, user_id=int(user.id))
    return NotificationCountOut(unread=n)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
async def notification_mark_read(
    user: CurrentUser, db: DB, notification_id: int = Path(ge=1)
) -> NotificationOut:
    notif = await notification_service.mark_read(
        db, notification_id=notification_id, user_id=int(user.id)
    )
    if notif is None:
        raise NotFoundError("Notifica non trovata.", code="notification_not_found")
    await db.commit()
    return NotificationOut.model_validate(notif)


@router.post("/notifications/mark-all-read", response_model=NotificationCountOut)
async def notifications_mark_all_read(
    user: CurrentUser, db: DB
) -> NotificationCountOut:
    marked = await notification_service.mark_all_read(db, user_id=int(user.id))
    await db.commit()
    log.info("yf.notifications.mark_all_read", user_id=user.id, marked=marked)
    return NotificationCountOut(unread=0)


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def notification_delete(
    user: CurrentUser, db: DB, notification_id: int = Path(ge=1)
) -> Response:
    deleted = await notification_service.delete_notification(
        db, notification_id=notification_id, user_id=int(user.id)
    )
    await db.commit()
    if not deleted:
        raise NotFoundError("Notifica non trovata.", code="notification_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/clear-read", response_model=MessageOut)
async def notifications_clear_read(user: CurrentUser, db: DB) -> MessageOut:
    """Elimina tutte le notifiche già lette dell'utente."""
    n = await notification_service.delete_all_read(db, user_id=int(user.id))
    await db.commit()
    log.info("yf.notifications.clear_read", user_id=user.id, deleted=n)
    return MessageOut(message=f"{n} notifiche eliminate.")


# ---------------------------------------------------------------------------
# Alerts (Phase 1.2.D)
# ---------------------------------------------------------------------------


def _alert_to_out(alert) -> AlertOut:
    return AlertOut(
        id=int(alert.id),
        is_enabled=bool(alert.is_enabled),
        channels=list(alert.channels or []),
        match_mode=alert.match_mode,  # type: ignore[arg-type]
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        topics=[
            AlertTopicOut(
                id=int(t.id),
                slug=t.slug,
                display_name=t.display_name,
                type=t.type,
            )
            for t in (alert.topics or [])
        ],
    )


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts_endpoint(user: CurrentUser, db: DB) -> list[AlertOut]:
    rows = await alert_service.list_alerts(db, user_id=int(user.id))
    return [_alert_to_out(a) for a in rows]


@router.post("/alerts", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert_endpoint(
    payload: AlertCreateIn, user: CurrentUser, db: DB
) -> AlertOut:
    alert = await alert_service.create_alert(
        db,
        user_id=int(user.id),
        topic_ids=payload.topic_ids,
        channels=payload.channels,
        match_mode=payload.match_mode,
    )
    await db.commit()
    log.info(
        "yf.me.alert_created",
        user_id=user.id,
        alert_id=alert.id,
        n_topics=len(alert.topics or []),
        match_mode=alert.match_mode,
    )
    return _alert_to_out(alert)


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert_endpoint(
    payload: AlertUpdateIn,
    user: CurrentUser,
    db: DB,
    alert_id: int = Path(ge=1),
) -> AlertOut:
    alert = await alert_service.update_alert(
        db,
        user_id=int(user.id),
        alert_id=alert_id,
        is_enabled=payload.is_enabled,
        channels=payload.channels,
        topic_ids=payload.topic_ids,
        match_mode=payload.match_mode,
    )
    await db.commit()
    return _alert_to_out(alert)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_endpoint(
    user: CurrentUser, db: DB, alert_id: int = Path(ge=1)
) -> Response:
    deleted = await alert_service.delete_alert(
        db, user_id=int(user.id), alert_id=alert_id
    )
    await db.commit()
    if not deleted:
        raise NotFoundError("Alert non trovato.", code="alert_not_found")
    log.info("yf.me.alert_deleted", user_id=user.id, alert_id=alert_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Bookmark (saved articles)
# ---------------------------------------------------------------------------


@router.get("/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(
    user: CurrentUser,
    db: DB,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[BookmarkOut]:
    rows = await bookmark_service.list_for_user(
        db, user_id=int(user.id), limit=limit, offset=offset
    )
    return [
        BookmarkOut(
            article=articles_service.to_list_item(row),  # type: ignore[arg-type]
            created_at=created_at,
        )
        for row, created_at in rows
    ]


@router.post("/bookmarks", response_model=BookmarkOut, status_code=status.HTTP_201_CREATED)
async def add_bookmark(
    payload: BookmarkAddIn, user: CurrentUser, db: DB
) -> BookmarkOut:
    await bookmark_service.add(
        db, user_id=int(user.id), article_id=payload.article_id
    )
    await db.commit()
    rows = await bookmark_service.list_for_user(
        db, user_id=int(user.id), limit=1, offset=0
    )
    # Filtra al bookmark appena creato (può non essere il primo se l'utente
    # ne aveva già di più recenti, ma quello che ci interessa è restituire
    # la card serializzata dell'articolo target).
    for row, created_at in rows:
        if int(row.article.id) == payload.article_id:
            return BookmarkOut(
                article=articles_service.to_list_item(row),  # type: ignore[arg-type]
                created_at=created_at,
            )
    raise NotFoundError("Articolo non trovato.", code="article_not_found")


@router.delete("/bookmarks/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(
    user: CurrentUser, db: DB, article_id: int = Path(ge=1)
) -> Response:
    removed = await bookmark_service.remove(
        db, user_id=int(user.id), article_id=article_id
    )
    await db.commit()
    if not removed:
        raise NotFoundError("Bookmark non trovato.", code="bookmark_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bookmarks/check", response_model=BookmarkIdsOut)
async def check_bookmarks(
    payload: dict, user: CurrentUser, db: DB
) -> BookmarkIdsOut:
    """Bulk check: dato un set di article_id, ritorna quelli bookmarked."""
    raw_ids = payload.get("ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    ids = [int(x) for x in raw_ids if isinstance(x, int) or str(x).isdigit()]
    bookmarked = await bookmark_service.ids_for_user(
        db, user_id=int(user.id), article_ids=ids
    )
    return BookmarkIdsOut(ids=sorted(bookmarked))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(user: CurrentUser, db: DB, request: Request) -> Response:
    """Elimina l'account dell'utente loggato. Cascade su categorie/sources/sessioni;
    anonimizza l'activity_log (user_id=NULL)."""
    user_id = int(user.id)
    await account_service.delete_user_cascade(db, user_id=user_id)
    await db.commit()

    settings = get_settings()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    # Revoca subito il cookie sessione (lato client)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain or None,
    )
    log.info("yf.me.deleted", user_id=user_id)
    _ = request  # parametri richiesti per coerenza, evita "unused" lint
    return response
