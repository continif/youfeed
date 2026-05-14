"""Pannello admin (`/yf_admin/*`) — gestione utenti, topic, articoli, regole.

HTTP Basic auth via `ADMIN_USERNAME` + `ADMIN_PASSWORD` in `.env`.
Tutto server-rendered Jinja2 (no SPA): un solo bookmark, no build step.

Rotte (Phase 1):
  GET  /yf_admin/                       dashboard
  GET  /yf_admin/users                  lista utenti
  GET  /yf_admin/topics                 lista topic
  GET  /yf_admin/topics/{id}            edit topic (form)
  POST /yf_admin/topics/{id}            salva edit
  POST /yf_admin/topics/{id}/delete     elimina topic
  GET  /yf_admin/articles               redirect a articles/{id} via form
  GET  /yf_admin/articles/{id}          ispeziona articolo + topic
  GET  /yf_admin/stats                  statistiche topic
  GET  /yf_admin/rules                  viewer regole (Phase 1: read-only)

Rotte (Phase 2 — rules CRUD):
  GET  /yf_admin/rules/{kind}/new       form add regola
  POST /yf_admin/rules/{kind}           crea regola
  POST /yf_admin/rules/{kind}/{id}/delete  elimina regola
  POST /yf_admin/rules/reload           invalida cache classify
  GET  /yf_admin/composite              lista composite rules
  GET  /yf_admin/composite/new          form add composite
  POST /yf_admin/composite              crea composite
  POST /yf_admin/composite/{id}/delete  elimina composite
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.admin_deps import require_admin
from app.deps import DB
from app.ingestion import classify
from app.utils.slugify import slugify
from app.models import (
    Article,
    ArticleTopic,
    AuthSession,
    BlockedAsn,
    BlockedCountry,
    Entity,
    FeaturedSource,
    Source,
    Topic,
    TopicCompositeRule,
    TopicTermRule,
    User,
)
from app.db import get_session_factory
from app.security import block_cache, countries as security_countries, events_store as security_events_store

log = structlog.get_logger()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _asset_version(rel_path: str) -> str:
    """mtime del file in static/ come query string — cache-bust automatico
    quando il file cambia (no purge Cloudflare/browser manuale)."""
    try:
        return str(int((_STATIC_DIR / rel_path).stat().st_mtime))
    except OSError:
        return "0"


_templates.env.globals["asset_version"] = _asset_version


def _format_unix_ts(ts: int | float | None) -> str:
    """Filtro Jinja per formattare timestamp Unix (es. eventi SQLite block_events)."""
    if ts is None:
        return "—"
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    try:
        return _dt.fromtimestamp(float(ts), tz=_tz.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return str(ts)


_templates.env.filters["datetime"] = _format_unix_ts


router = APIRouter(
    prefix="/yf_admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def dashboard(request: Request, db: DB) -> Response:
    counts = {
        "users": await _count(db, User),
        "articles": await _count(db, Article),
        "sources": await _count(db, Source),
        "topics": await _count(db, Topic),
        "topics_curated": (
            await db.execute(select(func.count(Topic.id)).where(Topic.is_curated.is_(True)))
        ).scalar(),
        "topics_non_curated": (
            await db.execute(select(func.count(Topic.id)).where(Topic.is_curated.is_(False)))
        ).scalar(),
        "article_topics": (
            await db.execute(select(func.count()).select_from(ArticleTopic))
        ).scalar() or 0,
    }
    return _templates.TemplateResponse(
        request, "admin/dashboard.html", {"counts": counts}
    )


# ---------------------------------------------------------------------------
# Utenti
# ---------------------------------------------------------------------------


@router.get("/users")
async def users_list(
    request: Request,
    db: DB,
    q: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Response:
    stmt = select(User).order_by(desc(User.id))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like)))
    total = (
        await db.execute(
            select(func.count(User.id)).where(
                or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
            )
            if q
            else select(func.count(User.id))
        )
    ).scalar()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    # Last login: prendi MAX(AuthSession.last_seen_at) per ogni user_id mostrato.
    last_logins: dict[int, Any] = {}
    if rows:
        last_login_rows = (
            await db.execute(
                select(AuthSession.user_id, func.max(AuthSession.last_seen_at))
                .where(AuthSession.user_id.in_([u.id for u in rows]))
                .group_by(AuthSession.user_id)
            )
        ).all()
        last_logins = {r[0]: r[1] for r in last_login_rows}

    return _templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "users": rows,
            "last_logins": last_logins,
            "q": q,
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    )


# ---------------------------------------------------------------------------
# Topic
# ---------------------------------------------------------------------------


@router.get("/topics")
async def topics_list(
    request: Request,
    db: DB,
    q: str = "",
    type_: str = Query(default="", alias="type"),
    is_curated: str = "",  # "1" | "0" | "" (any)
    limit: int = 50,
    offset: int = 0,
) -> Response:
    where = []
    if q:
        like = f"%{q}%"
        where.append(or_(Topic.display_name.ilike(like), Topic.slug.ilike(like)))
    if type_:
        # Filtro esplicito sul tipo: include 'invalid' se richiesto.
        where.append(Topic.type == type_)
    else:
        # Default: nascondi i topic 'invalid' (blacklist), per non sporcare
        # la review dei topic auto-extracted. Per vederli, filtra su type=invalid.
        where.append(Topic.type != "invalid")
    if is_curated == "1":
        where.append(Topic.is_curated.is_(True))
    elif is_curated == "0":
        where.append(Topic.is_curated.is_(False))

    base = select(Topic)
    count_q = select(func.count(Topic.id))
    for w in where:
        base = base.where(w)
        count_q = count_q.where(w)

    total = (await db.execute(count_q)).scalar()
    rows = (
        await db.execute(base.order_by(desc(Topic.id)).limit(limit).offset(offset))
    ).scalars().all()

    # Conteggio articoli per topic (solo per i topic mostrati, batch)
    article_counts: dict[int, int] = {}
    if rows:
        cnt_rows = (
            await db.execute(
                select(ArticleTopic.topic_id, func.count(ArticleTopic.article_id))
                .where(ArticleTopic.topic_id.in_([t.id for t in rows]))
                .group_by(ArticleTopic.topic_id)
            )
        ).all()
        article_counts = {r[0]: r[1] for r in cnt_rows}

    return _templates.TemplateResponse(
        request,
        "admin/topics.html",
        {
            "topics": rows,
            "article_counts": article_counts,
            "q": q,
            "type_": type_,
            "is_curated": is_curated,
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    )


@router.post("/topics/bulk")
async def topics_bulk(
    db: DB,
    action: str = Form(...),
    ids: list[int] = Form(default=[]),
    return_to: str = Form(""),
) -> Response:
    """Bulk action sui topic selezionati nella list page:
    - action='validate'   → set is_curated=true (whitelist)
    - action='invalidate' → set type='invalid' + cancella article_topics; il
      topic resta in tabella così l'extractor (on_conflict_do_nothing su slug)
      lo riconosce e skippa l'associazione invece di ricreare il topic ad ogni
      ingestion.

    NOTA: deve stare PRIMA di `/topics/{topic_id}` perché FastAPI risolve in
    ordine di registrazione e `bulk` non è un int.
    """
    if not ids:
        target = return_to if return_to.startswith("/yf_admin/") else "/yf_admin/topics"
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    if action == "validate":
        await db.execute(
            update(Topic).where(Topic.id.in_(ids)).values(is_curated=True)
        )
        log.info("yf.admin.topics_bulk_validate", count=len(ids))
        # Accoda enrichment Wikidata best-effort (saltato per topic già con qid)
        try:
            from app.workers.enrich import enqueue_enrich_wikidata

            for tid in ids:
                enqueue_enrich_wikidata(int(tid))
        except Exception as e:
            log.debug("yf.admin.enrich_enqueue_failed", error=str(e))
    elif action == "invalidate":
        # Cancella prima le associazioni: topic invalid non deve più apparire
        # sui feed pubblici. Poi marca il topic così future ingestion lo
        # ignorano (vedi `_upsert_regex_topic` e `_load_index`).
        await db.execute(
            delete(ArticleTopic).where(ArticleTopic.topic_id.in_(ids))
        )
        await db.execute(
            update(Topic)
            .where(Topic.id.in_(ids))
            .values(type="invalid", is_curated=False)
        )
        log.info("yf.admin.topics_bulk_invalidate", count=len(ids))
    else:
        raise HTTPException(status_code=400, detail=f"Action '{action}' non supportata")
    await db.commit()
    classify.invalidate_classifier_cache()
    target = return_to if return_to.startswith("/yf_admin/") else "/yf_admin/topics"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


_VALID_TOPIC_TYPES = (
    "brand",
    "person",
    "subject",
    "location",
    "model",
    "company",
    "organization",
    "software",
    "hardware",
    "event",
    "work",
)


@router.post("/topics/create")
async def topic_create(
    db: DB,
    display_name: str = Form(...),
    type_: str = Form(..., alias="type"),
    aliases: str = Form(""),
) -> Response:
    """Crea un nuovo topic curato a partire dal form sulla list page.

    Slug auto-generato via `slugify(display_name)`. Se uno con stesso slug
    esiste già: lo promuove a curated + aggiorna type/aliases (idempotente).

    NOTA: deve stare PRIMA di `/topics/{topic_id}` perché FastAPI risolve in
    ordine di registrazione.
    """
    name = display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="display_name vuoto")
    if type_ not in _VALID_TOPIC_TYPES:
        raise HTTPException(status_code=400, detail=f"type '{type_}' non valido")
    slug = slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="slug derivato vuoto")
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()]

    existing = (await db.execute(select(Topic).where(Topic.slug == slug))).scalar_one_or_none()
    if existing is None:
        await db.execute(pg_insert(Topic).values(
            type=type_, slug=slug, display_name=name,
            aliases=alias_list, description=None, external_refs=None, is_curated=True,
        ).on_conflict_do_nothing(index_elements=["slug"]))
        tid = (await db.execute(select(Topic.id).where(Topic.slug == slug))).scalar()
        log.info("yf.admin.topic_created", topic_id=tid, slug=slug, type=type_)
    else:
        merged = list(existing.aliases or [])
        for a in alias_list:
            if a not in merged:
                merged.append(a)
        await db.execute(update(Topic).where(Topic.id == existing.id).values(
            type=type_, display_name=name, is_curated=True, aliases=merged,
        ))
        tid = existing.id
        log.info("yf.admin.topic_upserted", topic_id=tid, slug=slug, type=type_)
    await db.commit()
    classify.invalidate_classifier_cache()
    # Auto-enrich Wikidata best-effort (skip se già ha qid)
    if tid is not None:
        try:
            from app.workers.enrich import enqueue_enrich_wikidata

            enqueue_enrich_wikidata(int(tid))
        except Exception as e:
            log.debug("yf.admin.enrich_enqueue_failed", error=str(e))
    return RedirectResponse(
        url=f"/yf_admin/topics/{tid}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/topics/{topic_id}")
async def topic_edit_form(
    request: Request, db: DB, topic_id: int
) -> Response:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic non trovato")
    article_count = (
        await db.execute(
            select(func.count(ArticleTopic.article_id)).where(
                ArticleTopic.topic_id == topic_id
            )
        )
    ).scalar()
    # Top 10 articoli che usano questo topic
    sample_articles = (
        await db.execute(
            select(Article, ArticleTopic.score)
            .join(ArticleTopic, ArticleTopic.article_id == Article.id)
            .where(ArticleTopic.topic_id == topic_id)
            .order_by(desc(ArticleTopic.score))
            .limit(10)
        )
    ).all()
    return _templates.TemplateResponse(
        request,
        "admin/topic_edit.html",
        {
            "topic": topic,
            "article_count": article_count,
            "sample_articles": [(a, s) for a, s in sample_articles],
        },
    )


@router.post("/topics/{topic_id}")
async def topic_save(
    db: DB,
    topic_id: int,
    display_name: str = Form(...),
    type_: str = Form(..., alias="type"),
    aliases: str = Form(""),
    is_curated: str = Form(""),
    description: str = Form(""),
) -> Response:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404)
    topic.display_name = display_name.strip()
    topic.type = type_.strip()
    # aliases textarea: una per riga
    topic.aliases = [
        line.strip() for line in aliases.splitlines() if line.strip()
    ] or []
    topic.is_curated = is_curated == "1"
    topic.description = description.strip() or None
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.topic_saved", topic_id=topic_id, slug=topic.slug)
    return RedirectResponse(
        url=f"/yf_admin/topics/{topic_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/topics/{topic_id}/delete")
async def topic_delete(db: DB, topic_id: int) -> Response:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404)
    slug = topic.slug
    # Usa DELETE statement (non `db.delete(topic)`): la relationship Topic
    # → ArticleTopic non ha cascade ORM e proverebbe a SET NULL il PK
    # `article_topics.topic_id` (NOT NULL). La FK ha già `ON DELETE CASCADE`
    # a livello DB, quindi un DELETE diretto fa scattare la cascade.
    await db.execute(delete(Topic).where(Topic.id == topic_id))
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.topic_deleted", topic_id=topic_id, slug=slug)
    return RedirectResponse(url="/yf_admin/topics", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Articoli (inspector)
# ---------------------------------------------------------------------------


@router.get("/articles")
async def articles_redirect(article_id: int = 0) -> Response:
    if article_id:
        return RedirectResponse(
            url=f"/yf_admin/articles/{article_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    raise HTTPException(status_code=400, detail="article_id mancante")


@router.get("/articles/{article_id}")
async def article_inspect(
    request: Request, db: DB, article_id: int
) -> Response:
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    source = await db.get(Source, article.source_id)
    rows = (
        await db.execute(
            select(Topic, ArticleTopic.score, ArticleTopic.source, ArticleTopic.position)
            .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
            .where(ArticleTopic.article_id == article_id)
            .order_by(desc(ArticleTopic.score))
        )
    ).all()
    topics = [
        {"topic": t, "score": s, "source": src, "position": pos}
        for t, s, src, pos in rows
    ]
    return _templates.TemplateResponse(
        request,
        "admin/article.html",
        {"article": article, "source": source, "topics": topics},
    )


# ---------------------------------------------------------------------------
# Statistiche
# ---------------------------------------------------------------------------


@router.get("/stats")
async def stats(request: Request, db: DB) -> Response:
    by_type = (
        await db.execute(
            select(Topic.type, func.count(Topic.id)).group_by(Topic.type).order_by(desc(func.count(Topic.id)))
        )
    ).all()
    top50 = (
        await db.execute(
            select(Topic, func.count(ArticleTopic.article_id).label("n"))
            .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
            .group_by(Topic.id)
            .order_by(desc("n"))
            .limit(50)
        )
    ).all()
    orphans = (
        await db.execute(
            select(func.count(Topic.id)).where(
                ~Topic.id.in_(select(ArticleTopic.topic_id).distinct())
            )
        )
    ).scalar()
    by_source = (
        await db.execute(
            select(ArticleTopic.source, func.count(ArticleTopic.article_id))
            .group_by(ArticleTopic.source)
            .order_by(desc(func.count(ArticleTopic.article_id)))
        )
    ).all()
    return _templates.TemplateResponse(
        request,
        "admin/stats.html",
        {
            "by_type": by_type,
            "top50": [(t, n) for t, n in top50],
            "orphans": orphans,
            "by_source": by_source,
        },
    )


# ---------------------------------------------------------------------------
# Regole (term rules + composite rules) — admin-editabili
# ---------------------------------------------------------------------------


_RULE_KINDS = {
    "ambiguous_location": (
        "Comuni IT ambigui",
        "Termini lowercase esclusi dal dict-match per topic location: il comune "
        "esiste ma collide con un sostantivo italiano comune (es. 'mira', 'fondi').",
    ),
    "brand_single": (
        "Blacklist BRAND_SINGLE / PERSON edge",
        "Termini Title Case esclusi da REGEX_BRAND_SINGLE e dal trim head/tail "
        "di REGEX_PER (avverbi, voci verbali, sostantivi generici).",
    ),
    "case_sensitive_slug": (
        "Slug case-sensitive",
        "Topic il cui display_name matcha solo se in Title Case esatto "
        "(es. 'lancia' = brand auto solo Title Case, lowercase = verbo).",
    ),
}

# URL slug → DB kind. Tieni le slug brevi/parlanti per la nav admin.
_RULE_SLUG_TO_KIND: dict[str, str] = {
    "ambigui": "ambiguous_location",
    "blacklist": "brand_single",
    "case-sensitive": "case_sensitive_slug",
}
_RULE_KIND_TO_SLUG: dict[str, str] = {v: k for k, v in _RULE_SLUG_TO_KIND.items()}


@router.get("/rules")
async def rules_index(request: Request) -> Response:
    """Redirect alla prima sezione: la pagina /yf_admin/rules unica è stata
    splittata in 3 viste separate (una per kind)."""
    return RedirectResponse(
        url="/yf_admin/rules/ambigui", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/rules/{rule_slug}")
async def rules_list(request: Request, db: DB, rule_slug: str) -> Response:
    kind = _RULE_SLUG_TO_KIND.get(rule_slug)
    if kind is None:
        raise HTTPException(status_code=404, detail=f"sezione '{rule_slug}' non valida")
    rows = (
        await db.execute(
            select(TopicTermRule)
            .where(TopicTermRule.kind == kind)
            .order_by(TopicTermRule.term)
        )
    ).scalars().all()
    label, descr = _RULE_KINDS[kind]
    # Sezioni per la nav: lista (slug, label, kind, attivo)
    sections = [
        (slug, _RULE_KINDS[k][0], k, slug == rule_slug)
        for slug, k in _RULE_SLUG_TO_KIND.items()
    ]
    return _templates.TemplateResponse(
        request,
        "admin/rules.html",
        {
            "rule_slug": rule_slug,
            "kind": kind,
            "label": label,
            "descr": descr,
            "rules": rows,
            "sections": sections,
            "total": len(rows),
        },
    )


@router.post("/rules")
async def rule_create(
    db: DB,
    kind: str = Form(...),
    term: str = Form(...),
    note: str = Form(""),
) -> Response:
    if kind not in _RULE_KINDS:
        raise HTTPException(status_code=400, detail=f"kind '{kind}' non valido")
    term = term.strip()
    if not term:
        raise HTTPException(status_code=400, detail="term vuoto")
    # Per ambiguous_location forziamo lowercase (il match è case-insensitive).
    if kind == "ambiguous_location":
        term = term.lower()
    stmt = pg_insert(TopicTermRule).values(
        kind=kind,
        term=term,
        note=note.strip() or None,
    ).on_conflict_do_nothing(index_elements=["kind", "term"])
    await db.execute(stmt)
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.rule_created", kind=kind, term=term)
    target = f"/yf_admin/rules/{_RULE_KIND_TO_SLUG.get(kind, 'ambigui')}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/rules/{rule_id}/delete")
async def rule_delete(db: DB, rule_id: int) -> Response:
    rule = await db.get(TopicTermRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404)
    kind = rule.kind
    await db.delete(rule)
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.rule_deleted", rule_id=rule_id, kind=kind, term=rule.term)
    target = f"/yf_admin/rules/{_RULE_KIND_TO_SLUG.get(kind, 'ambigui')}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Composite rules — sinonimi/associazioni (Google + Gemini → Google Gemini)
# ---------------------------------------------------------------------------


@router.get("/composite")
async def composite_list(request: Request, db: DB) -> Response:
    rows = (
        await db.execute(
            select(TopicCompositeRule).order_by(TopicCompositeRule.composite_slug)
        )
    ).scalars().all()
    # Per ogni regola, verifica esistenza topic composite e components in DB
    all_slugs: set[str] = set()
    for r in rows:
        all_slugs.add(r.composite_slug)
        for c in r.components:
            all_slugs.add(c)
    existing = {
        row.slug: row.id
        for row in (
            await db.execute(select(Topic).where(Topic.slug.in_(all_slugs)))
        ).scalars().all()
    }
    return _templates.TemplateResponse(
        request,
        "admin/composite.html",
        {"rules": rows, "existing_slugs": existing},
    )


@router.post("/composite")
async def composite_create(
    db: DB,
    composite_slug: str = Form(...),
    components: str = Form(...),
    note: str = Form(""),
) -> Response:
    composite_slug = composite_slug.strip()
    components_list = [
        line.strip() for line in components.replace(",", "\n").splitlines() if line.strip()
    ]
    if not composite_slug or len(components_list) < 2:
        raise HTTPException(
            status_code=400,
            detail="composite_slug e almeno 2 components richiesti",
        )
    stmt = pg_insert(TopicCompositeRule).values(
        composite_slug=composite_slug,
        components=components_list,
        note=note.strip() or None,
    ).on_conflict_do_nothing(index_elements=["composite_slug"])
    await db.execute(stmt)
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info(
        "yf.admin.composite_created",
        composite_slug=composite_slug,
        components=components_list,
    )
    return RedirectResponse(
        url="/yf_admin/composite", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/composite/{rule_id}/delete")
async def composite_delete(db: DB, rule_id: int) -> Response:
    rule = await db.get(TopicCompositeRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404)
    await db.delete(rule)
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.composite_deleted", rule_id=rule_id, slug=rule.composite_slug)
    return RedirectResponse(
        url="/yf_admin/composite", status_code=status.HTTP_303_SEE_OTHER
    )


# ---------------------------------------------------------------------------
# Entità non risolte (Phase 1.2.F)
# ---------------------------------------------------------------------------

_ENTITY_NER_TO_TOPIC_TYPE = {
    "PER": "person",
    "REGEX_PER": "person",
    "REGEX_POPE": "person",
    "ORG": "brand",
    "REGEX_BRAND_ALPHA": "brand",
    "REGEX_BRAND_SINGLE": "brand",
    "LOC": "location",
    "REGEX_MODEL": "model",
    "MISC": "subject",
}


@router.get("/entities")
async def entities_list(
    request: Request,
    db: DB,
    min_count: int = Query(default=2, ge=1, le=1000),
    ner_type: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Response:
    """Entità grezze non ancora risolte (topic_id IS NULL, ignored=false),
    ordinate per `occurrence_count DESC`. L'admin può promuoverle a topic,
    collegarle a un topic esistente, o ignorarle."""
    where = [Entity.topic_id.is_(None), Entity.ignored.is_(False), Entity.occurrence_count >= min_count]
    if ner_type:
        where.append(Entity.ner_type == ner_type)

    res = await db.execute(
        select(Entity).where(*where).order_by(Entity.occurrence_count.desc()).limit(limit)
    )
    rows = res.scalars().all()

    types_res = await db.execute(
        select(Entity.ner_type, func.count(Entity.id))
        .where(Entity.topic_id.is_(None), Entity.ignored.is_(False))
        .group_by(Entity.ner_type)
        .order_by(Entity.ner_type)
    )
    type_counts = list(types_res.all())

    return _templates.TemplateResponse(
        request,
        "admin/entities.html",
        {
            "entities": rows,
            "type_counts": type_counts,
            "filters": {"min_count": min_count, "ner_type": ner_type, "limit": limit},
        },
    )


@router.post("/entities/{entity_id}/promote")
async def entity_promote(
    db: DB,
    entity_id: int,
    type_: str = Form(default="", alias="type"),
    return_to: str = Form(""),
) -> Response:
    """Crea un nuovo Topic curato a partire da una Entity, e collega la entity
    al nuovo topic (`entities.topic_id = new_topic.id`).

    `type_` se non passato è derivato da `ner_type` via mapping.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity non trovata")

    topic_type = (type_ or _ENTITY_NER_TO_TOPIC_TYPE.get(entity.ner_type, "subject")).strip()
    if topic_type not in _VALID_TOPIC_TYPES:
        raise HTTPException(status_code=400, detail=f"type '{topic_type}' non valido")

    name = entity.surface_form.strip() or entity.normalized.strip()
    if not name:
        raise HTTPException(status_code=400, detail="surface_form vuoto")
    slug = slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="slug vuoto")

    existing = (
        await db.execute(select(Topic).where(Topic.slug == slug))
    ).scalar_one_or_none()
    if existing is None:
        await db.execute(
            pg_insert(Topic).values(
                type=topic_type,
                slug=slug,
                display_name=name,
                aliases=[],
                description=None,
                external_refs=None,
                is_curated=True,
            ).on_conflict_do_nothing(index_elements=["slug"])
        )
        tid = (await db.execute(select(Topic.id).where(Topic.slug == slug))).scalar()
    else:
        tid = existing.id
        await db.execute(
            update(Topic).where(Topic.id == tid).values(is_curated=True, type=topic_type)
        )

    entity.topic_id = tid
    await db.commit()
    classify.invalidate_classifier_cache()

    # Auto-enrich Wikidata best-effort
    try:
        from app.workers.enrich import enqueue_enrich_wikidata

        enqueue_enrich_wikidata(int(tid))
    except Exception:
        pass

    log.info(
        "yf.admin.entity_promoted",
        entity_id=entity_id,
        topic_id=tid,
        type=topic_type,
        slug=slug,
    )
    target = return_to if return_to.startswith("/yf_admin/") else "/yf_admin/entities"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/entities/{entity_id}/link")
async def entity_link(
    db: DB,
    entity_id: int,
    topic_id: int = Form(...),
    return_to: str = Form(""),
) -> Response:
    """Collega una Entity a un Topic esistente (`entities.topic_id = topic_id`)."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity non trovata")
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic non trovato")
    entity.topic_id = topic_id
    await db.commit()
    classify.invalidate_classifier_cache()
    log.info("yf.admin.entity_linked", entity_id=entity_id, topic_id=topic_id)
    target = return_to if return_to.startswith("/yf_admin/") else "/yf_admin/entities"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/entities/{entity_id}/ignore")
async def entity_ignore(
    db: DB, entity_id: int, return_to: str = Form("")
) -> Response:
    """Marca l'entity come ignorata: non apparirà più nella list view."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity non trovata")
    entity.ignored = True
    await db.commit()
    log.info("yf.admin.entity_ignored", entity_id=entity_id)
    target = return_to if return_to.startswith("/yf_admin/") else "/yf_admin/entities"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Featured sources (Phase 1.2.F)
# ---------------------------------------------------------------------------


@router.get("/featured")
async def featured_list(request: Request, db: DB) -> Response:
    """Lista featured_sources con i metadati della Source agganciata."""
    res = await db.execute(
        select(FeaturedSource, Source)
        .join(Source, Source.id == FeaturedSource.source_id)
        .order_by(FeaturedSource.position.asc(), FeaturedSource.source_id.asc())
    )
    rows = [{"featured": f, "source": s} for f, s in res.all()]
    return _templates.TemplateResponse(
        request, "admin/featured.html", {"items": rows}
    )


@router.post("/featured")
async def featured_add(
    db: DB,
    source_id: int = Form(...),
    category_hint: str = Form(""),
    display_name: str = Form(""),
    description: str = Form(""),
    position: int = Form(default=0),
) -> Response:
    """Aggiunge una Source a featured_sources. Idempotente via PK source_id."""
    src = await db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Source non trovata")

    await db.execute(
        pg_insert(FeaturedSource).values(
            source_id=source_id,
            category_hint=category_hint.strip() or None,
            display_name=display_name.strip() or None,
            description=description.strip() or None,
            position=position,
        ).on_conflict_do_update(
            index_elements=["source_id"],
            set_={
                "category_hint": category_hint.strip() or None,
                "display_name": display_name.strip() or None,
                "description": description.strip() or None,
                "position": position,
            },
        )
    )
    await db.commit()
    log.info("yf.admin.featured_upserted", source_id=source_id)
    return RedirectResponse(url="/yf_admin/featured", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/featured/{source_id}/delete")
async def featured_delete(db: DB, source_id: int) -> Response:
    await db.execute(delete(FeaturedSource).where(FeaturedSource.source_id == source_id))
    await db.commit()
    log.info("yf.admin.featured_deleted", source_id=source_id)
    return RedirectResponse(url="/yf_admin/featured", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Sources (con filtro status) (Phase 1.2.F)
# ---------------------------------------------------------------------------


@router.get("/sources")
async def sources_list(
    request: Request,
    db: DB,
    status_filter: str = Query(default="broken", alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Response:
    """Lista sources con filtro su status. Default su `broken` per evidenziare
    le fonti che richiedono intervento manuale (>= 3 fallimenti consecutivi)."""
    stmt = select(Source).order_by(Source.consecutive_failures.desc(), Source.id.asc()).limit(limit)
    if status_filter and status_filter != "all":
        stmt = stmt.where(Source.status == status_filter)

    res = await db.execute(stmt)
    sources = list(res.scalars().all())

    # Distribuzione status per pillole filtro
    dist_res = await db.execute(
        select(Source.status, func.count(Source.id)).group_by(Source.status).order_by(Source.status)
    )
    distribution = list(dist_res.all())

    return _templates.TemplateResponse(
        request,
        "admin/sources.html",
        {
            "sources": sources,
            "distribution": distribution,
            "filter_status": status_filter,
        },
    )


@router.post("/sources/{source_id}/reset-failures")
async def source_reset_failures(db: DB, source_id: int) -> Response:
    """Reset di consecutive_failures + status a 'active'. Utile dopo aver
    risolto manualmente il problema della fonte."""
    res = await db.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(consecutive_failures=0, status="active")
        .returning(Source.id)
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Source non trovata")
    await db.commit()
    log.info("yf.admin.source_reset", source_id=source_id)
    return RedirectResponse(url="/yf_admin/sources", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Reload cache (dopo edit manuali al DB o per forzare refresh)
# ---------------------------------------------------------------------------


@router.post("/cache/reload")
async def cache_reload() -> Response:
    classify.invalidate_classifier_cache()
    log.info("yf.admin.cache_reload")
    return RedirectResponse(url="/yf_admin/", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Security: blocked countries + ASN + event log
# ---------------------------------------------------------------------------


@router.get("/security/blocks")
async def security_blocks_list(request: Request, db: DB) -> Response:
    """Liste blocked_countries + blocked_asns + form di aggiunta inline.

    Carica anche l'elenco completo dei country dal MMDB per popolare il
    `<select>` di aggiunta (così l'admin sceglie da menù invece di scrivere
    l'ISO-2 a memoria). Lookup `iso_code → name` per la tabella corrente.
    """
    countries = (
        await db.execute(select(BlockedCountry).order_by(BlockedCountry.iso_code))
    ).scalars().all()
    asns = (
        await db.execute(select(BlockedAsn).order_by(BlockedAsn.asn))
    ).scalars().all()
    all_countries = security_countries.list_countries()
    name_by_iso = dict(all_countries)
    blocked_iso = {c.iso_code for c in countries}
    return _templates.TemplateResponse(
        request,
        "admin/security_blocks.html",
        {
            "countries": list(countries),
            "asns": list(asns),
            "all_countries": all_countries,
            "name_by_iso": name_by_iso,
            "blocked_iso": blocked_iso,
        },
    )


def _safe_redirect(return_to: str | None, default: str) -> str:
    """Solo path interni (`/yf_admin/...`). Niente redirect su host esterni."""
    if return_to and return_to.startswith("/yf_admin/"):
        return return_to
    # Se ci arriva una URL assoluta dalla stessa origin (request.url), accettala
    # ma riduci al path-only per evitare open-redirect.
    if return_to and "://" in return_to:
        from urllib.parse import urlparse
        parsed = urlparse(return_to)
        if parsed.path.startswith("/yf_admin/"):
            return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return default


@router.post("/security/blocks/countries")
async def security_block_country_add(
    db: DB,
    iso_code: str = Form(...),
    note: str = Form(default=""),
    return_to: str = Form(default=""),
) -> Response:
    iso = iso_code.strip().upper()
    if len(iso) != 2 or not iso.isalpha():
        raise HTTPException(status_code=400, detail="iso_code deve essere 2 lettere")
    stmt = pg_insert(BlockedCountry).values(iso_code=iso, note=note.strip() or None)
    stmt = stmt.on_conflict_do_nothing(index_elements=["iso_code"])
    await db.execute(stmt)
    await db.commit()
    await block_cache.invalidate(get_session_factory())
    log.info("yf.admin.security.country_blocked", iso_code=iso)
    return RedirectResponse(
        url=_safe_redirect(return_to, "/yf_admin/security/blocks"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/security/blocks/countries/{iso_code}/delete")
async def security_block_country_delete(
    db: DB, iso_code: str, return_to: str = Form(default="")
) -> Response:
    iso = iso_code.strip().upper()
    await db.execute(delete(BlockedCountry).where(BlockedCountry.iso_code == iso))
    await db.commit()
    await block_cache.invalidate(get_session_factory())
    log.info("yf.admin.security.country_unblocked", iso_code=iso)
    return RedirectResponse(
        url=_safe_redirect(return_to, "/yf_admin/security/blocks"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/security/blocks/asns")
async def security_block_asn_add(
    db: DB,
    asn: int = Form(...),
    note: str = Form(default=""),
    return_to: str = Form(default=""),
) -> Response:
    if asn <= 0:
        raise HTTPException(status_code=400, detail="asn deve essere > 0")
    stmt = pg_insert(BlockedAsn).values(asn=asn, note=note.strip() or None)
    stmt = stmt.on_conflict_do_nothing(index_elements=["asn"])
    await db.execute(stmt)
    await db.commit()
    await block_cache.invalidate(get_session_factory())
    log.info("yf.admin.security.asn_blocked", asn=asn)
    return RedirectResponse(
        url=_safe_redirect(return_to, "/yf_admin/security/blocks"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/security/blocks/asns/{asn}/delete")
async def security_block_asn_delete(
    db: DB, asn: int, return_to: str = Form(default="")
) -> Response:
    await db.execute(delete(BlockedAsn).where(BlockedAsn.asn == asn))
    await db.commit()
    await block_cache.invalidate(get_session_factory())
    log.info("yf.admin.security.asn_unblocked", asn=asn)
    return RedirectResponse(
        url=_safe_redirect(return_to, "/yf_admin/security/blocks"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/security/events")
async def security_events_list(
    request: Request,
    db: DB,
    country: str = Query(default=""),
    asn: str = Query(default=""),
    ip: str = Query(default=""),
    reason: str = Query(default=""),
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Response:
    """Eventi 403 recenti, filtrabili. Finestra temporale in ore.

    `asn` arriva come stringa per consentire empty-string dai form GET
    (un `int | None = None` rifiuterebbe `asn=` con un 422).
    """
    import time as _time
    asn_int: int | None = None
    asn_clean = asn.strip()
    if asn_clean:
        try:
            asn_int = int(asn_clean)
        except ValueError:
            raise HTTPException(status_code=400, detail="asn deve essere un intero")
    since_ts = int(_time.time()) - hours * 3600
    events = await security_events_store.list_events(
        country=country.strip().upper() or None,
        asn=asn_int,
        ip=ip.strip() or None,
        reason=reason.strip() or None,
        since_ts=since_ts,
        limit=limit,
    )
    total = await security_events_store.total_count(since_ts)
    # Per disabilitare i bottoni "Blocca" sulle righe il cui country/ASN è già
    # in blacklist (e per mostrare il nome country accanto al codice).
    blocked_countries_iso = set(
        (await db.execute(select(BlockedCountry.iso_code))).scalars().all()
    )
    blocked_asn_ids = set(
        int(a) for a in (await db.execute(select(BlockedAsn.asn))).scalars().all()
    )
    name_by_iso = dict(security_countries.list_countries())
    # return_to preserva i filtri correnti quando l'admin clicca "Blocca …"
    return_to = str(request.url)
    return _templates.TemplateResponse(
        request,
        "admin/security_events.html",
        {
            "events": events,
            "total": total,
            "filters": {
                "country": country,
                "asn": asn_int,
                "ip": ip,
                "reason": reason,
                "hours": hours,
                "limit": limit,
            },
            "blocked_countries_iso": blocked_countries_iso,
            "blocked_asn_ids": blocked_asn_ids,
            "name_by_iso": name_by_iso,
            "return_to": return_to,
        },
    )


@router.get("/security/stats")
async def security_stats(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
) -> Response:
    """Aggregati top-N per country/ASN/IP/path negli ultimi N giorni."""
    import time as _time
    since_ts = int(_time.time()) - days * 86400
    top_countries = await security_events_store.aggregate(
        group_by="country", since_ts=since_ts, limit=20
    )
    top_asns = await security_events_store.aggregate(
        group_by="asn", since_ts=since_ts, limit=20
    )
    top_ips = await security_events_store.aggregate(
        group_by="ip", since_ts=since_ts, limit=20
    )
    top_paths = await security_events_store.aggregate(
        group_by="path", since_ts=since_ts, limit=20
    )
    total = await security_events_store.total_count(since_ts)
    return _templates.TemplateResponse(
        request,
        "admin/security_stats.html",
        {
            "days": days,
            "total": total,
            "top_countries": top_countries,
            "top_asns": top_asns,
            "top_ips": top_ips,
            "top_paths": top_paths,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count(db: DB, model: Any) -> int:
    return (await db.execute(select(func.count(model.id)))).scalar() or 0
