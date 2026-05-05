"""FastAPI app entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.db import dispose_engine
from app.exceptions import register_exception_handlers
from app.logging_setup import setup_logging
from app.middleware.activity_log import ActivityLogMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.geoip import GeoIPMiddleware
from app.middleware.ratelimit import RateLimitMiddleware
from app.redis_client import dispose_redis
from app.routers import auth, categories, discovery, health, me, sources


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Init + cleanup risorse condivise."""
    setup_logging()
    log = structlog.get_logger()
    log.info("yf.startup", version=__version__, env=get_settings().yf_env)
    try:
        yield
    finally:
        log.info("yf.shutdown")
        await dispose_engine()
        await dispose_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="YOUFEED API",
        version=__version__,
        description="Aggregatore news IT-only — backend",
        # OpenAPI esposto solo in dev/staging (decisione finale in Da definire)
        docs_url="/yf_docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/yf_openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    # Middleware. Ordine entry: ultimo aggiunto = outermost = primo a vedere
    # la richiesta. Per noi serve:
    #   GeoIP → RateLimit → CSRF → ActivityLog → handler
    # quindi aggiungiamo nell'ordine inverso (innermost first):
    app.add_middleware(ActivityLogMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(GeoIPMiddleware)

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(categories.router)
    app.include_router(sources.me_router)
    app.include_router(sources.public_router)
    app.include_router(discovery.router)

    # NB: articles, public dispatcher, ecc. verranno registrati
    # nelle Phase successive (vedi Claude/STATUS.md).

    return app


app = create_app()
