"""Endpoint categorie utente (`/yf_me/categories`)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.auth_deps import CurrentUser
from app.deps import DB
from app.exceptions import AppError
from app.schemas.categories import (
    CategoryCreateIn,
    CategoryOut,
    CategoryTreeOut,
    CategoryUpdateIn,
)
from app.services import category_service
from app.services.auth_service import ValidationError

router = APIRouter(prefix="/yf_me/categories", tags=["categories"])


def _wrap_validation(e: ValidationError) -> AppError:
    return AppError(e.message, code=e.code, status_code=422)


@router.get("", response_model=CategoryTreeOut)
async def list_categories(user: CurrentUser, db: DB) -> CategoryTreeOut:
    items = await category_service.list_user_categories(db, user)
    tree = category_service.to_tree(items)
    # `to_tree` ritorna list[dict] — Pydantic valida via `CategoryNode.model_validate`
    from app.schemas.categories import CategoryNode

    return CategoryTreeOut(tree=[CategoryNode.model_validate(n) for n in tree])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CategoryOut)
async def create_category(
    payload: CategoryCreateIn, user: CurrentUser, db: DB
) -> CategoryOut:
    try:
        cat = await category_service.create_category(
            db,
            user=user,
            name=payload.name,
            parent_id=payload.parent_id,
            color=payload.color,
        )
    except ValidationError as e:
        raise _wrap_validation(e) from e

    await db.commit()
    return CategoryOut.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    payload: CategoryUpdateIn,
    user: CurrentUser,
    db: DB,
) -> CategoryOut:
    set_fields = payload.model_fields_set
    try:
        cat = await category_service.update_category(
            db,
            user=user,
            category_id=category_id,
            name=payload.name,
            parent_id=payload.parent_id,
            parent_id_set="parent_id" in set_fields,
            color=payload.color,
            color_set="color" in set_fields,
            position=payload.position,
            is_public=payload.is_public,
        )
    except ValidationError as e:
        raise _wrap_validation(e) from e

    await db.commit()
    return CategoryOut.model_validate(cat)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, user: CurrentUser, db: DB) -> None:
    await category_service.delete_category(db, user=user, category_id=category_id)
    await db.commit()
