# YOUFEED — Backend

FastAPI backend per YOUFEED. Vedi documentazione architetturale completa in [`../.claude/`](../.claude/).

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

## Dataset & snapshot

### Seed loader — [`app/utils/seed_loader.py`](app/utils/seed_loader.py)

Carica dataset curated nelle tabelle dell'app (idempotente, UPSERT su chiave naturale).

```bash
# Province italiane (CSV custom) → topics(type=location, is_curated=true)
python -m app.utils.seed_loader --provinces ../data/topics/province.csv

# Comuni italiani (CSV ISTAT, encoding cp1252) → topics(type=location, is_curated=true)
#   Gestisce collisioni di nome (es. Castro BG/LE → slug "castro-bg" / "castro-le",
#   display "Castro (BG)" / "Castro (LE)") e nomi bilingui Alto Adige/Valle d'Aosta
#   (es. "Aldino/Aldein" → display "Aldino", aliases ["Aldein"]).
python -m app.utils.seed_loader \
    --municipalities ../data/topics/Elenco-comuni-italiani.csv \
    --municipalities-encoding cp1252

# Altri dataset
python -m app.utils.seed_loader --reserved-words ../.claude/reserved-words.txt
python -m app.utils.seed_loader --topics ../data/topics/topics.csv
python -m app.utils.seed_loader --featured ../data/topics/featured.csv
```

Per l'estrazione "argomento di cronaca" il classifier deve riconoscere ogni
comune italiano (anche piccoli: Avetrana, Garlasco, ...): si carica l'intero
elenco ISTAT (~7900 comuni) come `is_curated=true`.

### Snapshot Parquet dei topics — [`app/utils/topics_snapshot.py`](app/utils/topics_snapshot.py)

Backup portabile di tutti i `topics` (qualunque `type`: `location`, `brand`,
`person`, `subject`, `model`) in un singolo file Parquet (zstd, level 9). Pensato
per bootstrap del DB da zero senza ripartire dai CSV grezzi e dalla logica di
slug anti-collisione.

```bash
# Export — tutti i type, solo curated (default)
python -m app.utils.topics_snapshot export --out ../data/topics.parquet

# Export — anche i topics non-curated (es. estratti automaticamente da ingestion)
python -m app.utils.topics_snapshot export --include-uncurated --out ../data/topics.parquet

# Export — un solo type
python -m app.utils.topics_snapshot export --type location --out ../data/locations.parquet

# Import — UPSERT su slug, idempotente
python -m app.utils.topics_snapshot import --in ../data/topics.parquet
```

Schema del Parquet (vedi `SCHEMA` nel modulo): `type`, `slug`, `display_name`,
`aliases` (`list<string>`), `description`, `external_refs` (JSON-encoded —
Parquet non ha un tipo JSONB), `is_curated`. Lo schema è coperto da
[`tests/integration/test_topics_snapshot.py`](tests/integration/test_topics_snapshot.py)
per evitare regressioni silenziose cross-versione.

Il file canonico [`data/topics.parquet`](../data/topics.parquet) è committato
nel repo: serve come bootstrap "1 comando" su un'installazione vergine
(`python -m app.utils.topics_snapshot import --in ../data/topics.parquet`).
