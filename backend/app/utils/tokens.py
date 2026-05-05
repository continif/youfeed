"""Generatori di token sicuri (verifica email, reset password, CSRF, ecc.)."""

from __future__ import annotations

import secrets


def url_safe_token(nbytes: int = 32) -> str:
    """Token URL-safe base64. ~43 caratteri con nbytes=32."""
    return secrets.token_urlsafe(nbytes)
