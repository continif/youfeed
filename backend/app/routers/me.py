"""Endpoint profilo utente loggato (/yf_me)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, status

from app.auth_deps import CurrentUser
from app.deps import DB
from app.schemas.auth import ChangePasswordIn, MessageOut, UserOut
from app.services import auth_service

log = structlog.get_logger()

router = APIRouter(prefix="/yf_me", tags=["me"])


@router.get("", response_model=UserOut)
async def get_me(user: CurrentUser) -> UserOut:
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
