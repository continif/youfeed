"""Servizio categorie: tree fetch + CRUD con vincoli alberatura."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import Category, User
from app.utils.slugify import slugify

_HEX_COLOR_RE = r"^#[0-9A-Fa-f]{6}$"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def list_user_categories(session: AsyncSession, user: User) -> list[Category]:
    res = await session.execute(
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(Category.parent_id.nulls_first(), Category.position)
    )
    return list(res.scalars().all())


def to_tree(categories: list[Category]) -> list[dict[str, Any]]:
    """Trasforma una flat list in tree (root → children → ...)."""
    by_id: dict[int, dict[str, Any]] = {
        c.id: {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "parent_id": c.parent_id,
            "position": c.position,
            "color": c.color,
            "is_public": c.is_public,
            "children": [],
        }
        for c in categories
    }
    roots: list[dict[str, Any]] = []
    for c in categories:
        node = by_id[c.id]
        if c.parent_id is None:
            roots.append(node)
        else:
            parent = by_id.get(c.parent_id)
            if parent is not None:
                parent["children"].append(node)
    return roots


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


async def _generate_unique_slug(
    session: AsyncSession,
    *,
    user_id: int,
    parent_id: int | None,
    base: str,
    exclude_id: int | None = None,
) -> str:
    """Slug unico nel namespace (user_id, parent_id, slug)."""
    base_slug = slugify(base) or "categoria"
    slug = base_slug
    n = 2
    while True:
        q = select(Category.id).where(
            Category.user_id == user_id,
            Category.parent_id.is_(parent_id) if parent_id is None else Category.parent_id == parent_id,
            Category.slug == slug,
        )
        if exclude_id is not None:
            q = q.where(Category.id != exclude_id)
        existing = (await session.execute(q)).scalar_one_or_none()
        if existing is None:
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


async def _validate_parent(
    session: AsyncSession, *, user: User, parent_id: int | None
) -> None:
    if parent_id is None:
        return
    parent = await session.get(Category, parent_id)
    if parent is None or parent.user_id != user.id:
        raise NotFoundError("Categoria padre non trovata.", code="parent_not_found")


def _validate_color(color: str | None) -> str | None:
    if color is None:
        return None
    import re

    if not re.match(_HEX_COLOR_RE, color):
        from app.services.auth_service import ValidationError

        raise ValidationError(
            "invalid_color", "Colore deve essere un esadecimale a 6 cifre tipo '#3b82f6'."
        )
    return color.lower()


async def create_category(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    parent_id: int | None = None,
    color: str | None = None,
) -> Category:
    name = name.strip()
    if not name:
        from app.services.auth_service import ValidationError

        raise ValidationError("invalid_name", "Il nome categoria non può essere vuoto.")
    if len(name) > 120:
        from app.services.auth_service import ValidationError

        raise ValidationError("invalid_name", "Nome troppo lungo (max 120 caratteri).")

    color = _validate_color(color)
    await _validate_parent(session, user=user, parent_id=parent_id)
    slug = await _generate_unique_slug(
        session, user_id=user.id, parent_id=parent_id, base=name
    )

    # Posizione di default: in fondo al livello corrente
    pos_q = select(Category.position).where(
        Category.user_id == user.id,
        Category.parent_id.is_(parent_id) if parent_id is None else Category.parent_id == parent_id,
    )
    res = await session.execute(pos_q)
    positions = [row[0] for row in res.all()]
    next_pos = max(positions, default=-1) + 1

    cat = Category(
        user_id=user.id,
        parent_id=parent_id,
        name=name,
        slug=slug,
        position=next_pos,
        color=color,
    )
    session.add(cat)
    await session.flush()
    return cat


async def update_category(
    session: AsyncSession,
    *,
    user: User,
    category_id: int,
    name: str | None = None,
    parent_id: int | None = None,
    parent_id_set: bool = False,
    color: str | None = None,
    color_set: bool = False,
    position: int | None = None,
    is_public: bool | None = None,
) -> Category:
    cat = await session.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise NotFoundError("Categoria non trovata.", code="category_not_found")

    if name is not None:
        n = name.strip()
        if not n:
            from app.services.auth_service import ValidationError

            raise ValidationError("invalid_name", "Il nome non può essere vuoto.")
        cat.name = n
        # Rigenera lo slug solo se il nome è cambiato
        cat.slug = await _generate_unique_slug(
            session,
            user_id=user.id,
            parent_id=cat.parent_id,
            base=n,
            exclude_id=cat.id,
        )

    if parent_id_set:
        # Vincoli: niente self-loop, niente loop ciclici
        if parent_id == cat.id:
            raise ConflictError(
                "Una categoria non può essere figlia di sé stessa.",
                code="invalid_parent",
            )
        if parent_id is not None:
            # Verifica che il nuovo parent non sia un discendente di cat
            await _ensure_not_descendant(session, user.id, ancestor_id=cat.id, candidate_id=parent_id)
            await _validate_parent(session, user=user, parent_id=parent_id)
        cat.parent_id = parent_id
        # Rigenera slug se il namespace è cambiato
        cat.slug = await _generate_unique_slug(
            session,
            user_id=user.id,
            parent_id=parent_id,
            base=cat.name,
            exclude_id=cat.id,
        )

    if color_set:
        cat.color = _validate_color(color)

    if position is not None:
        cat.position = position

    if is_public is not None:
        cat.is_public = is_public

    await session.flush()
    return cat


async def _ensure_not_descendant(
    session: AsyncSession,
    user_id: int,
    *,
    ancestor_id: int,
    candidate_id: int,
) -> None:
    """Solleva errore se `candidate_id` è discendente di `ancestor_id`."""
    current_id: int | None = candidate_id
    visited: set[int] = set()
    while current_id is not None:
        if current_id in visited:
            return  # protezione contro cicli pre-esistenti
        visited.add(current_id)
        if current_id == ancestor_id:
            raise ConflictError(
                "Sposterebbe la categoria sotto un suo discendente (loop).",
                code="cycle_in_tree",
            )
        node = await session.get(Category, current_id)
        if node is None or node.user_id != user_id:
            return
        current_id = node.parent_id


async def delete_category(
    session: AsyncSession, *, user: User, category_id: int
) -> None:
    cat = await session.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise NotFoundError("Categoria non trovata.", code="category_not_found")
    if cat.user_id != user.id:
        raise ForbiddenError("Non puoi eliminare una categoria di un altro utente.")
    # ON DELETE CASCADE su user_sources e su categorie figlie
    await session.delete(cat)
    await session.flush()
