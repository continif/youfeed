"""Endpoint auth v1.0.

Endpoints:
  POST /yf_auth/register
  GET  /yf_auth/verify-email
  POST /yf_auth/resend-verification
  GET  /yf_auth/username-available
  POST /yf_auth/login
  POST /yf_auth/logout
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from app.auth_deps import CurrentSession
from app.config import get_settings
from app.deps import DB
from app.exceptions import UnauthorizedError
from app.models import User
from app.schemas.auth import (
    LoginIn,
    MessageOut,
    RegisterIn,
    ResendVerificationIn,
    UsernameAvailableOut,
)
from app.services import auth_service
from app.workers.email import enqueue_verification

log = structlog.get_logger()

router = APIRouter(prefix="/yf_auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=60 * 60 * 24 * settings.session_lifetime_days,
        domain=settings.session_cookie_domain or None,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain or None,
        path="/",
    )


# ---------------------------------------------------------------------------
# Registrazione
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageOut,
)
async def register(payload: RegisterIn, db: DB) -> MessageOut:
    try:
        user, token = await auth_service.register_user(
            db,
            username=payload.username,
            email=str(payload.email),
            password=payload.password,
        )
    except auth_service.ValidationError as e:
        # Trasformiamo l'errore di validazione semantica in 422
        from app.exceptions import AppError

        raise AppError(e.message, code=e.code, status_code=422) from e

    await db.commit()

    enqueue_verification(to=user.email, username=user.username, token=token)
    log.info("yf.auth.register", user_id=user.id, username=user.username)

    return MessageOut(message="Registrazione effettuata. Controlla l'email per verificare l'account.")


# ---------------------------------------------------------------------------
# Verifica email
# ---------------------------------------------------------------------------


@router.get("/verify-email", response_model=MessageOut)
async def verify_email(token: str = Query(min_length=8, max_length=128), db: DB = ...) -> MessageOut:
    user = await auth_service.verify_email_token(db, token)
    await db.commit()
    log.info("yf.auth.email_verified", user_id=user.id)
    return MessageOut(message="Email verificata. Ora puoi accedere.")


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(payload: ResendVerificationIn, db: DB) -> MessageOut:
    res = await db.execute(select(User).where(User.email == str(payload.email).lower()))
    user = res.scalar_one_or_none()
    # Risposta volutamente identica per email esistenti e non — antiscan
    if user is None or user.email_verified:
        return MessageOut(message="Se l'email esiste, una nuova verifica è stata inviata.")

    token = await auth_service.issue_new_verification_token(db, user)
    await db.commit()
    enqueue_verification(to=user.email, username=user.username, token=token)
    log.info("yf.auth.resend_verification", user_id=user.id)
    return MessageOut(message="Se l'email esiste, una nuova verifica è stata inviata.")


# ---------------------------------------------------------------------------
# Username availability
# ---------------------------------------------------------------------------


@router.get("/username-available", response_model=UsernameAvailableOut)
async def username_available(u: str = Query(min_length=3, max_length=30), db: DB = ...) -> UsernameAvailableOut:
    available = await auth_service.is_username_available(db, u)
    return UsernameAvailableOut(available=available)


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@router.post("/login", response_model=MessageOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: DB,
) -> MessageOut:
    user = await auth_service.authenticate(
        db, identifier=payload.identifier, password=payload.password
    )

    fingerprint = request.headers.get("X-YF-Fingerprint")
    auth_session = await auth_service.create_session(
        db,
        user=user,
        fingerprint=fingerprint,
        client=request.headers.get("X-YF-Client", "web"),
        ip=getattr(request.state, "client_ip", None),
        country=getattr(request.state, "country", None),
        asn=getattr(request.state, "asn", None),
        ua=request.headers.get("User-Agent"),
    )
    await db.commit()

    _set_session_cookie(response, str(auth_session.id))
    log.info("yf.auth.login", user_id=user.id, session_id=str(auth_session.id))
    return MessageOut(message="Accesso effettuato.")


@router.post("/logout", response_model=MessageOut)
async def logout(
    request: Request,
    response: Response,
    db: DB,
) -> MessageOut:
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        try:
            import uuid

            sid = uuid.UUID(cookie)
            await auth_service.revoke_session(db, sid)
            await db.commit()
        except ValueError:
            pass
        except Exception:  # noqa: BLE001
            await db.rollback()

    _clear_session_cookie(response)
    return MessageOut(message="Disconnesso.")


# ---------------------------------------------------------------------------
# Sessione corrente — endpoint di prova (verrà spostato in /yf_me più avanti)
# ---------------------------------------------------------------------------


@router.get("/_session", response_model=MessageOut)
async def session_probe(_session: CurrentSession) -> MessageOut:
    """Endpoint di debug: verifica che il cookie sessione sia valido. 401 se no."""
    return MessageOut(message="Sessione attiva.")
