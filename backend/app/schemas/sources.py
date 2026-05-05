"""Schemi Pydantic per fonti."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceOut(BaseModel):
    """Vista pubblica di una `Source` globale."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    url_site: str | None
    url_feed: str | None
    wp_api_root: str | None
    title: str | None
    favicon_url: str | None
    status: str


class UserSourceOut(BaseModel):
    """Iscrizione utente-a-fonte (con categoria e fonte annestate)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    custom_title: str | None
    added_at: datetime
    source: SourceOut


class UserSourceListOut(BaseModel):
    items: list[UserSourceOut]


class UserSourceCreateIn(BaseModel):
    source_id: int = Field(gt=0)
    category_id: int = Field(gt=0)
    custom_title: str | None = Field(default=None, max_length=200)


class UserSourceUpdateIn(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    custom_title: str | None = Field(default=None, max_length=200)


class FeaturedSourceItem(BaseModel):
    """Card della FeaturedSourcesGallery."""

    model_config = ConfigDict(from_attributes=True)

    source_id: int
    display_name: str | None
    description: str | None
    position: int
    source: SourceOut


class FeaturedSourcesOut(BaseModel):
    """Raggruppamento per `category_hint`."""

    by_category: dict[str, list[FeaturedSourceItem]]
