"""Catch-all dispatcher Jinja2 per le pagine pubbliche.

Questo router è registrato come ULTIMO in `main.py`: cattura tutto ciò che
non è stato matchato dagli endpoint `/yf_*` (API) o servito da Apache (SPA
Vue su `/me/*`, static files).

Rotte:
  GET /                           -> home (landing)
  GET /{username}                 -> profilo pubblico (timeline + RSS link)
  GET /{username}/{category_slug} -> [v1.0+] timeline filtrata per categoria

Reserved usernames: se `username` matcha una parola in `reserved_usernames`
(es. "login", "register", "about", "static", "yf_*"), restituiamo 404
direttamente senza query articoli.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_deps import CurrentUserOptional
from app.config import get_settings
from app.deps import DB, RedisDep
from app.models import ReservedUsername, User, UserSource
from app.services import articles_service

log = structlog.get_logger()

_HOME_CACHE_KEY = "yf:home:public:articles"
_HOME_CACHE_TTL = 60  # secondi
_HOME_VETRINA_LIMIT = 12

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Le pagine "logiche" della SPA Vue che NON devono cadere nel dispatcher
# pubblico (Apache in dev fa già il proxy a Vite, ma lo blocchiamo anche
# qui per sicurezza — es. quando si testa direttamente la porta 8000).
SPA_RESERVED_PREFIXES = (
    "me",
    "login",
    "register",
    "logout",
    "verify-email",
    "reset-password",
    "onboarding",
    "settings",
)
# Path "tecnici" che non corrispondono a un username
TECH_RESERVED = frozenset(
    {
        "static",
        "assets",
        "images",
        "favicon.ico",
        "robots.txt",
        "sitemap.xml",
        "sw.js",
        "about",
        "bot",
        "chi-siamo",
        "come-funziona",
        "disclaimer",
    }
)


router = APIRouter(tags=["public-dispatcher"])


@router.get("/")
async def home(
    request: Request,
    db: DB,
    redis: RedisDep,
    user: CurrentUserOptional,
) -> Response:
    # Loggato → manda diritto al feed personale, no landing.
    if user is not None:
        return RedirectResponse(url="/me/feed", status_code=status.HTTP_302_FOUND)

    items = await _home_articles(db, redis)
    settings = get_settings()
    return _templates.TemplateResponse(
        request,
        "public/home.html",
        {
            "items": items,
            "canonical_url": settings.yf_public_base_url.rstrip("/") + "/",
        },
    )


async def _home_articles(db: AsyncSession, redis: Redis) -> list[dict[str, Any]]:
    """Vetrina home cached. Fail-open su errori Redis (la home non si rompe se
    Redis è giù — la query DB è da sola circa 1 join e 1 LIMIT)."""
    try:
        cached = await redis.get(_HOME_CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception as e:
        log.warning("home_cache_get_failed", error=str(e))

    rows = await articles_service.timeline_global_public(db, limit=_HOME_VETRINA_LIMIT)
    items = [_serialize_for_home(articles_service.to_list_item(r)) for r in rows]

    try:
        await redis.set(_HOME_CACHE_KEY, json.dumps(items), ex=_HOME_CACHE_TTL)
    except Exception as e:
        log.warning("home_cache_set_failed", error=str(e))

    return items


def _serialize_for_home(item: dict[str, Any]) -> dict[str, Any]:
    """Converte i campi non-JSON-serializzabili (datetime) in stringhe già
    pronte per il template Jinja della home."""
    pub = item.pop("published_at", None)
    item["published_at_iso"] = pub.isoformat() if pub else None
    item["published_at_human"] = pub.strftime("%d %b %Y · %H:%M") if pub else ""
    return item


async def _is_reserved(db, username: str) -> bool:
    if username.lower() in TECH_RESERVED:
        return True
    if username.lower() in SPA_RESERVED_PREFIXES:
        return True
    if username.lower().startswith("yf_"):
        return True
    row = await db.execute(
        select(ReservedUsername).where(ReservedUsername.word == username.lower())
    )
    return row.scalar_one_or_none() is not None


@router.get("/{username}", response_class=HTMLResponse)
async def profile(
    username: str,
    request: Request,
    db: DB,
    cursor: str | None = None,
) -> HTMLResponse:
    # Username vuoto/strano -> 404
    if not username or "/" in username or "." in username:
        return _render_404(request)

    if await _is_reserved(db, username):
        return _render_404(request, reason="username_reserved")

    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        return _render_404(request, reason="username_not_found")

    rows, next_cursor = await articles_service.timeline_for_public_user(
        db, target_user_id=int(user.id), cursor=cursor, limit=24
    )
    color_map = await articles_service.fetch_source_to_color(
        db, user_id=int(user.id), source_ids=[int(r.source.id) for r in rows]
    )
    items = [
        articles_service.to_list_item(r, category_color=color_map.get(int(r.source.id)))
        for r in rows
    ]

    # Conteggio fonti pubbliche per header
    source_count_row = await db.execute(
        select(UserSource.source_id)
        .where(UserSource.user_id == user.id)
    )
    source_count = len({int(r[0]) for r in source_count_row.all()})

    settings = get_settings()
    canonical = settings.yf_public_base_url.rstrip("/") + f"/{user.username}"
    return _templates.TemplateResponse(
        request,
        "public/profile.html",
        {
            "profile_username": user.username,
            "items": items,
            "next_cursor": next_cursor,
            "source_count": source_count,
            "canonical_url": canonical,
        },
    )


def _render_404(request: Request, *, reason: str | None = None) -> HTMLResponse:
    response = _templates.TemplateResponse(
        request,
        "public/404.html",
        {"reason": reason},
        status_code=status.HTTP_404_NOT_FOUND,
    )
    return response
