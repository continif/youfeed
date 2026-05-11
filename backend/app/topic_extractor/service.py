"""Logica DB per il topic extractor: scan articoli, upsert entities, review,
confirm, reject. Niente HTTP — i comandi CLI in `cli.py` chiamano qui.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Article,
    Entity,
    EntitySourceCount,
    Topic,
)
from app.topic_extractor.extractor import (
    Candidate,
    extract_all,
    extract_models,
    normalize,
)
from app.utils.slugify import slugify

log = structlog.get_logger()


@dataclass
class ScanStats:
    articles_seen: int = 0
    entities_inserted: int = 0
    entities_updated: int = 0
    source_counts_updated: int = 0


@dataclass
class ReviewItem:
    """Riga del comando `review`. `subtoken_topics` aiuta l'umano a capire
    se la entity è già nota in parte (es. 'Coca Cola' → 'Cola' è subject)."""

    entity_id: int
    surface_form: str
    normalized: str
    ner_type: str
    occurrence_count: int
    sources_count: int
    subtoken_topics: list[tuple[str, str]]  # [(subtoken, topic_type), ...]


# ---------------------------------------------------------------------------
# Scan articoli → entities
# ---------------------------------------------------------------------------


async def scan_articles(
    session: AsyncSession,
    *,
    article_limit: int | None = None,
    only_after_id: int | None = None,
    use_known_brands: bool = False,
) -> ScanStats:
    """Esegue gli extractor su titolo+description di tutti gli articoli.

    `use_known_brands=True` abilita anche l'extractor MODEL leggendo
    `topics WHERE type='brand' AND is_curated=true` come whitelist.
    """
    stats = ScanStats()

    known_brands: list[str] = []
    if use_known_brands:
        rows = (
            await session.execute(
                select(Topic.display_name, Topic.aliases)
                .where(Topic.type == "brand")
                .where(Topic.is_curated.is_(True))
            )
        ).all()
        for display_name, aliases in rows:
            if display_name:
                known_brands.append(display_name)
            for a in aliases or []:
                if a:
                    known_brands.append(a)

    stmt = select(Article.id, Article.source_id, Article.raw_meta_lite).where(
        Article.processing_status == "indexed"
    )
    if only_after_id is not None:
        stmt = stmt.where(Article.id > only_after_id)
    stmt = stmt.order_by(Article.id)
    if article_limit is not None:
        stmt = stmt.limit(article_limit)

    # Aggregatori in-memory per ridurre round-trip DB. Flush ogni 500 articoli.
    pending: dict[tuple[str, str], int] = defaultdict(int)  # (normalized, ner_type) → count
    pending_surface: dict[tuple[str, str], str] = {}  # → first surface_form seen
    pending_per_source: dict[tuple[str, str, int], int] = defaultdict(int)
    flush_every = 500

    rows = (await session.execute(stmt)).all()
    for art_id, source_id, raw_meta in rows:
        stats.articles_seen += 1
        text = _join_meta(raw_meta)
        if not text:
            continue
        candidates = extract_all(text, known_brands=known_brands or None)
        if not candidates:
            continue
        for c in candidates:
            key = (normalize(c.surface_form), c.ner_type)
            pending[key] += 1
            pending_surface.setdefault(key, c.surface_form)
            pending_per_source[(*key, int(source_id))] += 1

        if stats.articles_seen % flush_every == 0:
            await _flush(
                session,
                pending=pending,
                pending_surface=pending_surface,
                pending_per_source=pending_per_source,
                stats=stats,
            )
            pending.clear()
            pending_surface.clear()
            pending_per_source.clear()
            log.info("yf.extractor.scan_progress", articles=stats.articles_seen)

    if pending:
        await _flush(
            session,
            pending=pending,
            pending_surface=pending_surface,
            pending_per_source=pending_per_source,
            stats=stats,
        )

    log.info(
        "yf.extractor.scan_done",
        articles=stats.articles_seen,
        inserted=stats.entities_inserted,
        updated=stats.entities_updated,
    )
    return stats


def _join_meta(raw: dict | None) -> str:
    if not raw:
        return ""
    parts = []
    if raw.get("title"):
        parts.append(str(raw["title"]))
    if raw.get("description"):
        parts.append(str(raw["description"]))
    return ". ".join(parts)


async def _flush(
    session: AsyncSession,
    *,
    pending: dict[tuple[str, str], int],
    pending_surface: dict[tuple[str, str], str],
    pending_per_source: dict[tuple[str, str, int], int],
    stats: ScanStats,
) -> None:
    """UPSERT entities + entity_source_counts."""
    if not pending:
        return

    # 1) Upsert entities (incrementa occurrence_count)
    rows = [
        {
            "surface_form": pending_surface[(norm, ntype)],
            "normalized": norm,
            "ner_type": ntype,
            "occurrence_count": cnt,
        }
        for (norm, ntype), cnt in pending.items()
    ]
    stmt = pg_insert(Entity).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_entities_normalized_ner_type",
        set_={
            "occurrence_count": Entity.occurrence_count + stmt.excluded.occurrence_count,
            "last_seen_at": func.now(),
        },
    ).returning(Entity.id, Entity.normalized, Entity.ner_type)
    result = await session.execute(stmt)
    rows_returned = result.all()
    id_by_key: dict[tuple[str, str], int] = {
        (str(r[1]), str(r[2])): int(r[0]) for r in rows_returned
    }
    # `entities_updated` qui include sia primi insert che update successivi:
    # i due casi non si distinguono senza un trucco Postgres-only (xmax) e per
    # l'output del CLI non è informazione critica.
    stats.entities_updated += len(rows_returned)

    # 2) Upsert entity_source_counts (incrementa count)
    src_rows = []
    for (norm, ntype, source_id), cnt in pending_per_source.items():
        eid = id_by_key.get((norm, ntype))
        if eid is None:
            continue
        src_rows.append(
            {"entity_id": eid, "source_id": source_id, "count": cnt}
        )
    if src_rows:
        s_stmt = pg_insert(EntitySourceCount).values(src_rows)
        s_stmt = s_stmt.on_conflict_do_update(
            constraint="pk_entity_source_counts",
            set_={"count": EntitySourceCount.count + s_stmt.excluded.count},
        )
        await session.execute(s_stmt)
        stats.source_counts_updated += len(src_rows)


# ---------------------------------------------------------------------------
# Review: top candidate non risolti, con segnale su sub-token già conosciuti
# ---------------------------------------------------------------------------


async def review_top(
    session: AsyncSession,
    *,
    ner_type: str | None = None,
    min_count: int = 5,
    limit: int = 50,
) -> list[ReviewItem]:
    stmt = (
        select(
            Entity.id,
            Entity.surface_form,
            Entity.normalized,
            Entity.ner_type,
            Entity.occurrence_count,
            select(func.count())
            .select_from(EntitySourceCount)
            .where(EntitySourceCount.entity_id == Entity.id)
            .scalar_subquery()
            .label("sources_count"),
        )
        .where(Entity.topic_id.is_(None))
        .where(Entity.ignored.is_(False))
        .where(Entity.occurrence_count >= min_count)
    )
    if ner_type is not None:
        stmt = stmt.where(Entity.ner_type == ner_type)
    stmt = stmt.order_by(Entity.occurrence_count.desc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    # Calcola sub-token map per i topic già curati
    topics = (
        await session.execute(
            select(Topic.display_name, Topic.aliases, Topic.type).where(
                Topic.is_curated.is_(True)
            )
        )
    ).all()
    known: dict[str, str] = {}
    for display_name, aliases, t_type in topics:
        if display_name:
            known[display_name.lower()] = t_type
        for a in aliases or []:
            if a:
                known[a.lower()] = t_type

    out: list[ReviewItem] = []
    for r in rows:
        eid, surface, norm, ntype, occ, sources_count = r
        sub_hits: list[tuple[str, str]] = []
        for tok in surface.split():
            tok_clean = tok.strip(".,;:").lower()
            if tok_clean and tok_clean in known:
                sub_hits.append((tok_clean, known[tok_clean]))
        out.append(
            ReviewItem(
                entity_id=int(eid),
                surface_form=surface,
                normalized=norm,
                ner_type=ntype,
                occurrence_count=int(occ),
                sources_count=int(sources_count or 0),
                subtoken_topics=sub_hits,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Confirm: promuove entity → topic
# ---------------------------------------------------------------------------


async def confirm_entity(
    session: AsyncSession,
    *,
    entity_id: int,
    as_type: str,
    display_name: str | None = None,
) -> Topic:
    """Crea un Topic curated dalla entity e linka entity.topic_id.

    `as_type` ∈ {brand, person, location, model, subject, ...}.
    Se `display_name` non è specificato, usa `entity.surface_form`.
    """
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise ValueError(f"entity {entity_id} non trovata")

    name = display_name or entity.surface_form
    slug = slugify(name)
    if not slug:
        raise ValueError(f"slug vuoto per '{name}'")

    # Riusa Topic esistente se presente (caso: entity è alias di topic noto)
    existing = (
        await session.execute(select(Topic).where(Topic.slug == slug))
    ).scalar_one_or_none()

    if existing is not None:
        # Aggiunge surface_form come alias se non già presente
        aliases = list(existing.aliases or [])
        if entity.surface_form not in aliases and entity.surface_form != existing.display_name:
            aliases.append(entity.surface_form)
            existing.aliases = aliases
        existing.is_curated = True
        topic = existing
    else:
        topic = Topic(
            type=as_type,
            slug=slug,
            display_name=name,
            aliases=[],
            is_curated=True,
        )
        session.add(topic)
        await session.flush()

    entity.topic_id = topic.id
    await session.flush()
    log.info(
        "yf.extractor.confirm",
        entity_id=entity_id,
        topic_id=topic.id,
        type=as_type,
    )
    return topic


async def reject_entity(session: AsyncSession, *, entity_id: int) -> None:
    await session.execute(
        update(Entity).where(Entity.id == entity_id).values(ignored=True)
    )
    log.info("yf.extractor.reject", entity_id=entity_id)


async def known_brand_names(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(
            select(Topic.display_name, Topic.aliases)
            .where(Topic.type == "brand")
            .where(Topic.is_curated.is_(True))
        )
    ).all()
    out: list[str] = []
    for display_name, aliases in rows:
        if display_name:
            out.append(display_name)
        for a in aliases or []:
            if a:
                out.append(a)
    return out


# Ri-export per il CLI
__all__ = [
    "ReviewItem",
    "ScanStats",
    "confirm_entity",
    "known_brand_names",
    "reject_entity",
    "review_top",
    "scan_articles",
]


# Funzione helper non usata ma riferita per type-check pulito su Iterable
_ = (Candidate, extract_models, Iterable)
