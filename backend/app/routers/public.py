"""Endpoint pubblici di profilo: timeline JSON + RSS export.

Servono il "profilo pubblico" `/{username}` (catch-all gestito dal frontend
Jinja2) e l'export RSS del feed pubblico:

  GET /yf_users/{username}/feed.json
  GET /yf_users/{username}/feed.rss

Le rotte SPA (`/login`, `/me/*`, ecc.) sono parole riservate (vedi
`reserved_usernames`), quindi il prefisso `/yf_users/...` non collide.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB
from app.models import User
from app.schemas.articles import ArticleListItem, ArticleListOut
from app.services import articles_service

log = structlog.get_logger()

router = APIRouter(prefix="/yf_users", tags=["public"])


async def _resolve_user(db, username: str) -> User:
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found"
        )
    return user


@router.get("/{username}/feed.json", response_model=ArticleListOut)
async def public_feed_json(
    username: str,
    db: DB,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> ArticleListOut:
    user = await _resolve_user(db, username)
    rows, next_cursor = await articles_service.timeline_for_public_user(
        db, target_user_id=int(user.id), cursor=cursor, limit=limit
    )
    items = [
        ArticleListItem.model_validate(articles_service.to_list_item(r)) for r in rows
    ]
    return ArticleListOut(items=items, next_cursor=next_cursor)


@router.get("/{username}/feed.rss")
async def public_feed_rss(username: str, db: DB) -> Response:
    """Export RSS 2.0 del feed pubblico dell'utente."""
    user = await _resolve_user(db, username)
    rows, _ = await articles_service.timeline_for_public_user(
        db, target_user_id=int(user.id), cursor=None, limit=50
    )

    settings = get_settings()
    base = settings.yf_public_base_url.rstrip("/")
    profile_link = f"{base}/{username}"
    feed_link = f"{base}/yf_users/{username}/feed.rss"
    now = datetime.now(UTC)

    items_xml: list[str] = []
    for row in rows:
        a = row.article
        title = (a.raw_meta_lite or {}).get("title") or "(senza titolo)"
        description = (a.raw_meta_lite or {}).get("description") or ""
        pub = format_datetime(a.published_at)
        items_xml.append(
            f"""    <item>
      <title>{escape(str(title))}</title>
      <link>{escape(a.url_canonical)}</link>
      <guid isPermaLink="true">{escape(a.url_canonical)}</guid>
      <pubDate>{pub}</pubDate>
      <description>{escape(str(description))}</description>
      <source url="{escape(row.source.url_site or '')}">{escape(row.source.title or '')}</source>
    </item>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>YouFeed — {escape(username)}</title>
    <link>{profile_link}</link>
    <atom:link href="{feed_link}" rel="self" type="application/rss+xml"/>
    <description>Feed pubblico di {escape(username)} su YouFeed</description>
    <language>it-it</language>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <generator>YouFeed/1.0</generator>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")
