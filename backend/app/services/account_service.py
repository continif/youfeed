"""Account self-service: export GDPR + delete con anonimizzazione activity_log.

Le FK con `ondelete=CASCADE` su `users.id` puliscono `auth_sessions`,
`email_verification_tokens`, `categories` (e con esse `user_sources` via
cascade su `category_id`). `activity_log` non ha FK (è partitioned + alto
volume, niente cascade): qui facciamo `UPDATE user_id=NULL` per anonimizzare
prima del DELETE finale dell'utente.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActivityLog,
    AuthSession,
    Category,
    EmailVerificationToken,
    Source,
    User,
    UserSource,
)

log = structlog.get_logger()


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


async def build_export_archive(session: AsyncSession, *, user: User) -> bytes:
    """Costruisce un ZIP in-memory con tutti i dati dell'utente.

    Layout:
      user.json
      categories.json
      sources.json
      sessions.json   (sessioni di login, ip/ua/timestamp)

    Le password/hash NON sono incluse. Le risposte sono pensate per
    GDPR Art. 20 (data portability).
    """
    user_payload: dict[str, Any] = {
        "id": int(user.id),
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
        "onboarding_completed_at": _to_iso(user.onboarding_completed_at),
        "created_at": _to_iso(user.created_at),
        "updated_at": _to_iso(user.updated_at),
    }

    cats_rows = (
        await session.execute(
            select(Category).where(Category.user_id == user.id).order_by(Category.id)
        )
    ).scalars().all()
    categories_payload = [
        {
            "id": int(c.id),
            "name": c.name,
            "slug": c.slug,
            "parent_id": c.parent_id,
            "position": c.position,
            "color": c.color,
            "is_public": c.is_public,
            "created_at": _to_iso(c.created_at),
        }
        for c in cats_rows
    ]

    us_rows = (
        await session.execute(
            select(UserSource, Source)
            .join(Source, Source.id == UserSource.source_id)
            .where(UserSource.user_id == user.id)
            .order_by(UserSource.id)
        )
    ).all()
    sources_payload = [
        {
            "user_source_id": int(us.id),
            "category_id": int(us.category_id),
            "custom_title": us.custom_title,
            "added_at": _to_iso(us.added_at),
            "source": {
                "id": int(src.id),
                "kind": src.kind,
                "url_site": src.url_site,
                "url_feed": src.url_feed,
                "wp_api_root": src.wp_api_root,
                "title": src.title,
                "favicon_url": src.favicon_url,
            },
        }
        for us, src in us_rows
    ]

    auth_rows = (
        await session.execute(
            select(AuthSession)
            .where(AuthSession.user_id == user.id)
            .order_by(AuthSession.created_at.desc())
        )
    ).scalars().all()
    sessions_payload = [
        {
            "id": str(s.id),
            "client": s.client,
            "ip": str(s.ip) if s.ip is not None else None,
            "country": s.country,
            "asn": s.asn,
            "ua": s.ua,
            "created_at": _to_iso(s.created_at),
            "last_seen_at": _to_iso(s.last_seen_at),
            "revoked_at": _to_iso(s.revoked_at),
        }
        for s in auth_rows
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("user.json", json.dumps(user_payload, indent=2, ensure_ascii=False))
        zf.writestr(
            "categories.json", json.dumps(categories_payload, indent=2, ensure_ascii=False)
        )
        zf.writestr(
            "sources.json", json.dumps(sources_payload, indent=2, ensure_ascii=False)
        )
        zf.writestr(
            "sessions.json", json.dumps(sessions_payload, indent=2, ensure_ascii=False)
        )
        zf.writestr(
            "README.txt",
            (
                "Export YouFeed (GDPR Art. 20).\n"
                f"Generato il {datetime.now(UTC).isoformat()} per utente "
                f"{user.username} (id={user.id}).\n"
                "I file JSON contengono i dati personali in tuo possesso.\n"
            ),
        )
    return buf.getvalue()


async def delete_user_cascade(session: AsyncSession, *, user_id: int) -> None:
    """Anonimizza l'activity_log e cancella l'utente (CASCADE pulisce il resto).

    Ordine deliberato:
      1. UPDATE activity_log SET user_id=NULL WHERE user_id=$id
      2. DELETE auth_sessions WHERE user_id=$id  (via CASCADE su DELETE users,
         ma la sessione corrente serve per essere revocata esplicitamente
         prima del DELETE — vedi router)
      3. DELETE FROM users WHERE id=$id (CASCADE su categories/user_sources/...)
    """
    # 1. Anonimizza activity_log (preservato per analytics globali)
    await session.execute(
        update(ActivityLog)
        .where(ActivityLog.user_id == user_id)
        .values(user_id=None, fingerprint=None, ua=None, ip=None)
    )

    # 2. Pulisci email tokens (sarebbero cascaded ma li facciamo espliciti
    # così se qualcuno aggiunge ondelete=SET NULL un domani, evitiamo dati orfani)
    await session.execute(
        delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
    )

    # 3. Delete user — CASCADE cancella categories/user_sources/auth_sessions
    await session.execute(delete(User).where(User.id == user_id))

    # NB: i topics/articles globali NON sono toccati. La community condivide
    # le sources e gli articoli sono indipendenti dall'utente.
    log.info("yf.account.deleted", user_id=user_id)


async def set_onboarding_completed(
    session: AsyncSession, *, user: User, completed: bool
) -> User:
    """Imposta `onboarding_completed_at` su NOW() (True) o NULL (False).
    Il caller fa commit + refresh."""
    if completed:
        user.onboarding_completed_at = datetime.now(UTC)
    else:
        user.onboarding_completed_at = None
    _ = session  # firma omogenea con altri metodi del modulo
    return user


async def count_user_data(session: AsyncSession, *, user_id: int) -> dict[str, int]:
    """Helper: ritorna i conteggi di dati legati all'utente (debug + UI 'cosa stai per cancellare')."""
    cats = await session.scalar(
        text("SELECT COUNT(*) FROM categories WHERE user_id = :uid").bindparams(uid=user_id)
    )
    src = await session.scalar(
        text("SELECT COUNT(*) FROM user_sources WHERE user_id = :uid").bindparams(uid=user_id)
    )
    sess = await session.scalar(
        text("SELECT COUNT(*) FROM auth_sessions WHERE user_id = :uid").bindparams(uid=user_id)
    )
    return {
        "categories": int(cats or 0),
        "user_sources": int(src or 0),
        "sessions": int(sess or 0),
    }
