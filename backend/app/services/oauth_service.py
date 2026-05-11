"""OAuth service.

In v1.1 implementiamo un **flow simulato** "Google OAuth-like" per non
bloccare lo sviluppo in attesa della configurazione su Google Cloud Console.
Gli endpoint backend (`/yf_auth/google/authorize`, `/yf_auth/google/callback`)
hanno la stessa shape di un OAuth Authorization Code reale, così quando si
arriverà al vero Google il drop-in è isolato a `mock_exchange_code` →
`google_exchange_code`.

Comportamento:
- `is_simulate()` → True se `google_oauth_client_id` è vuoto (default dev).
- `build_authorize_redirect(next_path)` → produce l'URL della pagina di
  consenso (stub in /yf_auth/google/_mock in sim; URL Google in reale).
- `state` è un token firmato HMAC-SHA256 che incapsula `nonce`/`next`/`iat`.
- `exchange_code(code, state)` valida lo state e ritorna `OAuthProfile`.
- `find_or_create_oauth_user(db, profile)` lega o crea l'utente in DB:
  - match su `google_sub` → uso quello;
  - altrimenti match su email → lego `google_sub` all'esistente (auto-link
    accettabile in sim/dev; in prod si gestirà con conferma esplicita);
  - altrimenti nuovo User con username derivato dall'email + suffix se
    collide, password_hash NULL, email_verified=True (Google ha verificato).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import AppError
from app.models import ReservedUsername, User


# ---------------------------------------------------------------------------
# State firmato (HMAC-SHA256)
# ---------------------------------------------------------------------------

STATE_TTL_SECONDS = 600  # 10 minuti


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()


def issue_state(next_path: str | None) -> str:
    """Firma uno state token che incapsula nonce/next/iat."""
    settings = get_settings()
    payload = {
        "n": secrets.token_urlsafe(16),
        "next": next_path or "",
        "iat": int(time.time()),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = _sign(raw, settings.yf_secret_key)
    return f"{_b64url(raw)}.{_b64url(sig)}"


def verify_state(state: str) -> dict[str, str | int]:
    """Verifica firma + scadenza. Solleva AppError(400) se invalido."""
    if not state or state.count(".") != 1:
        raise AppError("State non valido.", code="oauth_state_invalid", status_code=400)
    payload_b64, sig_b64 = state.split(".", 1)
    try:
        raw = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception as e:
        raise AppError("State malformato.", code="oauth_state_invalid", status_code=400) from e

    settings = get_settings()
    expected = _sign(raw, settings.yf_secret_key)
    if not hmac.compare_digest(sig, expected):
        raise AppError("State signature mismatch.", code="oauth_state_invalid", status_code=400)

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise AppError("State payload illeggibile.", code="oauth_state_invalid", status_code=400) from e

    iat = int(data.get("iat", 0))
    if iat <= 0 or (int(time.time()) - iat) > STATE_TTL_SECONDS:
        raise AppError("State scaduto.", code="oauth_state_expired", status_code=400)
    return data


# ---------------------------------------------------------------------------
# Profile + mock exchange
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    sub: str
    email: str
    name: str | None = None


def is_simulate() -> bool:
    """True quando non è configurato un client_id Google reale."""
    return not bool(get_settings().google_oauth_client_id.strip())


def build_authorize_redirect(next_path: str | None) -> str:
    """URL su cui redirigere il browser dopo `/yf_auth/google/authorize`.

    In sim → la pagina di consenso stub `/yf_auth/google/_mock`.
    In reale → URL Google con i parametri OAuth.
    """
    state = issue_state(next_path)
    if is_simulate():
        return f"/yf_auth/google/_mock?state={urllib.parse.quote(state)}"

    settings = get_settings()
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


MOCK_CODE_RE = re.compile(r"^mock:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})$")


async def exchange_code(code: str, state: str) -> OAuthProfile:
    """Verifica lo state e produce il profilo OAuth.

    In sim il `code` ha forma `mock:<email>` (la pagina stub lo costruisce).
    """
    verify_state(state)

    if is_simulate():
        m = MOCK_CODE_RE.match(code or "")
        if not m:
            raise AppError(
                "Codice mock non valido.",
                code="oauth_code_invalid",
                status_code=400,
            )
        email = m.group(1).lower()
        # `sub` Google è opaco e stabile per utente; in sim deriviamo da email
        # con prefisso identificabile, così è ovvio in DB che è un account mock.
        sub = "mock-" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
        return OAuthProfile(sub=sub, email=email, name=None)

    raise AppError(
        "Google OAuth reale non ancora implementato.",
        code="oauth_not_configured",
        status_code=501,
    )


# ---------------------------------------------------------------------------
# User lookup / creation
# ---------------------------------------------------------------------------


_USERNAME_SAFE_RE = re.compile(r"[^a-z0-9_]")


def _username_from_email(email: str) -> str:
    """Username candidato dall'email locale-part, normalizzato."""
    local = email.split("@", 1)[0].lower()
    norm = _USERNAME_SAFE_RE.sub("_", local)
    norm = norm.strip("_") or "user"
    if not (norm[0].isalpha() or norm[0].isdigit()):
        norm = "u_" + norm
    return norm[:28]


async def _pick_available_username(db: AsyncSession, base: str) -> str:
    """Trova un username libero partendo da `base` (suffisso _N se collide)."""
    # Verifica anche reserved + prefisso yf_ (il base non lo avrebbe già: lo
    # toglierebbe il regex; difesa in profondità)
    if base.startswith("yf_"):
        base = "u_" + base[3:]

    res = await db.execute(
        select(ReservedUsername.word).where(func.lower(ReservedUsername.word) == base)
    )
    if res.scalar_one_or_none() is not None:
        base = "u_" + base

    for n in range(0, 1000):
        candidate = base if n == 0 else f"{base}_{n}"
        if len(candidate) > 30:
            candidate = candidate[:30]
        r = await db.execute(select(User.id).where(User.username == candidate))
        if r.scalar_one_or_none() is None:
            return candidate
    # Fallback estremo
    return "u_" + secrets.token_hex(6)


async def find_or_create_oauth_user(db: AsyncSession, profile: OAuthProfile) -> User:
    """Lookup per google_sub, fallback per email, oppure crea un nuovo utente.

    In tutti i casi l'utente risultante ha:
    - `google_sub` valorizzato con `profile.sub`;
    - `email_verified=True` (Google attesta l'email; per il mock accettiamo
      il claim come per il reale flow).
    """
    # 1. match per sub
    res = await db.execute(select(User).where(User.google_sub == profile.sub))
    user = res.scalar_one_or_none()
    if user is not None:
        if not user.email_verified:
            user.email_verified = True
        return user

    # 2. match per email — auto-link
    res = await db.execute(select(User).where(User.email == profile.email))
    user = res.scalar_one_or_none()
    if user is not None:
        user.google_sub = profile.sub
        user.email_verified = True
        return user

    # 3. nuovo utente
    base = _username_from_email(profile.email)
    username = await _pick_available_username(db, base)
    user = User(
        username=username,
        email=profile.email,
        password_hash=None,  # account OAuth-only finché non setta una pwd
        google_sub=profile.sub,
        email_verified=True,
    )
    db.add(user)
    await db.flush()
    return user
