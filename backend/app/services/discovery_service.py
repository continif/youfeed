"""Servizio discovery: orchestra `ingestion.discovery` e persiste in `sources`.

Idempotenza: se per la stessa `url_feed` o `wp_api_root` esiste già un record
in `sources`, lo riutilizza (eventualmente aggiornando `discovery_meta`).
Questo permette a più utenti di "scoprire" la stessa fonte e finire sullo
stesso `source_id` — coerente con il modello "Source globale condivisa".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import discovery
from app.models import Source

log = structlog.get_logger()


async def discover_and_persist(
    session: AsyncSession, *, url: str
) -> tuple[discovery.DiscoveryResult, Source | None]:
    """Esegue discovery e (se kind != invalid) crea/aggiorna `sources`.

    Ritorna `(result, source)`. `source` è None se invalid.
    """
    result = await discovery.discover(url)

    if result.kind == "invalid":
        log.info("yf.discovery.invalid", url=url, reason=result.reason)
        return result, None

    src = await _upsert_source(session, result)
    await session.flush()
    log.info(
        "yf.discovery.qualified",
        url=url,
        source_id=src.id,
        kind=result.kind,
    )
    return result, src


async def _upsert_source(
    session: AsyncSession, r: discovery.DiscoveryResult
) -> Source:
    """Cerca per chiave naturale (url_feed o wp_api_root); altrimenti crea."""
    existing: Source | None = None

    if r.kind == "rss" and r.url_feed:
        q = select(Source).where(Source.url_feed == r.url_feed)
        existing = (await session.execute(q)).scalar_one_or_none()
    elif r.kind == "wordpress_api" and r.wp_api_root:
        q = select(Source).where(Source.wp_api_root == r.wp_api_root)
        existing = (await session.execute(q)).scalar_one_or_none()

    discovery_meta: dict[str, Any] = {
        "candidates": [
            {
                "url_feed": c.url_feed,
                "title": c.title,
                "samples": len(c.sample_articles),
            }
            for c in r.candidates
        ],
        "og": {
            "title": r.og.title,
            "description": r.og.description,
            "image": r.og.image,
            "site_name": r.og.site_name,
            "favicon": r.og.favicon,
        },
        "qualified_at_iso": datetime.now(UTC).isoformat(),
    }

    if existing is not None:
        # Aggiorna metadati (titolo, favicon, status pending → active al primo
        # fetch reale che andrà a buon fine; qui lasciamo `pending` se nuovo)
        if not existing.title and r.og.title:
            existing.title = r.og.title
        if not existing.favicon_url and r.og.favicon:
            existing.favicon_url = r.og.favicon
        existing.discovery_meta = discovery_meta
        existing.qualified_at = datetime.now(UTC)
        # Se in passato era "invalid" e ora abbiamo qualificato, riallinea
        if existing.kind == "invalid" and r.kind != "invalid":
            existing.kind = r.kind
        return existing

    src = Source(
        kind=r.kind,
        url_site=r.url_site,
        url_feed=r.url_feed,
        wp_api_root=r.wp_api_root,
        title=r.og.title,
        favicon_url=r.og.favicon,
        status="pending",
        discovery_meta=discovery_meta,
        qualified_at=datetime.now(UTC),
    )
    session.add(src)
    await session.flush()
    return src
