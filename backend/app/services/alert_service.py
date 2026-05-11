"""Servizio alerts multi-topic (Phase 1.2.D + ext).

Modello dati:
- `alerts(id, user_id, channels[], match_mode, is_enabled, …)` — un alert
  può avere N topic, modalità match `'all'` (AND) o `'any'` (OR).
- `alert_topics(alert_id, topic_id)` M:N.

API:
- `list_alerts(db, user_id) -> list[Alert]` (relationship `topics` eager-loaded)
- `create_alert(db, user_id, topic_ids, channels, match_mode)` (validazione
  topic esistenti + non `'invalid'`)
- `update_alert(db, user_id, alert_id, is_enabled?, channels?, topic_ids?,
  match_mode?)` — replace dei topic se passati
- `delete_alert(db, user_id, alert_id)`
- `match_article(db, article_id)` (chiamato dal worker): logica set ⊆ per
  AND, intersezione non vuota per OR
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
    AlertTopic,
    Article,
    ArticleTopic,
    Topic,
)
from app.services import notification_service


log = structlog.get_logger()


_ALLOWED_CHANNELS = {"inapp", "push"}
_ALLOWED_MATCH_MODES = {"all", "any"}


def _normalize_channels(channels: list[str] | None) -> list[str]:
    if not channels:
        return ["inapp"]
    seen: list[str] = []
    for c in channels:
        c = c.strip().lower()
        if c in _ALLOWED_CHANNELS and c not in seen:
            seen.append(c)
    return seen or ["inapp"]


def _normalize_match_mode(mode: str | None) -> str:
    if not mode or mode not in _ALLOWED_MATCH_MODES:
        return "all"
    return mode


async def _validate_topics(db: AsyncSession, topic_ids: list[int]) -> list[Topic]:
    """Verifica che i topic esistano e nessuno sia type='invalid'."""
    if not topic_ids:
        raise AppError("Almeno un topic è richiesto.", code="topics_required", status_code=400)
    unique_ids = list(dict.fromkeys(topic_ids))  # preserve order, dedupe
    if len(unique_ids) > 10:
        raise AppError("Massimo 10 topic per alert.", code="too_many_topics", status_code=400)

    res = await db.execute(select(Topic).where(Topic.id.in_(unique_ids)))
    topics = list(res.scalars().all())
    found_ids = {int(t.id) for t in topics}
    missing = [tid for tid in unique_ids if tid not in found_ids]
    if missing:
        raise NotFoundError(
            f"Topic non trovati: {missing}", code="topic_not_found"
        )
    invalid = [t for t in topics if t.type == "invalid"]
    if invalid:
        raise AppError(
            "Alcuni topic non sono utilizzabili (tipo invalid).",
            code="topic_invalid",
            status_code=400,
        )
    return topics


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def list_alerts(db: AsyncSession, *, user_id: int) -> list[Alert]:
    """Lista alert dell'utente, con topic eager-loaded (selectin)."""
    res = await db.execute(
        select(Alert).where(Alert.user_id == user_id).order_by(Alert.created_at.desc())
    )
    return list(res.scalars().all())


async def create_alert(
    db: AsyncSession,
    *,
    user_id: int,
    topic_ids: list[int],
    channels: list[str] | None = None,
    match_mode: str | None = None,
) -> Alert:
    """Crea un nuovo alert con N topic. Sempre crea una nuova row — l'UI può
    eventualmente offrire "merge" se rileva un alert con stesso set."""
    topics = await _validate_topics(db, topic_ids)
    norm_channels = _normalize_channels(channels)
    norm_mode = _normalize_match_mode(match_mode)

    alert = Alert(
        user_id=user_id,
        channels=norm_channels,
        match_mode=norm_mode,
        is_enabled=True,
    )
    db.add(alert)
    await db.flush()  # serve alert.id per i join

    for t in topics:
        db.add(AlertTopic(alert_id=int(alert.id), topic_id=int(t.id)))
    await db.flush()
    await db.refresh(alert, attribute_names=["topics"])
    return alert


async def update_alert(
    db: AsyncSession,
    *,
    user_id: int,
    alert_id: int,
    is_enabled: bool | None = None,
    channels: list[str] | None = None,
    topic_ids: list[int] | None = None,
    match_mode: str | None = None,
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
    if match_mode is not None:
        alert.match_mode = _normalize_match_mode(match_mode)
    if topic_ids is not None:
        topics = await _validate_topics(db, topic_ids)
        # Replace: cancella le righe esistenti e inserisce le nuove
        await db.execute(
            delete(AlertTopic).where(AlertTopic.alert_id == int(alert.id))
        )
        for t in topics:
            db.add(AlertTopic(alert_id=int(alert.id), topic_id=int(t.id)))

    alert.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(alert, attribute_names=["topics"])
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
    """Genera AlertMatch + Notification per ogni alert attivo che soddisfa la
    condizione `match_mode` sui topic dell'articolo.

    - `match_mode='all'`: l'articolo deve contenere TUTTI i topic dell'alert
      (set inclusion `alert.topics ⊆ article.topics`).
    - `match_mode='any'`: l'articolo deve contenere ALMENO UNO dei topic.

    Idempotente: la PK composita su `alert_matches` evita duplicati.
    """
    article = await db.get(Article, article_id)
    if article is None:
        return 0

    # Topic dell'articolo
    topic_ids_res = await db.execute(
        select(ArticleTopic.topic_id).where(ArticleTopic.article_id == article_id)
    )
    article_topic_ids: set[int] = {int(r) for r in topic_ids_res.scalars().all()}
    if not article_topic_ids:
        return 0

    # Pre-filtro: alerts che hanno ALMENO UN topic in comune con l'articolo.
    # Per 'any' è sufficiente; per 'all' è un superset (raffiniamo sotto).
    candidate_alert_ids_res = await db.execute(
        select(AlertTopic.alert_id)
        .where(AlertTopic.topic_id.in_(article_topic_ids))
        .distinct()
    )
    candidate_alert_ids = [int(r) for r in candidate_alert_ids_res.scalars().all()]
    if not candidate_alert_ids:
        return 0

    # Carica alerts candidati + tutti i loro topic_ids in un singolo round-trip
    alert_rows = await db.execute(
        select(Alert)
        .where(Alert.id.in_(candidate_alert_ids))
        .where(Alert.is_enabled.is_(True))
    )
    candidates = list(alert_rows.scalars().all())
    if not candidates:
        return 0

    # Costruisci mappa alert_id → set(topic_ids) caricando da alert_topics
    at_rows = await db.execute(
        select(AlertTopic.alert_id, AlertTopic.topic_id).where(
            AlertTopic.alert_id.in_([int(a.id) for a in candidates])
        )
    )
    topics_per_alert: dict[int, set[int]] = {}
    for aid, tid in at_rows.all():
        topics_per_alert.setdefault(int(aid), set()).add(int(tid))

    # Recupero titolo articolo (vive in Manticore)
    from app.ingestion import manticore_client

    title: str | None = None
    try:
        docs = await manticore_client.get_by_ids([article_id])
        title = (docs.get(article_id) or {}).get("title")
    except Exception:
        title = None
    if not title:
        title = article.url_canonical

    # Display name per i topic matched (per body notifica)
    matched_topic_ids = set()
    for alert in candidates:
        matched_topic_ids.update(topics_per_alert.get(int(alert.id), set()))
    matched_topic_ids &= article_topic_ids
    topic_names: dict[int, tuple[str, str, str]] = {}
    if matched_topic_ids:
        name_res = await db.execute(
            select(Topic.id, Topic.display_name, Topic.slug, Topic.type)
            .where(Topic.id.in_(matched_topic_ids))
        )
        for tid, name, slug, ttype in name_res.all():
            topic_names[int(tid)] = (name, slug, ttype)

    created = 0
    for alert in candidates:
        alert_topic_set = topics_per_alert.get(int(alert.id), set())
        if not alert_topic_set:
            continue

        if alert.match_mode == "all":
            satisfied = alert_topic_set.issubset(article_topic_ids)
        else:
            satisfied = bool(alert_topic_set & article_topic_ids)
        if not satisfied:
            continue

        # Insert match: ON CONFLICT DO NOTHING per idempotenza
        ins = (
            pg_insert(AlertMatch)
            .values(alert_id=int(alert.id), article_id=article_id)
            .on_conflict_do_nothing(index_elements=["alert_id", "article_id"])
            .returning(AlertMatch.alert_id)
        )
        ins_res = await db.execute(ins)
        if ins_res.scalar_one_or_none() is None:
            continue

        # Compose notification text from matched topics
        hit_ids = list(alert_topic_set & article_topic_ids)
        hit_names = [topic_names[tid][0] for tid in hit_ids if tid in topic_names]
        if len(hit_names) == 1:
            title_n = f"Nuovo articolo su «{hit_names[0]}»"
        else:
            joined = " + ".join(f"«{n}»" for n in hit_names[:4])
            if len(hit_names) > 4:
                joined += f" +{len(hit_names) - 4}"
            title_n = f"Nuovo articolo: {joined}"

        await notification_service.create_notification(
            db,
            user_id=int(alert.user_id),
            kind="alert_match",
            title=title_n,
            body=title[:200],
            link=f"/me/article/{article_id}",
            payload={
                "alert_id": int(alert.id),
                "topic_ids": list(alert_topic_set),
                "matched_topic_ids": hit_ids,
                "match_mode": alert.match_mode,
                "article_id": article_id,
            },
        )
        created += 1

        # Push channel
        if "push" in (alert.channels or []):
            from app.workers.push import enqueue_push

            try:
                enqueue_push(
                    int(alert.user_id),
                    {
                        "title": title_n,
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
            article_topic_count=len(article_topic_ids),
            candidates=len(candidates),
        )
    return created
