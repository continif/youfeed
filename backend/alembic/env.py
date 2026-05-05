"""Alembic environment per YOUFEED.

Legge `DATABASE_URL_SYNC` direttamente da env (no dipendenza da app.config)
così Alembic può girare anche senza l'intera app inizializzata.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Carica .env se disponibile (sviluppo locale).
# Strip dei commenti inline: tutto dopo ` #` è ignorato (lo spazio prima
# dell'hash è obbligatorio così non spezziamo URL/secret che contengono `#`).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if " #" in v:
            v = v.split(" #", 1)[0]
        os.environ.setdefault(k.strip(), v.strip())

# Importa la metadata di tutti i modelli per autogenerate
from app.models import Base  # noqa: E402

config = context.config

# Risolvi la URL sync da env
db_url = os.environ.get("DATABASE_URL_SYNC")
if not db_url:
    raise RuntimeError(
        "DATABASE_URL_SYNC non trovata. Impostala in .env o nelle variabili d'ambiente."
    )
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (genera SQL, non applica)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (applica al DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
