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

## Script operativi

Tutti sotto [`infra/scripts/`](infra/scripts/). Tipicamente lanciati dalla root del repo come `./infra/scripts/<nome>.sh`. Richiedono `.env` nella root (sourciato dai singoli script che ne hanno bisogno).

| Script | A cosa serve | Quando lanciarlo |
|---|---|---|
| [`deploy.sh`](infra/scripts/deploy.sh) | `git pull` + `pip install` + `alembic upgrade head` + `npm run build` + restart servizi. È il flusso completo, niente CI/CD. | Ogni rilascio in produzione. |
| [`restart.sh`](infra/scripts/restart.sh) | Riavvia i systemd unit: `yf-api`, `yf-scheduler`, `yf-activity-log`, worker RQ. Accetta `api` / `workers` / `all` (default). | Dopo modifiche solo a backend Python (template, router) senza pull (es. dev locale di prod). |
| [`backup.sh`](infra/scripts/backup.sh) | `pg_dump --format=custom` + `BACKUP TABLE` Manticore + `rsync --link-dest` immagini. Destinazione `${BACKUP_DIR:-/var/backups/youfeed}/<TS>/` con retention 14 giorni. | Una volta al giorno via cron (TODO: configurare upload offsite). |
| [`maxmind-refresh.sh`](infra/scripts/maxmind-refresh.sh) | Scarica le MMDB di GeoLite2 (ASN + Country) usando `MAXMIND_LICENSE_KEY`. Refresha la cache country JSON sul server. | Una volta al mese via cron. |
| [`check-personalization.sh`](infra/scripts/check-personalization.sh) | Diagnostica end-to-end della pipeline eventi tracking: stato worker + coda Redis + breakdown `activity_log` per `event_type` + counter `articles.read_count`. Accetta una finestra temporale come argomento (default `24h`, es. `1h` / `7d`). | Quando vuoi verificare che gli eventi Phase 1 (preview_open, original_open, ecc.) stiano davvero entrando, o per debugging di lag worker. |

### Permessi e sudo

`restart.sh` chiama `sudo systemctl restart ...` — l'utente che lo esegue deve avere `NOPASSWD` su quei unit o digitare la password. `deploy.sh` finisce con un `restart.sh` interno: stesso requisito.

`backup.sh` chiama `pg_dump` direttamente con `DATABASE_URL_SYNC`, e `rsync` su `${IMAGES_DIR:-/var/lib/youfeed/images}` — quindi l'utente deve avere accesso lettura su quella cartella e scrittura sulla `BACKUP_DIR`.
