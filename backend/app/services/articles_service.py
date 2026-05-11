"""Servizio articoli: timeline (utente loggato + pubblica) e dettaglio.

La timeline è una query relativamente semplice su Postgres: prende gli
articoli delle sources iscritte (per utente loggato) o di tutte le sources
di un utente (vista pubblica), filtra per `published_at`, applica cursore
keyset.

Il dettaglio articolo recupera anche `content_html` da Manticore.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.ingestion import manticore_client
from app.models import (
    Article,
    ArticleTopic,
    Category,
    Source,
    Topic,
    UserSource,
)


@dataclass
class TimelineRow:
    article: Article
    source: Source
    topics: list[Topic]


# ---------------------------------------------------------------------------
# Cursor keyset (published_at, id) -> stringa opaca base64
# ---------------------------------------------------------------------------


def _encode_cursor(published_at: datetime, article_id: int) -> str:
    raw = f"{published_at.isoformat()}|{article_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), int(id_str)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Timeline query helpers
# ---------------------------------------------------------------------------


async def _hydrate_topics(
    session: AsyncSession, article_ids: list[int]
) -> dict[int, list[Topic]]:
    if not article_ids:
        return {}
    stmt = (
        select(ArticleTopic.article_id, Topic)
        .join(Topic, Topic.id == ArticleTopic.topic_id)
        .where(ArticleTopic.article_id.in_(article_ids))
        .order_by(ArticleTopic.score.desc())
    )
    rows = (await session.execute(stmt)).all()
    out: dict[int, list[Topic]] = {}
    for art_id, topic in rows:
        out.setdefault(int(art_id), []).append(topic)
    return out


async def _query_timeline(
    session: AsyncSession,
    *,
    source_ids_subq: Any,
    cursor: str | None,
    limit: int,
    topic_id: int | None = None,
) -> list[TimelineRow]:
    cur = _decode_cursor(cursor) if cursor else None

    stmt = (
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.source_id.in_(source_ids_subq))
        .where(Article.processing_status == "indexed")
    )
    if topic_id is not None:
        # EXISTS subquery — più efficiente di JOIN+DISTINCT su article_topics
        topic_subq = (
            select(ArticleTopic.article_id)
            .where(ArticleTopic.article_id == Article.id)
            .where(ArticleTopic.topic_id == topic_id)
        )
        stmt = stmt.where(topic_subq.exists())
    if cur is not None:
        cur_ts, cur_id = cur
        stmt = stmt.where(
            or_(
                Article.published_at < cur_ts,
                and_(Article.published_at == cur_ts, Article.id < cur_id),
            )
        )
    stmt = stmt.order_by(Article.published_at.desc(), Article.id.desc()).limit(limit)

    articles = (await session.execute(stmt)).scalars().all()
    if not articles:
        return []

    topics_by_id = await _hydrate_topics(session, [int(a.id) for a in articles])
    return [
        TimelineRow(
            article=a,
            source=a.source,
            topics=topics_by_id.get(int(a.id), []),
        )
        for a in articles
    ]


async def timeline_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    cursor: str | None = None,
    limit: int = 30,
    category_id: int | None = None,
    topic_id: int | None = None,
) -> tuple[list[TimelineRow], str | None]:
    """Timeline dell'utente loggato: articoli delle sue user_sources.

    Se `category_id` è specificato, filtra ulteriormente sulle user_sources
    che appartengono alla categoria o alle sue sotto-categorie (BFS in-app
    sull'albero categorie utente — v1.0 ha solo 2 livelli, niente cicli).

    Se `topic_id` è specificato, filtra agli articoli che hanno quel topic
    in `article_topics` (independent dal filter category).
    """
    subq = select(UserSource.source_id).where(UserSource.user_id == user_id)
    if category_id is not None:
        cat_ids = await _descendant_category_ids(
            session, user_id=user_id, root_id=category_id
        )
        if not cat_ids:
            return [], None
        subq = subq.where(UserSource.category_id.in_(cat_ids))
    rows = await _query_timeline(
        session,
        source_ids_subq=subq,
        cursor=cursor,
        limit=limit,
        topic_id=topic_id,
    )
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1].article
        next_cursor = _encode_cursor(last.published_at, int(last.id))
    return rows, next_cursor


async def _descendant_category_ids(
    session: AsyncSession, *, user_id: int, root_id: int
) -> list[int]:
    """Ritorna [root_id] + tutti i discendenti per l'utente. Si appoggia su
    `Category.parent_id`. Verifica che la categoria appartenga all'utente
    (security: evita di filtrare su categorie altrui)."""
    root = (
        await session.execute(
            select(Category).where(
                Category.id == root_id, Category.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if root is None:
        return []
    # BFS: 2 livelli max in v1.0, ma il loop generale funziona anche con N.
    out: list[int] = [int(root.id)]
    frontier: list[int] = [int(root.id)]
    while frontier:
        children = (
            await session.execute(
                select(Category.id)
                .where(Category.user_id == user_id)
                .where(Category.parent_id.in_(frontier))
            )
        ).all()
        frontier = [int(r[0]) for r in children]
        out.extend(frontier)
    return out


async def timeline_for_public_user(
    session: AsyncSession,
    *,
    target_user_id: int,
    cursor: str | None = None,
    limit: int = 30,
) -> tuple[list[TimelineRow], str | None]:
    """Timeline pubblica del profilo `/{username}` — solo sources rese pubbliche."""
    # In v1.0 la "pubblicità" del feed è a livello categoria (Category.is_public).
    # Filtra le UserSource che hanno una category con is_public=True.
    from app.models import Category

    subq = (
        select(UserSource.source_id)
        .join(Category, Category.id == UserSource.category_id)
        .where(UserSource.user_id == target_user_id)
        .where(Category.is_public == True)  # noqa: E712
    )
    rows = await _query_timeline(
        session, source_ids_subq=subq, cursor=cursor, limit=limit
    )
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1].article
        next_cursor = _encode_cursor(last.published_at, int(last.id))
    return rows, next_cursor


async def timeline_global_public(
    session: AsyncSession,
    *,
    limit: int = 12,
) -> list[TimelineRow]:
    """Vetrina pubblica per la home: ultimi articoli aggregati da TUTTE le
    categorie pubbliche di TUTTI gli utenti. Niente cursor (fixed-size feed
    pensato per la landing). DISTINCT a livello di source_id nel subquery
    evita duplicati quando più utenti pubblicano la stessa source."""
    from app.models import Category

    subq = (
        select(UserSource.source_id)
        .join(Category, Category.id == UserSource.category_id)
        .where(Category.is_public == True)  # noqa: E712
        .distinct()
    )
    return await _query_timeline(
        session, source_ids_subq=subq, cursor=None, limit=limit
    )


# ---------------------------------------------------------------------------
# Dettaglio articolo (con content_html da Manticore)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TF-IDF dei topic per "related_articles"
#
# Peso del topic t = log(N_articoli / N_articoli_con_t). Topic raro = peso
# alto. Cache module-level con fallback alla mediana per topic non visti.
# Invalidata da `invalidate_topic_idf_cache()` (chiamata dagli admin write
# che cambiano massicciamente le associazioni article_topics).
# ---------------------------------------------------------------------------

_IDF_CACHE: dict[int, float] | None = None
_IDF_FALLBACK: float = 1.0  # mediana al primo build, usata per topic ignoti


def invalidate_topic_idf_cache() -> None:
    """Forza il rebuild della tabella IDF al prossimo `related_articles`.
    Da chiamare dopo bulk update di `article_topics` (riclassificazione,
    moderazione admin)."""
    global _IDF_CACHE, _IDF_FALLBACK
    _IDF_CACHE = None
    _IDF_FALLBACK = 1.0


async def _load_topic_idf(session: AsyncSession) -> tuple[dict[int, float], float]:
    """Costruisce (e cachea) la mappa topic_id → IDF.

    Algoritmo classico: idf(t) = log(N / df(t)) dove N è il numero di
    articoli (indexed) con almeno un topic, e df(t) è il numero di articoli
    che contengono il topic t. Smoothing minimo: max(1, df) e max(0, idf).
    """
    global _IDF_CACHE, _IDF_FALLBACK
    if _IDF_CACHE is not None:
        return _IDF_CACHE, _IDF_FALLBACK
    n_total = (
        await session.execute(
            select(func.count(func.distinct(ArticleTopic.article_id)))
        )
    ).scalar() or 1
    rows = (
        await session.execute(
            select(
                ArticleTopic.topic_id,
                func.count(func.distinct(ArticleTopic.article_id)),
            ).group_by(ArticleTopic.topic_id)
        )
    ).all()
    idf: dict[int, float] = {}
    for tid, df in rows:
        df = max(1, int(df))
        idf[int(tid)] = max(0.0, math.log(n_total / df))
    # Fallback per topic ignoti (es. nuovi inseriti dopo il build): usa la
    # mediana, così non penalizza né favorisce a priori.
    if idf:
        sorted_w = sorted(idf.values())
        mid = len(sorted_w) // 2
        _IDF_FALLBACK = sorted_w[mid] if len(sorted_w) % 2 else (
            (sorted_w[mid - 1] + sorted_w[mid]) / 2
        )
    _IDF_CACHE = idf
    return _IDF_CACHE, _IDF_FALLBACK


def _weight_sum(topic_ids: set[int], idf: dict[int, float], fallback: float) -> float:
    return sum(idf.get(tid, fallback) for tid in topic_ids)


async def related_articles(
    session: AsyncSession,
    *,
    article_id: int,
    days_window: int = 15,
    min_overlap: float = 0.4,
    # Soglie sull'intersezione (in OR con min_overlap):
    # - se 1 solo topic comune: il suo peso deve essere ≥ `strong_single_min`
    #   (topic specifico, es. un model/person rari)
    # - se ≥ 2 topic comuni: la somma pesi ≥ `min_inter_weight` (basta un mix)
    strong_single_min: float = 4.0,
    min_inter_weight: float = 3.0,
    formula: str = "coverage",
    limit: int = 20,
) -> list[tuple[TimelineRow, float]]:
    """Articoli "simili" all'articolo sorgente (F-005, T-012-context).

    Criteri:
      - finestra temporale: published_at ∈ [src - days_window, src + days_window]
      - escluso l'articolo sorgente
      - solo `processing_status='indexed'`
      - overlap ≥ min_overlap secondo la formula scelta. Lo score usa pesi
        TF-IDF dei topic (vedi `_load_topic_idf`): un match su "Sony Xperia
        1 VIII" (raro) pesa molto più di un match su "Smartphone" (comune).
          * `coverage`: max(Σ idf(A∩B)/Σ idf(A), Σ idf(A∩B)/Σ idf(B))
                        — simmetrico, premia il lato meglio coperto (default)
          * `source`  : Σ idf(A∩B) / Σ idf(A)                  — copertura sul sorgente
          * `max`     : Σ idf(A∩B) / max(Σ idf(A), Σ idf(B))   — più severo
          * `jaccard` : Σ idf(A∩B) / Σ idf(A∪B)                — molto severo

    Ritorna lista di `(TimelineRow, overlap_score)` ordinata per overlap desc,
    poi per prossimità temporale asc.
    """
    from datetime import timedelta

    src = (
        await session.execute(
            select(Article).where(Article.id == article_id)
        )
    ).scalar_one_or_none()
    if src is None or src.published_at is None:
        return []

    src_topic_ids = (
        await session.execute(
            select(ArticleTopic.topic_id).where(ArticleTopic.article_id == article_id)
        )
    ).all()
    src_topic_set = {int(r[0]) for r in src_topic_ids}
    if not src_topic_set:
        return []

    # Carica pesi IDF (cache module-level)
    idf, fallback = await _load_topic_idf(session)
    src_weight = _weight_sum(src_topic_set, idf, fallback)
    if src_weight <= 0:
        return []

    # Candidati nella finestra temporale, indexed, con almeno 1 topic in comune.
    window_start = src.published_at - timedelta(days=days_window)
    window_end = src.published_at + timedelta(days=days_window)

    cand_query = (
        select(ArticleTopic.article_id, ArticleTopic.topic_id)
        .join(Article, Article.id == ArticleTopic.article_id)
        .where(Article.id != article_id)
        .where(Article.processing_status == "indexed")
        .where(Article.published_at.between(window_start, window_end))
        .where(ArticleTopic.topic_id.in_(src_topic_set))
    )
    cand_rows = (await session.execute(cand_query)).all()
    if not cand_rows:
        return []

    # Aggrega: candidate_id -> set di topic in comune
    inter_by_id: dict[int, set[int]] = {}
    for aid, tid in cand_rows:
        inter_by_id.setdefault(int(aid), set()).add(int(tid))

    # Recupera |B| per ciascun candidato (numero totale di topic).
    cand_ids = list(inter_by_id.keys())
    size_query = (
        select(ArticleTopic.article_id, ArticleTopic.topic_id)
        .where(ArticleTopic.article_id.in_(cand_ids))
    )
    size_rows = (await session.execute(size_query)).all()
    b_topics_by_id: dict[int, set[int]] = {}
    for aid, tid in size_rows:
        b_topics_by_id.setdefault(int(aid), set()).add(int(tid))

    # Calcolo overlap pesato TF-IDF secondo formula
    # `scored` = (aid, overlap, n_intersection): tripla per permettere
    # l'ordinamento primario per numero di topic in comune (più topic = più
    # forte la correlazione tematica) e secondario per coverage TF-IDF.
    scored: list[tuple[int, float, int]] = []
    for aid, inter_set in inter_by_id.items():
        inter_w = _weight_sum(inter_set, idf, fallback)
        # Anti-falsi-positivi: con `coverage` simmetrico anche un solo topic
        # in comune (es. "europa" w≈2, o un brand auto comune) può portare
        # score a 1.0. Richiedi o ≥2 topic comuni, o 1 ma raro (es. il model
        # specifico "Sony Xperia 1 VIII").
        if len(inter_set) == 1:
            if inter_w < strong_single_min:
                continue
        elif inter_w < min_inter_weight:
            continue
        b_set = b_topics_by_id.get(aid, set()) or set()
        b_w = _weight_sum(b_set, idf, fallback) or 1.0
        if formula == "source":
            overlap = inter_w / src_weight
        elif formula == "jaccard":
            union_w = src_weight + b_w - inter_w
            overlap = inter_w / union_w if union_w > 0 else 0.0
        elif formula == "max":
            overlap = inter_w / max(src_weight, b_w)
        else:  # default 'coverage' — simmetrico
            overlap = max(inter_w / src_weight, inter_w / b_w)
        if overlap >= min_overlap:
            scored.append((aid, overlap, len(inter_set)))

    if not scored:
        return []

    # Sort primary: numero di topic in comune (desc — più topic = più
    # specifica la correlazione, riduce il drift "stesso brand storia diversa").
    # Sort secondary: overlap TF-IDF coverage (desc).
    scored.sort(key=lambda x: (x[2], x[1]), reverse=True)
    top_ids = [aid for aid, _, _ in scored[: limit * 2]]  # buffer per stabilità

    # Hydrate articoli + topics per costruire TimelineRow
    art_query = (
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.id.in_(top_ids))
    )
    arts = {int(a.id): a for a in (await session.execute(art_query)).scalars().all()}
    topics_by_id = await _hydrate_topics(session, top_ids)

    # Re-ordina secondo lo scored e applica limit + tie-break temporale.
    # `count_by_id` serve nel sort finale per preservare il primato del
    # numero di topic in comune (vedi sort di `scored`).
    count_by_id = {aid: cnt for aid, _, cnt in scored}
    src_pub = src.published_at
    out: list[tuple[TimelineRow, float]] = []
    for aid, overlap, _ in scored[:limit]:
        a = arts.get(aid)
        if a is None:
            continue
        row = TimelineRow(
            article=a,
            source=a.source,
            topics=topics_by_id.get(aid, []),
        )
        out.append((row, overlap))
    # Sort finale: (n_topic_intersection desc, overlap desc, prossimità temporale).
    out.sort(
        key=lambda t: (
            -count_by_id.get(int(t[0].article.id), 0),
            -t[1],
            abs((t[0].article.published_at - src_pub).total_seconds())
            if t[0].article.published_at
            else 0,
        )
    )
    return out


async def get_article_detail(
    session: AsyncSession, *, article_id: int
) -> tuple[TimelineRow, dict[str, Any]] | None:
    """Ritorna (row, manticore_doc) o None se l'articolo non esiste."""
    stmt = (
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.id == article_id)
    )
    article = (await session.execute(stmt)).scalar_one_or_none()
    if article is None:
        return None

    topics_by_id = await _hydrate_topics(session, [int(article.id)])
    row = TimelineRow(
        article=article,
        source=article.source,
        topics=topics_by_id.get(int(article.id), []),
    )

    docs = await manticore_client.get_by_ids([int(article.id)])
    return row, docs.get(int(article.id), {})


# ---------------------------------------------------------------------------
# Conversione TimelineRow -> dict per Pydantic
# ---------------------------------------------------------------------------


def _public_image_url(image_local_path: str | None) -> str | None:
    if not image_local_path:
        return None
    settings = get_settings()
    prefix = settings.images_public_prefix.rstrip("/")
    return f"{prefix}/{image_local_path}"


def to_list_item(
    row: TimelineRow, *, category_color: str | None = None
) -> dict[str, Any]:
    """Adatta un TimelineRow al payload `ArticleListItem`.

    `category_color` è il colore della categoria con cui l'utente (loggato o
    target del profilo pubblico) ha linkato la source. None se la timeline è
    chiamata senza contesto utente.
    """
    a = row.article
    s = row.source
    image_local_url = _public_image_url(a.image_local_path)
    return {
        "id": int(a.id),
        "url_canonical": a.url_canonical,
        "title": (a.raw_meta_lite or {}).get("title", ""),
        "description": (a.raw_meta_lite or {}).get("description"),
        "image_url": a.image_url,
        "image_local_url": image_local_url,
        "image_width": a.image_width,
        "image_height": a.image_height,
        "author": a.author,
        "published_at": a.published_at,
        "category_color": category_color,
        "source": {
            "id": int(s.id),
            "title": s.title,
            "favicon_url": s.favicon_url,
            "url_site": s.url_site
            or (f"https://{urlparse(s.url_feed).netloc}" if s.url_feed else None),
        },
        "topics": [
            {
                "id": int(t.id),
                "slug": t.slug,
                "display_name": t.display_name,
                "type": t.type,
            }
            for t in row.topics
        ],
    }


async def fetch_source_to_color(
    session: AsyncSession, *, user_id: int, source_ids: list[int]
) -> dict[int, str | None]:
    """Mappa `source_id -> default_color` (hex `#rrggbb` o None) per le
    user_sources dell'utente. Pre-fetch in batch per evitare N+1 nel render
    della timeline."""
    if not source_ids:
        return {}
    stmt = (
        select(UserSource.source_id, Category.color)
        .join(Category, Category.id == UserSource.category_id)
        .where(UserSource.user_id == user_id)
        .where(UserSource.source_id.in_(source_ids))
    )
    rows = (await session.execute(stmt)).all()
    return {int(sid): color for sid, color in rows}


def to_detail(row: TimelineRow, manticore_doc: dict[str, Any]) -> dict[str, Any]:
    base = to_list_item(row)
    base["content_html"] = manticore_doc.get("content_html") or None
    base["content_text"] = manticore_doc.get("content_text") or None
    base["internal_links"] = row.article.internal_links or []
    return base
