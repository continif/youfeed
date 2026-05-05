"""Servizio auth: registrazione, login, sessioni, verifica email, password."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.models import (
    AuthSession,
    EmailVerificationToken,
    ReservedUsername,
    User,
)
from app.utils.passwords import hash_password, needs_rehash, verify_password
from app.utils.tokens import url_safe_token

if TYPE_CHECKING:
    pass


USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_]{1,28}[a-z0-9])?$")
# 3-30 char, lowercase + cifre + underscore, no underscore iniziale/finale.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MIN_PASSWORD_LEN = 10


class ValidationError(Exception):
    """Errore di validazione semantica (vs RequestValidationError di FastAPI)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Validazione
# ---------------------------------------------------------------------------


async def validate_username(session: AsyncSession, username: str) -> None:
    """Verifica formato + non in reserved_usernames + prefisso yf_."""
    norm = username.lower().strip()

    if not USERNAME_RE.match(norm):
        raise ValidationError(
            "invalid_username",
            "Username non valido: 3-30 caratteri, minuscole, cifre, underscore.",
        )

    if norm.startswith("yf_"):
        raise ValidationError(
            "reserved_prefix",
            "Username che iniziano per 'yf_' sono riservati.",
        )

    res = await session.execute(
        select(ReservedUsername.word).where(func.lower(ReservedUsername.word) == norm)
    )
    if res.scalar_one_or_none() is not None:
        raise ValidationError("reserved_username", "Username riservato, scegline un altro.")


def validate_email(email: str) -> str:
    norm = email.strip().lower()
    if not EMAIL_RE.match(norm):
        raise ValidationError("invalid_email", "Email non valida.")
    return norm


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValidationError(
            "weak_password",
            f"La password deve avere almeno {MIN_PASSWORD_LEN} caratteri.",
        )
    # Politica MVP: solo lunghezza. Aggiungere classi di caratteri se serve.


async def is_username_available(session: AsyncSession, username: str) -> bool:
    """True se l'username è formalmente valido, non riservato e non occupato."""
    try:
        await validate_username(session, username)
    except ValidationError:
        return False
    res = await session.execute(select(User.id).where(User.username == username.lower()))
    return res.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Registrazione + verifica email
# ---------------------------------------------------------------------------


async def register_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
) -> tuple[User, str]:
    """Crea un User non verificato e restituisce (user, verification_token).

    Il caller emette l'email con il link `…/verify-email?token={token}`.
    """
    norm_username = username.lower().strip()
    norm_email = validate_email(email)
    validate_password(password)
    await validate_username(session, norm_username)

    # Conflitti
    existing = await session.execute(
        select(User).where(or_(User.username == norm_username, User.email == norm_email))
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        if found.username == norm_username:
            raise ConflictError("Username già in uso.", code="username_taken")
        raise ConflictError("Email già registrata.", code="email_taken")

    user = User(
        username=norm_username,
        email=norm_email,
        password_hash=hash_password(password),
        email_verified=False,
    )
    session.add(user)
    await session.flush()

    token = url_safe_token(32)
    session.add(
        EmailVerificationToken(
            token=token,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    await session.flush()
    return user, token


async def verify_email_token(session: AsyncSession, token: str) -> User:
    res = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token == token)
    )
    record = res.scalar_one_or_none()
    if record is None:
        raise NotFoundError("Token non valido.", code="invalid_token")

    now = datetime.now(UTC)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        raise UnauthorizedError("Token scaduto.", code="expired_token")

    user = await session.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Utente non trovato.", code="user_not_found")

    user.email_verified = True
    await session.delete(record)
    await session.flush()
    return user


async def issue_new_verification_token(session: AsyncSession, user: User) -> str:
    """Invalida i token pendenti per l'utente e ne emette uno nuovo."""
    await session.execute(
        EmailVerificationToken.__table__.delete().where(
            EmailVerificationToken.user_id == user.id
        )
    )
    token = url_safe_token(32)
    session.add(
        EmailVerificationToken(
            token=token,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    await session.flush()
    return token


# ---------------------------------------------------------------------------
# Login + sessioni
# ---------------------------------------------------------------------------


async def authenticate(
    session: AsyncSession, *, identifier: str, password: str
) -> User:
    """Login per username o email + password. Solleva UnauthorizedError se fallisce."""
    norm = identifier.strip().lower()
    res = await session.execute(
        select(User).where(or_(User.username == norm, User.email == norm))
    )
    user = res.scalar_one_or_none()
    if user is None or user.password_hash is None:
        raise UnauthorizedError("Credenziali non valide.", code="invalid_credentials")

    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("Credenziali non valide.", code="invalid_credentials")

    if not user.email_verified:
        raise UnauthorizedError(
            "Email non ancora verificata. Controlla la tua casella.",
            code="email_not_verified",
        )

    # Rehash trasparente se i parametri Argon2 sono stati alzati
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    fingerprint: str | None,
    client: str = "web",
    ip: str | None = None,
    country: str | None = None,
    asn: int | None = None,
    ua: str | None = None,
) -> AuthSession:
    auth = AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        fingerprint=fingerprint,
        client=client,
        ip=ip,
        country=country,
        asn=asn,
        ua=ua,
    )
    session.add(auth)
    await session.flush()
    return auth


async def revoke_session(session: AsyncSession, session_id: uuid.UUID) -> None:
    auth = await session.get(AuthSession, session_id)
    if auth is None or auth.revoked_at is not None:
        return
    auth.revoked_at = datetime.now(UTC)
    await session.flush()


async def touch_session(session: AsyncSession, session_id: uuid.UUID) -> None:
    """Aggiorna last_seen_at. Chiamato dal middleware/dependency di auth."""
    await session.execute(
        AuthSession.__table__.update()
        .where(AuthSession.id == session_id)
        .where(AuthSession.revoked_at.is_(None))
        .values(last_seen_at=datetime.now(UTC))
    )


async def load_active_session(
    session: AsyncSession, session_id: uuid.UUID
) -> tuple[AuthSession, User] | None:
    """Carica sessione attiva + utente in un solo round-trip."""
    res = await session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.id == session_id)
        .where(AuthSession.revoked_at.is_(None))
        .where(
            AuthSession.last_seen_at
            > datetime.now(UTC) - timedelta(days=get_settings().session_lifetime_days)
        )
    )
    row = res.first()
    if row is None:
        return None
    return row[0], row[1]


# ---------------------------------------------------------------------------
# Cambio password
# ---------------------------------------------------------------------------


async def change_password(
    session: AsyncSession, user: User, *, current: str, new: str
) -> None:
    if user.password_hash is None or not verify_password(current, user.password_hash):
        raise UnauthorizedError("Password corrente non valida.", code="invalid_password")
    validate_password(new)
    user.password_hash = hash_password(new)
    await session.flush()
