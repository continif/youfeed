"""Setup DB di test per integration test.

Strategia:
- DB dedicato `youfeed_test` (override via env `DATABASE_URL_TEST`).
- Se il DB non esiste, lo creiamo (richiede CREATEDB sul ruolo).
- Eseguiamo `alembic upgrade head` programmaticamente al primo invocation.
- Per ogni test, TRUNCATE delle tabelle utente prima di yield della session.

Tutti i test integration vengono SKIPPATI se il DB di test non è raggiungibile
(connection refused, autorizzazione negata, etc.) — così la suite resta
verde anche in CI senza Postgres.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _resolve_test_urls() -> tuple[str, str]:
    """Ritorna (async_url, sync_url) per il DB di test.

    Ordine di preferenza:
    1. Env `DATABASE_URL_TEST` (async) + `DATABASE_URL_SYNC_TEST` (sync).
    2. Deriva da `DATABASE_URL` / `DATABASE_URL_SYNC` sostituendo il nome
       del DB con `<original>_test`.
    """
    async_test = os.environ.get("DATABASE_URL_TEST")
    sync_test = os.environ.get("DATABASE_URL_SYNC_TEST")
    if async_test and sync_test:
        return async_test, sync_test

    async_main = os.environ.get("DATABASE_URL")
    sync_main = os.environ.get("DATABASE_URL_SYNC")
    if not async_main or not sync_main:
        pytest.skip("DATABASE_URL/DATABASE_URL_SYNC mancanti — integration skip")

    def _swap_db(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path.lstrip("/")
        if not path:
            pytest.skip(f"URL {url!r} senza database name — integration skip")
        return urlunsplit((parts.scheme, parts.netloc, "/" + path + "_test", parts.query, parts.fragment))

    return _swap_db(async_main), _swap_db(sync_main)


def _ensure_test_db_exists(sync_url: str) -> None:
    """Connette al DB `postgres` (o template1) e crea il DB target se manca."""
    import psycopg2

    parts = urlsplit(sync_url)
    target_db = parts.path.lstrip("/")
    bootstrap = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))

    # psycopg2 non accetta lo scheme `postgresql`: bene, lo accetta nativo.
    conn = psycopg2.connect(bootstrap)
    try:
        conn.autocommit = True  # CREATE DATABASE non può stare in transaction
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        if cur.fetchone() is None:
            # Sanitize: target_db viene da env, ma per sicurezza permettiamo
            # solo identificatori semplici.
            if not target_db.replace("_", "").isalnum():
                pytest.fail(f"Nome DB test non sicuro: {target_db!r}")
            cur.execute(f'CREATE DATABASE "{target_db}"')
        cur.close()
    finally:
        conn.close()


def _ensure_extensions(sync_url: str) -> None:
    """CITEXT + pgcrypto. Da PG13+ sono `trusted` => utenti normali OK."""
    import psycopg2

    conn = psycopg2.connect(sync_url)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        for ext in ("citext", "pgcrypto"):
            try:
                cur.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
            except psycopg2.errors.InsufficientPrivilege as e:
                pytest.skip(
                    f"Manca permesso per CREATE EXTENSION {ext} sul DB test: {e}"
                )
        cur.close()
    finally:
        conn.close()


def _run_migrations(sync_url: str) -> None:
    """alembic upgrade head sul DB test (idempotente)."""
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    cfg_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    # alembic env.py legge DATABASE_URL_SYNC da env: lo override.
    os.environ["DATABASE_URL_SYNC"] = sync_url
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def integration_db_url() -> str:
    """Engine async URL per il DB test. Setup completo (create + migrate)."""
    async_url, sync_url = _resolve_test_urls()
    try:
        _ensure_test_db_exists(sync_url)
        _ensure_extensions(sync_url)
        _run_migrations(sync_url)
    except Exception as e:
        pytest.skip(f"Setup DB test fallito: {e}")
    return async_url


@pytest_asyncio.fixture(scope="session")
async def integration_engine(integration_db_url: str):
    # NullPool: ogni AsyncSession ha la sua connection fresca. Evita
    # il classico "another operation is in progress" di asyncpg quando
    # le connessioni vengono riusate fra test.
    engine = create_async_engine(
        integration_db_url, echo=False, future=True, poolclass=NullPool
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def integration_sessionmaker(integration_engine):
    return async_sessionmaker(integration_engine, expire_on_commit=False, class_=AsyncSession)


# Lista tabelle da pulire tra un test e l'altro. activity_log è esclusa
# perché partitioned + i test attuali non la usano; se servirà, aggiungerla.
_TRUNCATE_TABLES = (
    "article_topics",
    "article_entities",
    "articles",
    "user_sources",
    "categories",
    "featured_sources",
    "sources",
    "auth_sessions",
    "email_verification_tokens",
    "users",
    "entities",
    "topics",
    "reserved_usernames",
)


@pytest_asyncio.fixture
async def db_session(integration_sessionmaker) -> AsyncIterator[AsyncSession]:
    """Sessione pulita: TRUNCATE prima del test, commit/rollback gestito dal test."""
    async with integration_sessionmaker() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(_TRUNCATE_TABLES)
                + " RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session
