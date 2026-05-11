"""Schemi Pydantic per timeline e dettaglio articoli."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArticleSourceMini(BaseModel):
    """Fonte minimale annestata in ArticleListItem."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    favicon_url: str | None
    url_site: str | None


class TopicMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    display_name: str
    type: str


class ArticleListItem(BaseModel):
    """Card timeline: tutto ciò che serve per renderizzare una `<ArticleCard>`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    url_canonical: str
    title: str
    description: str | None
    image_url: str | None  # URL pubblico (variante desktop) — può essere None
    image_local_url: str | None  # serving locale (es. /images/ab/cd/...)
    image_width: int | None
    image_height: int | None
    author: str | None
    published_at: datetime
    source: ArticleSourceMini
    topics: list[TopicMini] = Field(default_factory=list)
    # Colore della categoria a cui l'utente loggato (o l'utente target del
    # profilo pubblico) ha linkato la source. None se non c'è binding o se
    # la timeline è chiamata in contesto senza utente. Hex `#rrggbb`.
    category_color: str | None = None


class ArticleListOut(BaseModel):
    items: list[ArticleListItem]
    next_cursor: str | None = None


class RelatedArticleItem(ArticleListItem):
    """Card correlata: ArticleListItem + score di overlap topic."""

    overlap: float = Field(ge=0.0, le=1.0)


class RelatedArticlesOut(BaseModel):
    items: list[RelatedArticleItem]
    formula: str
    min_overlap: float
    days_window: int


class ArticleDetailOut(ArticleListItem):
    """Dettaglio articolo: include il content_html sanitizzato (da Manticore)."""

    content_html: str | None = None
    content_text: str | None = None
    internal_links: list[dict[str, str]] = Field(default_factory=list)


class TrackEventIn(BaseModel):
    """Evento client (impression / click / dwell / scroll)."""

    event_type: str = Field(min_length=2, max_length=32)
    target_type: str | None = Field(default=None, max_length=16)
    target_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, object] | None = None
