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


class UserOut(BaseModel):
    """Rappresentazione pubblica dell'utente loggato."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    email_verified: bool
    onboarding_completed_at: datetime | None
    created_at: datetime


class MessageOut(BaseModel):
    """Risposta generica con messaggio human-readable."""

    message: str


class UsernameAvailableOut(BaseModel):
    available: bool
