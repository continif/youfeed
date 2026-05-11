"""Endpoint articoli (timeline utente loggato + dettaglio singolo)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.auth_deps import CurrentUser
from app.deps import DB
from app.schemas.articles import (
    ArticleDetailOut,
    ArticleListItem,
    ArticleListOut,
    RelatedArticleItem,
    RelatedArticlesOut,
)
from app.services import articles_service

log = structlog.get_logger()

router = APIRouter(prefix="/yf_articles", tags=["articles"])


@router.get("/feed", response_model=ArticleListOut)
async def get_my_feed(
    user: CurrentUser,
    db: DB,
    cursor: str | None = Query(default=None, description="Cursore keyset opaco"),
    limit: int = Query(default=30, ge=1, le=100),
    category: int | None = Query(
        default=None,
        description="Filtra il feed agli articoli delle source linkate a questa "
        "categoria (e alle sue sotto-categorie).",
    ),
    topic: int | None = Query(
        default=None,
        description="Filtra il feed ai soli articoli che hanno questo topic.",
    ),
) -> ArticleListOut:
    """Timeline dell'utente loggato: articoli delle sue user_sources."""
    rows, next_cursor = await articles_service.timeline_for_user(
        db,
        user_id=int(user.id),
        cursor=cursor,
        limit=limit,
        category_id=category,
        topic_id=topic,
    )
    color_map = await articles_service.fetch_source_to_color(
        db, user_id=int(user.id), source_ids=[int(r.source.id) for r in rows]
    )
    items = [
        ArticleListItem.model_validate(
            articles_service.to_list_item(r, category_color=color_map.get(int(r.source.id)))
        )
        for r in rows
    ]
    return ArticleListOut(items=items, next_cursor=next_cursor)


@router.get("/{article_id}", response_model=ArticleDetailOut)
async def get_article(article_id: int, user: CurrentUser, db: DB) -> ArticleDetailOut:
    """Dettaglio articolo: include content_html da Manticore + category_color
    derivato dalla user_source dell'utente loggato (se l'articolo è in una
    sua source)."""
    result = await articles_service.get_article_detail(db, article_id=article_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article_not_found")
    row, manticore_doc = result
    color_map = await articles_service.fetch_source_to_color(
        db, user_id=int(user.id), source_ids=[int(row.source.id)]
    )
    detail = articles_service.to_detail(row, manticore_doc)
    detail["category_color"] = color_map.get(int(row.source.id))
    return ArticleDetailOut.model_validate(detail)


@router.get("/{article_id}/related", response_model=RelatedArticlesOut)
async def get_related_articles(
    article_id: int,
    user: CurrentUser,
    db: DB,
    days: int = Query(default=15, ge=1, le=90, description="Finestra temporale ±N giorni"),
    min_overlap: float = Query(
        default=0.4, ge=0.0, le=1.0,
        description="Soglia minima di overlap TF-IDF dei topic",
    ),
    formula: str = Query(
        default="coverage",
        pattern="^(coverage|source|max|jaccard)$",
        description=(
            "coverage=max(inter/A,inter/B) simmetrico (default), "
            "source=inter/A, max=inter/max(A,B), jaccard=inter/(A∪B). "
            "Tutti i conteggi sono pesati TF-IDF."
        ),
    ),
    limit: int = Query(default=20, ge=1, le=50),
) -> RelatedArticlesOut:
    """Ritorna gli articoli simili al `article_id` (F-005)."""
    pairs = await articles_service.related_articles(
        db,
        article_id=article_id,
        days_window=days,
        min_overlap=min_overlap,
        formula=formula,
        limit=limit,
    )
    color_map = await articles_service.fetch_source_to_color(
        db,
        user_id=int(user.id),
        source_ids=[int(row.source.id) for row, _ in pairs],
    )
    items = [
        RelatedArticleItem.model_validate(
            {
                **articles_service.to_list_item(
                    row, category_color=color_map.get(int(row.source.id))
                ),
                "overlap": overlap,
            }
        )
        for row, overlap in pairs
    ]
    return RelatedArticlesOut(
        items=items,
        formula=formula,
        min_overlap=min_overlap,
        days_window=days,
    )
