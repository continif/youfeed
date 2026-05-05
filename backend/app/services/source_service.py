"""Servizio fonti utente.

`Source` è condivisa tra utenti (1 record per fonte distinta), `UserSource`
è la relazione N:1 con `Category`. La creazione di un `Source` nuovo passa
sempre dal flusso di **discovery** (Phase 8 — `POST /yf_sources/discover`).

Quindi:
  - POST /yf_me/sources accetta `source_id` esistente + `category_id`
  - PATCH /yf_me/sources/{id} cambia categoria/custom_title della relazione
  - DELETE /yf_me/sources/{id} rimuove solo la relazione utente, NON la
    `Source` globale (potrebbe essere usata da altri utenti)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictError, NotFoundError
from app.models import Category, FeaturedSource, Source, User, UserSource


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def list_user_sources(
    session: AsyncSession, user: User
) -> list[UserSource]:
    res = await session.execute(
        select(UserSource)
        .where(UserSource.user_id == user.id)
        .options(selectinload(UserSource.source), selectinload(UserSource.category))
        .order_by(UserSource.added_at.desc())
    )
    return list(res.scalars().all())


async def list_featured_grouped(
    session: AsyncSession,
) -> dict[str, list[tuple[FeaturedSource, Source]]]:
    """Ritorna fonti suggerite raggruppate per `category_hint`.

    Map: category_hint -> [(featured, source)] ordinati per position.
    """
    res = await session.execute(
        select(FeaturedSource, Source)
        .join(Source, Source.id == FeaturedSource.source_id)
        .order_by(FeaturedSource.category_hint, FeaturedSource.position)
    )
    grouped: dict[str, list[tuple[FeaturedSource, Source]]] = {}
    for fs, src in res.all():
        key = fs.category_hint or "_other"
        grouped.setdefault(key, []).append((fs, src))
    return grouped


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


async def _load_user_category(
    session: AsyncSession, *, user: User, category_id: int
) -> Category:
    cat = await session.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise NotFoundError("Categoria non trovata.", code="category_not_found")
    return cat


async def add_user_source(
    session: AsyncSession,
    *,
    user: User,
    source_id: int,
    category_id: int,
    custom_title: str | None = None,
) -> UserSource:
    # Categoria valida e dell'utente?
    await _load_user_category(session, user=user, category_id=category_id)

    # Source globale esistente e qualified?
    src = await session.get(Source, source_id)
    if src is None:
        raise NotFoundError("Fonte non trovata.", code="source_not_found")
    if src.kind == "invalid":
        raise ConflictError(
            "Questa fonte è marcata come non valida.", code="source_invalid"
        )

    us = UserSource(
        user_id=user.id,
        source_id=source_id,
        category_id=category_id,
        custom_title=custom_title.strip() if custom_title else None,
    )
    session.add(us)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        # Probabile uq_user_sources_user_source
        raise ConflictError(
            "Hai già aggiunto questa fonte.", code="source_already_added"
        ) from e
    return us


async def update_user_source(
    session: AsyncSession,
    *,
    user: User,
    user_source_id: int,
    category_id: int | None = None,
    custom_title: str | None = None,
    custom_title_set: bool = False,
) -> UserSource:
    us = await session.get(UserSource, user_source_id)
    if us is None or us.user_id != user.id:
        raise NotFoundError("Iscrizione non trovata.", code="user_source_not_found")

    if category_id is not None:
        await _load_user_category(session, user=user, category_id=category_id)
        us.category_id = category_id

    if custom_title_set:
        us.custom_title = custom_title.strip() if custom_title else None

    await session.flush()
    return us


async def remove_user_source(
    session: AsyncSession, *, user: User, user_source_id: int
) -> None:
    us = await session.get(UserSource, user_source_id)
    if us is None or us.user_id != user.id:
        raise NotFoundError("Iscrizione non trovata.", code="user_source_not_found")
    await session.delete(us)
    await session.flush()
