"""Dependency HTTP Basic per il pannello admin (`/yf_admin/*`).

Credenziali da `.env`:
    ADMIN_USERNAME=...
    ADMIN_PASSWORD=...

In v1 plaintext nel `.env` come da specifica utente. Roadmap: bcrypt hash
+ rotation. Se le credenziali non sono settate, ogni accesso restituisce
401 (admin disabilitato).

Usato come `Depends(require_admin)` su tutto il router admin.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

_security = HTTPBasic(realm="YouFeed Admin")


def require_admin(
    creds: HTTPBasicCredentials = Depends(_security),
) -> str:
    """Verifica username/password contro `.env` con `secrets.compare_digest`
    (timing-safe). Ritorna lo username admin se ok; solleva 401 altrimenti.
    """
    settings = get_settings()
    expected_user = settings.admin_username
    expected_pwd = settings.admin_password

    # Admin disabilitato se manca anche solo una delle due env var.
    if not expected_user or not expected_pwd:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin non configurato. Setta ADMIN_USERNAME + ADMIN_PASSWORD nel .env.",
            headers={"WWW-Authenticate": 'Basic realm="YouFeed Admin"'},
        )

    user_ok = secrets.compare_digest(
        creds.username.encode("utf-8"), expected_user.encode("utf-8")
    )
    pwd_ok = secrets.compare_digest(
        creds.password.encode("utf-8"), expected_pwd.encode("utf-8")
    )
    if not (user_ok and pwd_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
            headers={"WWW-Authenticate": 'Basic realm="YouFeed Admin"'},
        )
    return creds.username
