"""Schemi Pydantic per alerts multi-topic (Phase 1.2.D + ext)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertTopicOut(BaseModel):
    """Minimal topic info da renderizzare insieme all'alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    display_name: str
    type: str


MatchMode = Literal["all", "any"]


class AlertOut(BaseModel):
    """Alert dell'utente con N topic."""

    id: int
    is_enabled: bool
    channels: list[str]
    match_mode: MatchMode
    created_at: datetime
    updated_at: datetime
    topics: list[AlertTopicOut]


class AlertCreateIn(BaseModel):
    topic_ids: list[int] = Field(min_length=1, max_length=10)
    channels: list[str] | None = None
    match_mode: MatchMode = "all"


class AlertUpdateIn(BaseModel):
    is_enabled: bool | None = None
    channels: list[str] | None = None
    topic_ids: list[int] | None = Field(default=None, min_length=1, max_length=10)
    match_mode: MatchMode | None = None
