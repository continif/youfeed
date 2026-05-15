"""Schemi Pydantic per gli endpoint auth."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    # identifier può essere username o email (Pydantic non discrimina, lo facciamo a runtime)
    identifier: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class ResendVerificationIn(BaseModel):
    email: EmailStr


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=10, max_length=200)


class MePatchIn(BaseModel):
    """Patch parziale per `/yf_me`. Setta `onboarding_completed_at = NOW()`
    se True, NULL se False (utile per test/admin).

    `profile_seo_*`: SEO custom della pagina pubblica `/{username}`.
    Stringa vuota → reset al default (catchy markettaro).
    """

    onboarding_completed: bool | None = None
    profile_seo_title: str | None = Field(default=None, max_length=80)
    profile_seo_description: str | None = Field(default=None, max_length=200)


class UserOut(BaseModel):
    """Rappresentazione pubblica dell'utente loggato."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    email_verified: bool
    onboarding_completed_at: datetime | None
    profile_seo_title: str | None = None
    profile_seo_description: str | None = None
    created_at: datetime


class MessageOut(BaseModel):
    """Risposta generica con messaggio human-readable."""

    message: str


class DeviceOut(BaseModel):
    """Sessione attiva dell'utente loggato (Phase 1.1.C)."""

    id: str
    client: str
    ip: str | None
    country: str | None
    ua: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


class UsernameAvailableOut(BaseModel):
    available: bool
