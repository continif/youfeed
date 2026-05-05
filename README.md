# YOUFEED

Aggregatore di news personalizzabile, IT-only. Sostituirà l'attuale [youfeed.it](https://www.youfeed.it).

> Documentazione completa: [`Claude/`](Claude/) — design, schema, scope per release, sequenza task operativa.

## Quickstart sviluppo locale

```bash
# 1. Servizi di supporto (Postgres, Redis, Manticore)
docker-compose up -d

# 2. Backend
cd backend
python3.12 -m venv ../.venv
source ../.venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # popola SECRET_KEY etc.
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Frontend (in un'altra shell)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Struttura repo

```
youfeed/
  Claude/             # documentazione di design (architettura, MVP, status, ecc.)
  backend/            # FastAPI + ingestion + worker
  frontend/           # Vue 3 SPA
  infra/              # systemd, Apache vhost, docker-compose, script
  data/               # stopwords/wordforms IT, MMDB locali (dev)
  CLAUDE.md           # descrizione di prodotto
  STATUS.md → Claude/STATUS.md   # task list operativa
```

## Documentazione di riferimento

- [`Claude/ARCHITECTURE.md`](Claude/ARCHITECTURE.md) — architettura, stack, hosting
- [`Claude/MVP.md`](Claude/MVP.md) — scope per release (v1.0 → v2.0)
- [`Claude/STATUS.md`](Claude/STATUS.md) — sequenza task con stato
- [`Claude/BACKEND.md`](Claude/BACKEND.md), [`INGESTION.md`](Claude/INGESTION.md), [`DATABASE.md`](Claude/DATABASE.md), [`KNOWLEDGE-GRAPH.md`](Claude/KNOWLEDGE-GRAPH.md), [`FRONTEND.md`](Claude/FRONTEND.md) — design tecnico per area
- [`Claude/COMMANDS.md`](Claude/COMMANDS.md) — cheatsheet comandi quotidiani (dev, test, DB, Apache, deploy)
- [`Claude/reserved-words.txt`](Claude/reserved-words.txt) — username vietati

## Deploy in produzione

```bash
# Sul server, come utente youfeed:
cd /opt/youfeed
./infra/scripts/deploy.sh
```

Vedi [`infra/systemd/README.md`](infra/systemd/README.md) per il setup iniziale.
