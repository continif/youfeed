"""Endpoint SEO: sitemap.xml + robots.txt.

Niente `/yf_` prefix qui: i crawler cercano percorsi standard.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB
from app.models import Article
from app.services import seo_service

log = structlog.get_logger()

router = APIRouter(tags=["seo"])


@router.get("/sitemap.xml")
async def sitemap(db: DB) -> Response:
    settings = get_settings()
    base_url = settings.yf_public_base_url.rstrip("/")

    # Home: lastmod = max(published_at) globale (proxy per "ultima novità")
    last_global = await db.scalar(
        select(func.max(Article.published_at)).where(
            Article.processing_status == "indexed"
        )
    )
    if last_global is None:
        last_global = datetime.now(UTC)
    elif last_global.tzinfo is None:
        last_global = last_global.replace(tzinfo=UTC)

    entries = [
        seo_service.SitemapEntry(
            loc=base_url + "/",
            lastmod=last_global,
            changefreq="hourly",
            priority=1.0,
        )
    ]
    entries.extend(
        await seo_service.collect_public_profile_entries(db, base_url=base_url)
    )

    body = seo_service.build_sitemap_xml(entries)
    return Response(content=body, media_type="application/xml; charset=utf-8")


@router.get("/robots.txt")
async def robots() -> PlainTextResponse:
    settings = get_settings()
    body = seo_service.build_robots_txt(
        base_url=settings.yf_public_base_url,
        allow_indexing=settings.is_production or settings.is_dev,
    )
    return PlainTextResponse(content=body)
