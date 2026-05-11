"""Schemi Pydantic per notifiche in-app (Phase 1.1.E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    payload: dict[str, Any] | None
    read_at: datetime | None
    created_at: datetime


class NotificationCountOut(BaseModel):
    unread: int
