"""Endpoint `POST /yf_sources/discover`."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DB
from app.schemas.discovery import (
    DiscoverIn,
    DiscoveryOut,
    FeedCandidateOut,
    OgPreviewOut,
)
from app.services import discovery_service

router = APIRouter(prefix="/yf_sources", tags=["sources"])


@router.post("/discover", response_model=DiscoveryOut)
async def discover_url(payload: DiscoverIn, db: DB) -> DiscoveryOut:
    result, source = await discovery_service.discover_and_persist(db, url=payload.url)
    await db.commit()

    return DiscoveryOut(
        kind=result.kind,
        source_id=source.id if source is not None else None,
        url_site=result.url_site,
        url_feed=result.url_feed,
        wp_api_root=result.wp_api_root,
        candidates=[
            FeedCandidateOut(
                url_feed=c.url_feed,
                title=c.title,
                sample_articles=c.sample_articles,
            )
            for c in result.candidates
        ],
        og=OgPreviewOut(
            title=result.og.title,
            description=result.og.description,
            image=result.og.image,
            site_name=result.og.site_name,
            favicon=result.og.favicon,
        ),
        reason=result.reason,
    )
