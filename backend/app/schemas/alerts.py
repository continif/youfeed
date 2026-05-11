"""Schemi Pydantic per alerts (Phase 1.2.D)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertTopicOut(BaseModel):
    """Minimal topic info da renderizzare insieme all'alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    display_name: str
    type: str


class AlertOut(BaseModel):
    """Alert dell'utente, joined con il Topic."""

    id: int
    is_enabled: bool
    channels: list[str]
    created_at: datetime
    updated_at: datetime
    topic: AlertTopicOut


class AlertCreateIn(BaseModel):
    topic_id: int = Field(ge=1)
    channels: list[str] | None = None


class AlertUpdateIn(BaseModel):
    is_enabled: bool | None = None
    channels: list[str] | None = None
