# YOUFEED

Aggregatore di news personalizzabile, IT-only. Sostituirà l'attuale [youfeed.it](https://www.youfeed.it).

> Documentazione completa: [`.claude/`](.claude/) — design, schema, scope per release, sequenza task operativa.

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
  .claude/             # documentazione di design (architettura, MVP, status, ecc.)
  backend/            # FastAPI + ingestion + worker
  frontend/           # Vue 3 SPA
  infra/              # systemd, Apache vhost, docker-compose, script
  data/               # stopwords/wordforms IT, MMDB locali (dev), snapshot topics (parquet)
  CLAUDE.md           # descrizione di prodotto
  STATUS.md → .claude/STATUS.md   # task list operativa
```

## Documentazione di riferimento

- [`.claude/ARCHITECTURE.md`](.claude/ARCHITECTURE.md) — architettura, stack, hosting
- [`.claude/MVP.md`](.claude/MVP.md) — scope per release (v1.0 → v2.0)
- [`.claude/STATUS.md`](.claude/STATUS.md) — sequenza task con stato
- [`.claude/BACKEND.md`](.claude/BACKEND.md), [`INGESTION.md`](.claude/INGESTION.md), [`DATABASE.md`](.claude/DATABASE.md), [`KNOWLEDGE-GRAPH.md`](.claude/KNOWLEDGE-GRAPH.md), [`FRONTEND.md`](.claude/FRONTEND.md) — design tecnico per area
- [`.claude/COMMANDS.md`](.claude/COMMANDS.md) — cheatsheet comandi quotidiani (dev, test, DB, Apache, deploy)
- [`.claude/reserved-words.txt`](.claude/reserved-words.txt) — username vietati

## Bootstrap dataset

Tutti i `topics` curated (province, comuni ISTAT, brand, ...) sono backuppati
in [`data/topics.parquet`](data/topics.parquet). Su un DB vergine basta un
import:

```bash
cd backend
python -m app.utils.topics_snapshot import --in ../data/topics.parquet
```

Per (ri)generare il file dai CSV grezzi e dettagli sui CLI vedi
[`backend/README.md`](backend/README.md#dataset--snapshot).

## Deploy in produzione

```bash
# Sul server, come utente youfeed:
cd /opt/youfeed
./infra/scripts/deploy.sh
```

Vedi [`infra/systemd/README.md`](infra/systemd/README.md) per il setup iniziale.
