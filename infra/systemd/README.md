# systemd units YOUFEED

Da copiare in `/etc/systemd/system/` sul server di produzione.

## Unit

| File | Descrizione |
|---|---|
| `yf-api.service` | API FastAPI + Uvicorn (4 worker) |
| `yf-worker@.service` | template parametrico, una istanza per coda RQ |
| `yf-scheduler.service` | scheduler ingestion (tick + dispatch) |
| `yf-manage-partitions.{service,timer}` | partition maintenance giornaliera (02:30 UTC) |
| `yf-reclassify-topics.{service,timer}` | reclassify articoli 2x/giorno (04:00 + 16:00 UTC) per riassorbire correzioni admin sui topic |
| `yf-topics-snapshot.{service,timer}` | backup Parquet topics ogni notte (03:00 UTC) |

## Code v1.0

Avviare un'istanza del template `yf-worker@.service` per ciascuna coda:

```bash
sudo systemctl enable --now yf-worker@discover.service
sudo systemctl enable --now yf-worker@fetch_rss.service
sudo systemctl enable --now yf-worker@fetch_wp.service
sudo systemctl enable --now yf-worker@process_article.service   # MVP collassato
sudo systemctl enable --now yf-worker@image_processor.service
sudo systemctl enable --now yf-worker@email.service
sudo systemctl enable --now yf-worker@activity_log.service
sudo systemctl enable --now yf-worker@manage_partitions.service
```

Code aggiunte in v1.1+ (vedi STATUS.md):

```bash
# v1.2
sudo systemctl enable --now yf-worker@push.service
sudo systemctl enable --now yf-worker@alerts_match.service
sudo systemctl enable --now yf-worker@enrich_wikidata.service
sudo systemctl enable --now yf-worker@retention_sweep.service
```

## Timer (job ricorrenti)

```bash
# Già v1.0: partition maintenance giornaliera
sudo systemctl enable --now yf-manage-partitions.timer

# Reclassify articoli vs stato corrente dei topic — 04:00 + 16:00 UTC
sudo systemctl enable --now yf-reclassify-topics.timer

# Backup Parquet dei topic — 03:00 UTC, file unico sovrascritto in
# /opt/youfeed/data/topics-snapshot.parquet
sudo systemctl enable --now yf-topics-snapshot.timer
```

Per ispezionarli:
```bash
systemctl list-timers 'yf-*' --no-pager
journalctl -u yf-reclassify-topics -n 50 --no-pager
journalctl -u yf-topics-snapshot -n 50 --no-pager
```

## Setup iniziale

```bash
# 1. Creazione utente di servizio
sudo useradd --system --home-dir /opt/youfeed --shell /usr/sbin/nologin youfeed

# 2. Directory dati
sudo mkdir -p /var/lib/youfeed/{images,maxmind} /var/log/youfeed
sudo chown -R youfeed:youfeed /var/lib/youfeed /var/log/youfeed

# 3. Repo + venv
sudo -u youfeed git clone <repo-url> /opt/youfeed
cd /opt/youfeed
sudo -u youfeed python3.12 -m venv .venv
sudo -u youfeed .venv/bin/pip install -e backend

# 4. Env
sudo -u youfeed cp .env.example .env
sudo -u youfeed nano .env   # popola valori reali

# 5. Migrations
sudo -u youfeed .venv/bin/alembic -c backend/alembic.ini upgrade head

# 6. Build frontend
cd frontend && sudo -u youfeed npm ci && sudo -u youfeed npm run build

# 7. Apache + systemd
sudo cp infra/apache/youfeed.conf /etc/apache2/sites-available/
sudo a2ensite youfeed
sudo systemctl reload apache2

sudo cp infra/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yf-api yf-scheduler
# + tutti i yf-worker@<coda> sopra
```

## Deploy successivo

Vedi `infra/scripts/deploy.sh`.
