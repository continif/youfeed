"""Servizio notifiche in-app (Phase 1.1.E).

Funzioni:
- CRUD usate dagli endpoint /yf_me/notifications/*
- `generate_daily_digests(db)` produce un digest "il tuo feed ha N nuovi
  articoli oggi" per ogni utente con almeno una fonte attiva e con una
  sessione attiva negli ultimi 14 giorni (evita di inondare account
  dormienti). Idempotente per giorno: salta se esiste già un digest per
  l'utente oggi.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, AuthSession, Notification, User, UserSource


log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Read-side
# ---------------------------------------------------------------------------


async def list_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    only_unread: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    stmt: Select[tuple[Notification]] = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if only_unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def count_unread(db: AsyncSession, *, user_id: int) -> int:
    res = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id)
        .where(Notification.read_at.is_(None))
    )
    return int(res.scalar_one() or 0)


# ---------------------------------------------------------------------------
# Write-side
# ---------------------------------------------------------------------------


async def mark_read(
    db: AsyncSession, *, notification_id: int, user_id: int
) -> Notification | None:
    res = await db.execute(
        select(Notification)
        .where(Notification.id == notification_id)
        .where(Notification.user_id == user_id)
    )
    notif = res.scalar_one_or_none()
    if notif is None:
        return None
    if notif.read_at is None:
        notif.read_at = datetime.now(UTC)
        await db.flush()
    return notif


async def mark_all_read(db: AsyncSession, *, user_id: int) -> int:
    """Marca read=now() tutte le notifiche unread dell'utente. Ritorna count."""
    res = await db.execute(
        Notification.__table__.update()
        .where(Notification.user_id == user_id)
        .where(Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
        .returning(Notification.id)
    )
    return len(res.fetchall())


async def delete_notification(
    db: AsyncSession, *, notification_id: int, user_id: int
) -> bool:
    """Elimina una notifica. Ritorna True se esisteva."""
    res = await db.execute(
        Notification.__table__.delete()
        .where(Notification.id == notification_id)
        .where(Notification.user_id == user_id)
        .returning(Notification.id)
    )
    return res.scalar_one_or_none() is not None


async def delete_all_read(db: AsyncSession, *, user_id: int) -> int:
    """Elimina tutte le notifiche già lette dell'utente. Ritorna count."""
    res = await db.execute(
        Notification.__table__.delete()
        .where(Notification.user_id == user_id)
        .where(Notification.read_at.is_not(None))
        .returning(Notification.id)
    )
    return len(res.fetchall())


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    payload: dict | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
        payload=payload,
    )
    db.add(notif)
    await db.flush()
    return notif


# ---------------------------------------------------------------------------
# Daily digest generator
# ---------------------------------------------------------------------------


DIGEST_LOOKBACK_HOURS = 24
ACTIVE_USER_LOOKBACK_DAYS = 14


async def _has_digest_today(db: AsyncSession, user_id: int, since: datetime) -> bool:
    res = await db.execute(
        select(Notification.id)
        .where(Notification.user_id == user_id)
        .where(Notification.kind == "digest_daily")
        .where(Notification.created_at >= since)
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _count_new_articles_for_user(
    db: AsyncSession, user_id: int, since: datetime
) -> int:
    """Conta articoli ingested negli ultimi N ore per le fonti attive dell'utente."""
    res = await db.execute(
        select(func.count(Article.id))
        .join(UserSource, UserSource.source_id == Article.source_id)
        .where(UserSource.user_id == user_id)
        .where(Article.ingested_at >= since)
    )
    return int(res.scalar_one() or 0)


async def generate_daily_digests(db: AsyncSession) -> int:
    """Crea un digest per ogni utente attivo con articoli nuovi nelle ultime 24h.

    Ritorna il numero di notifiche create. Idempotente per giorno.
    """
    now = datetime.now(UTC)
    article_since = now - timedelta(hours=DIGEST_LOOKBACK_HOURS)
    same_day_since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    active_since = now - timedelta(days=ACTIVE_USER_LOOKBACK_DAYS)

    # Utenti con: ≥1 user_source + sessione attiva recente
    res = await db.execute(
        select(User.id, User.username)
        .where(
            User.id.in_(
                select(UserSource.user_id).distinct()
            )
        )
        .where(
            User.id.in_(
                select(AuthSession.user_id)
                .where(AuthSession.last_seen_at >= active_since)
                .where(AuthSession.revoked_at.is_(None))
                .distinct()
            )
        )
    )
    candidates = res.all()

    created = 0
    for user_id, username in candidates:
        if await _has_digest_today(db, user_id, same_day_since):
            continue
        n_new = await _count_new_articles_for_user(db, user_id, article_since)
        if n_new <= 0:
            continue
        body = (
            f"Hai {n_new} nuovi articoli dalle tue fonti nelle ultime 24 ore."
            if n_new > 1
            else "Hai 1 nuovo articolo dalle tue fonti nelle ultime 24 ore."
        )
        await create_notification(
            db,
            user_id=user_id,
            kind="digest_daily",
            title="Nuovi articoli nel tuo feed",
            body=body,
            link="/me/feed",
            payload={"count": n_new},
        )
        created += 1
        log.info(
            "yf.notifications.digest_created",
            user_id=user_id,
            username=username,
            count=n_new,
        )

    await db.commit()
    log.info("yf.notifications.digest_run_complete", created=created)
    return created
