# YOUFEED — Backend

FastAPI backend per YOUFEED. Vedi documentazione architetturale completa in [`../Claude/`](../Claude/).

## Quickstart sviluppo

```bash
# 1. Python 3.12 con virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Installazione editable + tooling
pip install -e ".[dev]"

# 3. Servizi di supporto (via docker-compose dalla root del repo)
cd ..
docker-compose up -d postgres redis manticore

# 4. Variabili d'ambiente
cp .env.example .env
# Edita .env con i valori locali

# 5. Migrazioni DB
cd backend
alembic upgrade head

# 6. Run dev server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Struttura

```
backend/
  app/
    main.py            # FastAPI app + lifespan + middleware mounting
    config.py          # Settings via pydantic-settings
    deps.py            # Dependency injection (DB, Redis, current_user, ...)
    models/            # SQLAlchemy ORM models
    repositories/      # DB access layer per dominio
    schemas/           # Pydantic in/out
    services/          # Logica di dominio (auth, sources, categories, ...)
    routers/           # FastAPI routers (un file per dominio)
    middleware/        # CF-IP, MaxMind, rate limit, CSRF, activity log
    workers/           # RQ job functions
    templates/         # Jinja2 (pagine pubbliche + email)
    rss/               # Generazione feed RSS
    utils/             # Helper trasversali
  alembic/             # Migrazioni schema Postgres
  tests/
    unit/
    integration/
```

## Comandi utili

```bash
ruff check app tests           # lint
ruff format app tests          # format
pyright app tests              # type check
pytest                         # tutti i test
pytest -m "not integration"    # solo unit
alembic revision --autogenerate -m "descrizione"   # nuova migration
alembic upgrade head           # applica
alembic downgrade -1           # rollback ultima
```
