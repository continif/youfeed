"""Schemi Pydantic per Web Push (Phase 1.2.E)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VapidKeyOut(BaseModel):
    """Risposta `/yf_push/vapid-key`: chiave pubblica VAPID b64url."""

    public_key: str
    configured: bool


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=512)
    auth: str = Field(min_length=10, max_length=128)


class PushSubscriptionCreateIn(BaseModel):
    """Body inviato dalla SPA dopo `PushManager.subscribe()`."""

    endpoint: str = Field(min_length=10, max_length=1024)
    keys: PushSubscriptionKeys


class PushSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    ua: str | None
    created_at: datetime
    last_seen_at: datetime
