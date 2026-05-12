"""Schemi Pydantic per i bookmark (saved articles)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .articles import ArticleListItem


class BookmarkAddIn(BaseModel):
    article_id: int = Field(ge=1)


class BookmarkOut(BaseModel):
    """Singolo bookmark con l'articolo annestato (card timeline)."""

    model_config = ConfigDict(from_attributes=True)

    article: ArticleListItem
    created_at: datetime


class BookmarkIdsOut(BaseModel):
    """Risposta della check API: quali fra gli id richiesti sono bookmark."""

    ids: list[int]
