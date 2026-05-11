"""Servizio alerts (Phase 1.2.D iteration-1).

Iteration-1: alert basati su topic (un alert = "voglio essere notificato
quando appare un articolo con questo topic"). Il matcher gira come job RQ
accodato dopo l'indicizzazione di ogni articolo (vedi `workers/alerts.py`).

API:
- `list_alerts(db, user_id) -> list[Alert]`
- `create_alert(db, user_id, topic_id, channels)` (idempotente: ON CONFLICT
  riabilita l'alert esistente)
- `update_alert(db, user_id, alert_id, is_enabled?, channels?)`
- `delete_alert(db, user_id, alert_id)`
- `match_article(db, article_id)` (chiamato dal worker)
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError, NotFoundError
from app.models import (
    Alert,
    AlertMatch,
    Article,
    ArticleTopic,
    Topic,
)
from app.services import notification_service


log = structlog.get_logger()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

_ALLOWED_CHANNELS = {"inapp", "push"}


def _normalize_channels(channels: list[str] | None) -> list[str]:
    if not channels:
        return ["inapp"]
    seen: list[str] = []
    for c in channels:
        c = c.strip().lower()
        if c in _ALLOWED_CHANNELS and c not in seen:
            seen.append(c)
    return seen or ["inapp"]


async def list_alerts(db: AsyncSession, *, user_id: int) -> list[tuple[Alert, Topic]]:
    """Lista alert dell'utente, joined con il Topic per render diretto."""
    res = await db.execute(
        select(Alert, Topic)
        .join(Topic, Topic.id == Alert.topic_id)
        .where(Alert.user_id == user_id)
        .order_by(Alert.created_at.desc())
    )
    return [(a, t) for a, t in res.all()]


async def create_alert(
    db: AsyncSession, *, user_id: int, topic_id: int, channels: list[str] | None = None
) -> Alert:
    # Verifica topic esistente + non 'invalid'
    res = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = res.scalar_one_or_none()
    if topic is None:
        raise NotFoundError("Topic non trovato.", code="topic_not_found")
    if topic.type == "invalid":
        raise AppError(
            "Topic non utilizzabile per gli alert.",
            code="topic_invalid",
            status_code=400,
        )

    norm_channels = _normalize_channels(channels)
    now = datetime.now(UTC)

    stmt = (
        pg_insert(Alert)
        .values(
            user_id=user_id,
            topic_id=topic_id,
            channels=norm_channels,
            is_enabled=True,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_alerts_user_topic",
            set_={"is_enabled": True, "channels": norm_channels, "updated_at": now},
        )
        .returning(Alert)
    )
    res = await db.execute(stmt)
    row = res.scalar_one()
    return row


async def update_alert(
    db: AsyncSession,
    *,
    user_id: int,
    alert_id: int,
    is_enabled: bool | None = None,
    channels: list[str] | None = None,
) -> Alert:
    res = await db.execute(
        select(Alert).where(and_(Alert.id == alert_id, Alert.user_id == user_id))
    )
    alert = res.scalar_one_or_none()
    if alert is None:
        raise NotFoundError("Alert non trovato.", code="alert_not_found")

    if is_enabled is not None:
        alert.is_enabled = is_enabled
    if channels is not None:
        alert.channels = _normalize_channels(channels)
    alert.updated_at = datetime.now(UTC)
    await db.flush()
    return alert


async def delete_alert(db: AsyncSession, *, user_id: int, alert_id: int) -> bool:
    res = await db.execute(
        delete(Alert)
        .where(Alert.id == alert_id)
        .where(Alert.user_id == user_id)
        .returning(Alert.id)
    )
    return res.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Matcher (chiamato dal worker)
# ---------------------------------------------------------------------------


async def match_article(db: AsyncSession, *, article_id: int) -> int:
    """Genera AlertMatch + Notification per ogni alert attivo che matcha
    uno dei topic dell'articolo. Ritorna il numero di notifiche create.

    Idempotente: la PK composita su `alert_matches` evita duplicati se la
    funzione viene rieseguita sullo stesso articolo (es. retry RQ).
    """
    article = await db.get(Article, article_id)
    if article is None:
        return 0

    # Topic dell'articolo
    topic_ids_res = await db.execute(
        select(ArticleTopic.topic_id).where(ArticleTopic.article_id == article_id)
    )
    topic_ids = [int(r) for r in topic_ids_res.scalars().all()]
    if not topic_ids:
        return 0

    # Alert attivi sui topic
    res = await db.execute(
        select(Alert, Topic)
        .join(Topic, Topic.id == Alert.topic_id)
        .where(Alert.topic_id.in_(topic_ids))
        .where(Alert.is_enabled.is_(True))
    )
    candidates = list(res.all())
    if not candidates:
        return 0

    # Recupero title per la notifica (vive in Manticore, non in PG)
    from app.ingestion import manticore_client

    title: str | None = None
    try:
        docs = await manticore_client.get_by_ids([article_id])
        title = (docs.get(article_id) or {}).get("title")
    except Exception:
        title = None
    if not title:
        title = article.url_canonical

    created = 0
    for alert, topic in candidates:
        # Insert match: ON CONFLICT DO NOTHING per idempotenza
        ins = (
            pg_insert(AlertMatch)
            .values(alert_id=int(alert.id), article_id=article_id)
            .on_conflict_do_nothing(index_elements=["alert_id", "article_id"])
            .returning(AlertMatch.alert_id)
        )
        ins_res = await db.execute(ins)
        if ins_res.scalar_one_or_none() is None:
            # Già notificato in passato → skip
            continue

        await notification_service.create_notification(
            db,
            user_id=int(alert.user_id),
            kind="alert_match",
            title=f"Nuovo articolo su «{topic.display_name}»",
            body=title[:200],
            link=f"/me/article/{article_id}",
            payload={
                "alert_id": int(alert.id),
                "topic_id": int(topic.id),
                "topic_slug": topic.slug,
                "article_id": article_id,
            },
        )
        created += 1

        # Push channel: accoda un job se 'push' è tra i channels dell'alert
        if "push" in (alert.channels or []):
            from app.workers.push import enqueue_push

            try:
                enqueue_push(
                    int(alert.user_id),
                    {
                        "title": f"Nuovo articolo su «{topic.display_name}»",
                        "body": title[:200],
                        "link": f"/me/article/{article_id}",
                        "tag": f"alert-{alert.id}",
                    },
                )
            except Exception as e:
                log.debug("yf.alerts.push_enqueue_failed", error=str(e))

    await db.commit()
    if created:
        log.info(
            "yf.alerts.matched",
            article_id=article_id,
            alerts_matched=created,
            topic_count=len(topic_ids),
        )
    return created
