"""Servizio bookmark (saved articles).

Operations:
- `add(db, user_id, article_id)` — INSERT idempotente (no errore se già salvato).
- `remove(db, user_id, article_id)` — DELETE; ritorna True se esisteva.
- `list_for_user(db, user_id, limit, offset)` — pagina di articoli salvati,
  in formato TimelineRow per riusare `articles_service.to_list_item`.
- `ids_for_user(db, user_id, article_ids)` — subset dei `article_ids` che
  risultano bookmarked dall'utente. Pensato per il bulk check sulle card
  della timeline (frontend invia gli id correnti, riceve l'overlay).
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Article, ArticleBookmark
from app.services.articles_service import TimelineRow, _hydrate_topics


async def add(db: AsyncSession, *, user_id: int, article_id: int) -> bool:
    """Idempotente: ON CONFLICT DO NOTHING. Ritorna True se inserito."""
    stmt = (
        pg_insert(ArticleBookmark)
        .values(user_id=user_id, article_id=article_id)
        .on_conflict_do_nothing(index_elements=["user_id", "article_id"])
        .returning(ArticleBookmark.article_id)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none() is not None


async def remove(db: AsyncSession, *, user_id: int, article_id: int) -> bool:
    res = await db.execute(
        ArticleBookmark.__table__.delete()
        .where(
            and_(
                ArticleBookmark.user_id == user_id,
                ArticleBookmark.article_id == article_id,
            )
        )
        .returning(ArticleBookmark.article_id)
    )
    return res.scalar_one_or_none() is not None


async def list_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    limit: int = 30,
    offset: int = 0,
) -> list[tuple[TimelineRow, "object"]]:
    """Ritorna `[(TimelineRow, created_at)]` ordinati per created_at DESC."""
    bm_stmt = (
        select(ArticleBookmark)
        .where(ArticleBookmark.user_id == user_id)
        .order_by(ArticleBookmark.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    bookmarks = list((await db.execute(bm_stmt)).scalars().all())
    if not bookmarks:
        return []

    art_ids = [int(b.article_id) for b in bookmarks]
    art_stmt = (
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.id.in_(art_ids))
    )
    articles_by_id = {
        int(a.id): a for a in (await db.execute(art_stmt)).scalars().all()
    }
    topics_by_id = await _hydrate_topics(db, art_ids)

    out: list[tuple[TimelineRow, object]] = []
    for b in bookmarks:
        a = articles_by_id.get(int(b.article_id))
        if a is None:
            continue  # articolo eliminato (CASCADE già pulisce, ma race-safe)
        row = TimelineRow(
            article=a, source=a.source, topics=topics_by_id.get(int(a.id), [])
        )
        out.append((row, b.created_at))
    return out


async def ids_for_user(
    db: AsyncSession, *, user_id: int, article_ids: list[int]
) -> set[int]:
    if not article_ids:
        return set()
    res = await db.execute(
        select(ArticleBookmark.article_id)
        .where(ArticleBookmark.user_id == user_id)
        .where(ArticleBookmark.article_id.in_(article_ids))
    )
    return {int(r) for r in res.scalars().all()}
