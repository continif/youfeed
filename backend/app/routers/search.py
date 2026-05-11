"""Full-text search via Manticore (v1.1.D).

Endpoints:
- `GET /yf_search?q=...&limit=N&offset=M`  — risultati paginati con snippet
- `GET /yf_search/suggest?q=...`           — autocomplete topic + sources

Auth-aware: utente loggato → filtra alle sue `user_sources` (timeline-
coherent). Anonimo → cerca su tutto il corpus indicizzato.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.auth_deps import CurrentUserOptional
from app.deps import DB
from app.schemas.search import SearchOut, SearchResultItem, SuggestOut
from app.services import articles_service, search_service
from app.services.articles_service import TimelineRow

router = APIRouter(prefix="/yf_search", tags=["search"])


@router.get("", response_model=SearchOut)
async def search(
    db: DB,
    user: CurrentUserOptional,
    q: str = Query("", min_length=0, max_length=200, description="Query full-text"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000),
) -> SearchOut:
    user_id = int(user.id) if user is not None else None
    hits, total = await search_service.search(
        db, query=q, user_id=user_id, limit=limit, offset=offset,
    )

    # Color map (solo se loggato + ho almeno un hit, per evitare query inutile)
    color_map: dict[int, str | None] = {}
    if user is not None and hits:
        color_map = await articles_service.fetch_source_to_color(
            db, user_id=int(user.id),
            source_ids=[int(h.source.id) for h in hits],
        )

    items: list[SearchResultItem] = []
    for h in hits:
        row = TimelineRow(article=h.article, source=h.source, topics=h.topics)
        base = articles_service.to_list_item(
            row, category_color=color_map.get(int(h.source.id))
        )
        base["highlights"] = h.highlights
        items.append(SearchResultItem(**base))
    return SearchOut(
        items=items, total=total, limit=limit, offset=offset, query=q.strip(),
    )


@router.get("/suggest", response_model=SuggestOut)
async def suggest(
    db: DB,
    q: str = Query("", min_length=0, max_length=80, description="Prefix per autocomplete"),
    limit: int = Query(default=8, ge=1, le=20),
) -> SuggestOut:
    data = await search_service.suggest(db, prefix=q, limit=limit)
    return SuggestOut(**data)
