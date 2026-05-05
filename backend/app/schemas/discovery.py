"""Schemi Pydantic per discovery URL."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class DiscoverIn(BaseModel):
    url: str = Field(min_length=4, max_length=2048)


class FeedCandidateOut(BaseModel):
    url_feed: str
    title: str | None
    sample_articles: list[dict[str, str]]


class OgPreviewOut(BaseModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None
    favicon: str | None = None


class DiscoveryOut(BaseModel):
    """Risposta del discovery.

    Se `kind == 'invalid'`, `source_id` è None e `reason` spiega perché.
    Se `kind ∈ {'rss', 'wordpress_api'}`, `source_id` è l'ID della Source
    creata/aggiornata (l'utente la riutilizzerà nel POST /yf_me/sources).
    """

    kind: str  # 'rss' | 'wordpress_api' | 'invalid'
    source_id: int | None = None
    url_site: str | None = None
    url_feed: str | None = None
    wp_api_root: str | None = None
    candidates: list[FeedCandidateOut] = Field(default_factory=list)
    og: OgPreviewOut = Field(default_factory=OgPreviewOut)
    reason: str | None = None
