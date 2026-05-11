"""Configurazione pytest condivisa.

Strategia env:
- Se esiste un `.env` (sviluppo locale), lo carichiamo subito a livello modulo
  con strip degli inline comments (stessa logica di alembic/env.py / config.py).
  In questo modo i test integration usano le credenziali Postgres reali.
- I valori chiave non ancora presenti vengono completati con dummy: serve
  per i test unit, che non toccano Postgres/Redis ma istanziano `Settings`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# --- Caricamento .env (eseguito al collect time, prima di importare app.*).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        if " #" in _v:
            _v = _v.split(" #", 1)[0]
        os.environ.setdefault(_k.strip(), _v.strip())


@pytest.fixture(autouse=True, scope="session")
def _env_defaults() -> Iterator[None]:
    """Imposta env minime per far partire la config in test (no .env richiesto)."""
    os.environ.setdefault("YF_SECRET_KEY", "test-secret-key-very-long-1234567890")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
    )
    os.environ.setdefault(
        "DATABASE_URL_SYNC", "postgresql://test:test@localhost:5432/test"
    )
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("YF_DEBUG", "true")
    yield
