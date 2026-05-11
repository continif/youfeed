"""Retention sweep (Phase 1.2.G).

Droppa articoli vecchi e senza engagement per controllare la dimensione del
content store. Idempotente, batched, supporta dry-run.

Criteri di mantenimento (un articolo è "preservato" se ANCHE solo uno di
questi è vero):
- `read_count > 0` o `open_count > 0` (engagement utente)
- esiste almeno una riga in `alert_matches` (qualcuno è stato notificato)
- `published_at >= now - max_age_days` (articolo recente)
- source del articolo è `is_featured=true` (le fonti featured mantengono lo
  storico per il dispatcher pubblico Jinja2)

Per ogni articolo droppato:
1. cancellazione dal Manticore RT index (`articles_rt`)
2. DELETE FROM articles → CASCADE su article_topics, article_entities,
   alert_matches, ecc.

I file immagine su disco NON vengono toccati in iteration-1: il deduplica
per URL-hash significa che lo stesso file può servire più articoli, e un
reference-counting esaustivo a tempo di sweep è costoso. Le immagini orfane
si possono ripulire con un job separato (TODO 1.2.G-ext).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import manticore_client
from app.models import AlertMatch, Article, FeaturedSource


log = structlog.get_logger()


DEFAULT_MAX_AGE_DAYS = 365
DEFAULT_BATCH_SIZE = 500


@dataclass(slots=True)
class SweepStats:
    candidates: int = 0
    deleted: int = 0
    manticore_failed: int = 0
    dry_run: bool = False


def _candidate_filter(cutoff: datetime):
    """Predicato SQL per "candidabile alla cancellazione".

    Articolo OLD (published_at < cutoff) AND senza engagement AND senza
    alert_match AND non appartenente a una source featured.
    """
    no_engagement = and_(Article.read_count == 0, Article.open_count == 0)
    no_alert = ~exists().where(AlertMatch.article_id == Article.id)
    # Source featured = entry in featured_sources (con eventuale featured_until
    # nel futuro o NULL = sempre featured). Manteniamo l'archivio per il
    # dispatcher pubblico Jinja2.
    now = datetime.now(UTC)
    not_featured = ~exists().where(
        and_(
            FeaturedSource.source_id == Article.source_id,
            or_(
                FeaturedSource.featured_until.is_(None),
                FeaturedSource.featured_until > now,
            ),
        )
    )
    return and_(
        Article.published_at < cutoff,
        no_engagement,
        no_alert,
        not_featured,
    )


async def count_candidates(
    db: AsyncSession, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    res = await db.execute(
        select(func.count(Article.id)).where(_candidate_filter(cutoff))
    )
    return int(res.scalar_one() or 0)


async def _drop_batch(db: AsyncSession, ids: list[int]) -> tuple[int, int]:
    """Cancella un batch di articoli da Manticore + Postgres.

    Ritorna (deleted_count, manticore_failures).
    """
    if not ids:
        return 0, 0

    # 1. Manticore (best-effort per id; se Manticore è down, log e procedi)
    mfail = 0
    for aid in ids:
        ok = await manticore_client.delete_article(int(aid))
        if not ok:
            mfail += 1

    # 2. Postgres delete cascade
    res = await db.execute(
        delete(Article).where(Article.id.in_(ids)).returning(Article.id)
    )
    deleted_ids = [int(r) for r in res.scalars().all()]
    await db.commit()
    return len(deleted_ids), mfail


async def sweep(
    db: AsyncSession,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    dry_run: bool = False,
) -> SweepStats:
    """Esegue il sweep completo. Ritorna le stats.

    `max_batches` permette di limitare il throughput per run (utile per
    primi cicli prudenti). `dry_run=True` conta i candidati senza toccare.
    """
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    stats = SweepStats(dry_run=dry_run)

    if dry_run:
        stats.candidates = await count_candidates(db, max_age_days=max_age_days)
        log.info(
            "yf.retention.dry_run",
            candidates=stats.candidates,
            cutoff=cutoff.isoformat(),
            max_age_days=max_age_days,
        )
        return stats

    batch_n = 0
    while True:
        # Seleziona prossimo batch (LIMIT senza OFFSET, gli ID già cancellati
        # non riappaiono dopo il commit)
        res = await db.execute(
            select(Article.id)
            .where(_candidate_filter(cutoff))
            .order_by(Article.id.asc())
            .limit(batch_size)
        )
        ids = [int(r) for r in res.scalars().all()]
        if not ids:
            break

        batch_n += 1
        deleted, mfail = await _drop_batch(db, ids)
        stats.candidates += len(ids)
        stats.deleted += deleted
        stats.manticore_failed += mfail

        log.info(
            "yf.retention.batch",
            batch=batch_n,
            requested=len(ids),
            deleted=deleted,
            manticore_failed=mfail,
        )

        if max_batches is not None and batch_n >= max_batches:
            log.info("yf.retention.max_batches_reached", max_batches=max_batches)
            break

    log.info(
        "yf.retention.complete",
        deleted=stats.deleted,
        manticore_failed=stats.manticore_failed,
        max_age_days=max_age_days,
    )
    return stats
