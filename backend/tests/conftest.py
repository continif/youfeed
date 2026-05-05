"""Configurazione pytest condivisa.

Per i test unit (no Postgres/Redis/Manticore), forziamo SECRET_KEY e
DATABASE_URL a valori dummy così l'app può istanziare le settings senza
errori. I test che richiedono i servizi reali sono marcati `integration`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


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
