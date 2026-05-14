"""Endpoint SEO: sitemap.xml + robots.txt + pagine informative pubbliche.

Niente `/yf_` prefix qui: i crawler cercano percorsi standard. Le pagine
servite via Jinja2 (no SPA) sono quelle che ci interessa far indicizzare
e che non hanno bisogno della reattività di Vue:
  - /bot           identificazione crawler
  - /chi-siamo     about page
  - /come-funziona guida utente
  - /disclaimer    nota legale
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB
from app.ingestion.user_agent import USER_AGENT, USER_AGENT_TOKEN, USER_AGENT_VERSION
from app.models import Article
from app.services import seo_service

log = structlog.get_logger()

router = APIRouter(tags=["seo"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/bot")
async def bot_page(request: Request) -> Response:
    """Pagina pubblica di identificazione del nostro crawler.

    Pubblicizzata via header `User-Agent: YouFeed/<v> (+https://www.youfeed.it/bot)`.
    Spiega cosa fa il bot, come identificarlo e come bloccarlo via
    robots.txt o WAF. Niente login richiesto.
    """
    return _templates.TemplateResponse(
        request,
        "public/bot.html",
        {
            "user_agent": USER_AGENT,
            "user_agent_token": USER_AGENT_TOKEN,
            "user_agent_version": USER_AGENT_VERSION,
        },
    )


def _info_page(request: Request, template: str, slug: str) -> Response:
    settings = get_settings()
    canonical = settings.yf_public_base_url.rstrip("/") + "/" + slug
    return _templates.TemplateResponse(
        request,
        template,
        {"canonical_url": canonical},
    )


@router.get("/chi-siamo")
async def chi_siamo(request: Request) -> Response:
    return _info_page(request, "public/chi-siamo.html", "chi-siamo")


@router.get("/come-funziona")
async def come_funziona(request: Request) -> Response:
    return _info_page(request, "public/come-funziona.html", "come-funziona")


@router.get("/disclaimer")
async def disclaimer(request: Request) -> Response:
    return _info_page(request, "public/disclaimer.html", "disclaimer")


@router.get("/sitemap.xml")
async def sitemap(db: DB) -> Response:
    settings = get_settings()
    base_url = settings.yf_public_base_url.rstrip("/")

    # Home lastmod = max(published_at) globale (proxy per "ultima novità").
    # Le info page hanno lastmod statico = mtime del template (build asset).
    last_global = await db.scalar(
        select(func.max(Article.published_at)).where(
            Article.processing_status == "indexed"
        )
    )
    if last_global is None:
        last_global = datetime.now(UTC)
    elif last_global.tzinfo is None:
        last_global = last_global.replace(tzinfo=UTC)

    entries = seo_service.build_static_entries(
        base_url=base_url, home_lastmod=last_global
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
