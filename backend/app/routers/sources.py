"""Endpoint sources: lista utente, link/unlink, featured gallery.

`POST /yf_sources/discover` (creazione di nuove `Source`) è in un router
separato — vedi `app.routers.discovery` (Phase 8).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.auth_deps import CurrentUser
from app.deps import DB
from app.schemas.sources import (
    FeaturedSourceItem,
    FeaturedSourcesOut,
    SourceOut,
    UserSourceCreateIn,
    UserSourceListOut,
    UserSourceOut,
    UserSourceUpdateIn,
)
from app.services import source_service

# Due router: uno utente-only sotto /yf_me, uno pubblico sotto /yf_sources
me_router = APIRouter(prefix="/yf_me/sources", tags=["sources"])
public_router = APIRouter(prefix="/yf_sources", tags=["sources"])


# ---------------------------------------------------------------------------
# /yf_me/sources
# ---------------------------------------------------------------------------


@me_router.get("", response_model=UserSourceListOut)
async def list_my_sources(user: CurrentUser, db: DB) -> UserSourceListOut:
    items = await source_service.list_user_sources(db, user)
    return UserSourceListOut(
        items=[UserSourceOut.model_validate(us) for us in items]
    )


@me_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=UserSourceOut
)
async def add_source(
    payload: UserSourceCreateIn, user: CurrentUser, db: DB
) -> UserSourceOut:
    us = await source_service.add_user_source(
        db,
        user=user,
        source_id=payload.source_id,
        category_id=payload.category_id,
        custom_title=payload.custom_title,
    )
    await db.commit()
    # Re-load con relazioni per la response
    items = await source_service.list_user_sources(db, user)
    refreshed = next((x for x in items if x.id == us.id), us)
    return UserSourceOut.model_validate(refreshed)


@me_router.patch("/{user_source_id}", response_model=UserSourceOut)
async def patch_source(
    user_source_id: int,
    payload: UserSourceUpdateIn,
    user: CurrentUser,
    db: DB,
) -> UserSourceOut:
    set_fields = payload.model_fields_set
    us = await source_service.update_user_source(
        db,
        user=user,
        user_source_id=user_source_id,
        category_id=payload.category_id,
        custom_title=payload.custom_title,
        custom_title_set="custom_title" in set_fields,
    )
    await db.commit()
    items = await source_service.list_user_sources(db, user)
    refreshed = next((x for x in items if x.id == us.id), us)
    return UserSourceOut.model_validate(refreshed)


@me_router.delete("/{user_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(user_source_id: int, user: CurrentUser, db: DB) -> None:
    await source_service.remove_user_source(
        db, user=user, user_source_id=user_source_id
    )
    await db.commit()


# ---------------------------------------------------------------------------
# /yf_sources/featured (pubblico, no auth richiesta)
# ---------------------------------------------------------------------------


@public_router.get("/featured", response_model=FeaturedSourcesOut)
async def featured_gallery(db: DB) -> FeaturedSourcesOut:
    grouped = await source_service.list_featured_grouped(db)

    out: dict[str, list[FeaturedSourceItem]] = {}
    for hint, items in grouped.items():
        out[hint] = [
            FeaturedSourceItem(
                source_id=fs.source_id,
                display_name=fs.display_name,
                description=fs.description,
                position=fs.position,
                source=SourceOut.model_validate(src),
            )
            for fs, src in items
        ]
    return FeaturedSourcesOut(by_category=out)
