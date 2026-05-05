"""Settings centralizzate via pydantic-settings.

Tutte le variabili sono lette da `.env` (o env del processo).
Si veda `.env.example` per la lista completa con default.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env vive in root del repo (un livello sopra backend/). Lo carichiamo a mano
# con strip degli inline comments (` #` → ignora il resto), così non rompiamo
# valori che contengono `#` (URL/secret) e ci comportiamo come alembic/env.py
# e utils/seed_loader.py, che usano lo stesso parser semplice.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        if " #" in _v:
            _v = _v.split(" #", 1)[0]
        os.environ.setdefault(_k.strip(), _v.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Generale ----
    yf_env: str = "development"
    yf_debug: bool = False
    yf_secret_key: str = Field(min_length=16)
    yf_public_base_url: str = "http://localhost:8000"
    yf_frontend_base_url: str = "http://localhost:5173"

    # ---- Postgres ----
    database_url: str  # async per app
    database_url_sync: str  # sync per Alembic

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"
    rq_redis_url: str = "redis://localhost:6379/1"

    # ---- Manticore ----
    manticore_host: str = "127.0.0.1"
    manticore_port: int = 9306
    manticore_http_port: int = 9308

    # ---- SMTP / Email (OVH) ----
    smtp_host: str = "ssl0.ovh.net"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "noreply@youfeed.it"
    smtp_from_name: str = "YouFeed"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    # ---- Sessione cookie ----
    session_cookie_name: str = "yf_session"
    session_cookie_domain: str = ""  # vuoto in dev
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_lifetime_days: int = 30

    # ---- Rate limit ----
    rate_limit_anon_per_min: int = 60
    rate_limit_user_per_min: int = 600

    # ---- MaxMind ----
    maxmind_db_dir: Path = Path("./data/maxmind")
    maxmind_license_key: str = ""

    # ---- Storage immagini ----
    images_dir: Path = Path("./data/images")
    images_public_prefix: str = "/images"
    image_mobile_width: int = 370
    image_desktop_max_width: int = 1200
    image_webp_quality: int = 80

    # ---- Logging ----
    log_level: str = "INFO"
    log_json: bool = False

    # ---- Google OAuth (v1.1) ----
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # ---- Web Push (v1.2) ----
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:noreply@youfeed.it"

    # ---- LLM (v1.2) ----
    anthropic_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.yf_env == "production"

    @property
    def is_dev(self) -> bool:
        return self.yf_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton delle settings. Cached per evitare re-parsing del .env."""
    return Settings()  # type: ignore[call-arg]
