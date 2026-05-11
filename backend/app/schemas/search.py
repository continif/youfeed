"""Schemi Pydantic per la search (v1.1.D)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.articles import ArticleListItem


class SearchHighlights(BaseModel):
    """Snippet con `<mark>` evidenziati dal motore."""
    title: str = ""
    description: str = ""
    content_text: str = ""


class SearchResultItem(ArticleListItem):
    """Articolo + snippet evidenziato dal full-text search."""

    model_config = ConfigDict(from_attributes=True)

    highlights: SearchHighlights = Field(default_factory=SearchHighlights)


class SearchOut(BaseModel):
    items: list[SearchResultItem]
    total: int
    limit: int
    offset: int
    query: str


class SuggestTopicItem(BaseModel):
    id: int
    slug: str
    display_name: str
    type: str


class SuggestSourceItem(BaseModel):
    id: int
    title: str | None
    url_site: str | None


class SuggestOut(BaseModel):
    topics: list[SuggestTopicItem] = Field(default_factory=list)
    sources: list[SuggestSourceItem] = Field(default_factory=list)
