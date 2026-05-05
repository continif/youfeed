"""Dependency FastAPI per ricavare l'utente corrente dalla sessione.

Due varianti:
  - `current_user_optional`: ritorna User|None (per endpoint che cambiano
    comportamento se loggato o no, es. home, search)
  - `current_user`: solleva 401 se non autenticato (per endpoint protetti)

La sessione può arrivare via:
  - cookie `yf_session` (web)
  - header `Authorization: Bearer <session_id_uuid>` (mobile, futuro)
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Request

from app.config import get_settings
from app.deps import DB
from app.exceptions import UnauthorizedError
from app.models import AuthSession, User
from app.services import auth_service

log = structlog.get_logger()


def _extract_session_id(request: Request) -> uuid.UUID | None:
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        try:
            return uuid.UUID(cookie)
        except ValueError:
            return None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            return uuid.UUID(token)
        except ValueError:
            return None

    return None


async def current_user_optional(request: Request, db: DB) -> User | None:
    sid = _extract_session_id(request)
    if sid is None:
        return None
    pair = await auth_service.load_active_session(db, sid)
    if pair is None:
        return None
    auth_session, user = pair
    request.state.user_id = user.id
    request.state.session_id = str(auth_session.id)
    # Aggiorna last_seen_at (best-effort)
    await auth_service.touch_session(db, auth_session.id)
    return user


async def current_user(
    user: Annotated[User | None, Depends(current_user_optional)],
) -> User:
    if user is None:
        raise UnauthorizedError("Autenticazione richiesta.", code="auth_required")
    return user


async def current_session(request: Request, db: DB) -> AuthSession:
    """Variante che ritorna la sessione attiva (per endpoint che la modificano)."""
    sid = _extract_session_id(request)
    if sid is None:
        raise UnauthorizedError("Autenticazione richiesta.", code="auth_required")
    pair = await auth_service.load_active_session(db, sid)
    if pair is None:
        raise UnauthorizedError("Sessione scaduta o invalidata.", code="session_invalid")
    return pair[0]


# Type aliases per uso negli endpoint
CurrentUser = Annotated[User, Depends(current_user)]
CurrentUserOptional = Annotated["User | None", Depends(current_user_optional)]
CurrentSession = Annotated[AuthSession, Depends(current_session)]
