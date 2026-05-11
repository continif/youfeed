# Runbook operativo YOUFEED

Documento operativo per l'avvio, monitoraggio e gestione incidenti dei servizi
YOUFEED in produzione (Ubuntu + systemd).

## Componenti

| Servizio | Tipo | Comando | Note |
|----------|------|---------|------|
| `yf-api` | uvicorn FastAPI | `systemctl status yf-api` | listen `127.0.0.1:8000`, dietro Apache |
| `yf-scheduler` | loop async | `systemctl status yf-scheduler` | enqueue fetch_rss/fetch_wp |
| `yf-worker@<queue>` | RQ worker template | `systemctl status yf-worker@fetch_rss` | uno per coda: `email`, `fetch_rss`, `fetch_wp`, `process_article`, `image_processor` |
| `yf-activity-log` | drainer Redis → PG | `systemctl status yf-activity-log` | BLPOP su `yf:activity:queue` |
| `yf-manage-partitions.timer` | timer daily | `systemctl list-timers yf-*` | crea/droppa partizioni `activity_log` |

## Avvio iniziale (deploy nuovo server)

```bash
# 1. Clona il repo come utente youfeed
sudo mkdir -p /opt/youfeed && sudo chown youfeed: /opt/youfeed
sudo -u youfeed git clone <REPO_URL> /opt/youfeed

# 2. Crea venv e installa deps
sudo -u youfeed /usr/bin/python3.12 -m venv /opt/youfeed/.venv
sudo -u youfeed /opt/youfeed/.venv/bin/pip install -e /opt/youfeed/backend

# 3. Copia .env e popola le variabili reali
sudo cp /opt/youfeed/.env.example /opt/youfeed/.env
sudo chmod 600 /opt/youfeed/.env
sudo chown youfeed: /opt/youfeed/.env
sudo nano /opt/youfeed/.env

# 4. DB migrations + seed
cd /opt/youfeed/backend
sudo -u youfeed /opt/youfeed/.venv/bin/alembic upgrade head
sudo -u youfeed /opt/youfeed/.venv/bin/python -m app.utils.seed_loader \
    --reserved-words ../Claude/reserved-words.txt \
    --topics ../infra/seed/topics.yaml \
    --featured ../infra/seed/featured_sources.yaml

# 5. Manticore RT index
mysql -h 127.0.0.1 -P 9306 < /opt/youfeed/backend/manticore/articles_rt.sql

# 6. Frontend build
cd /opt/youfeed/frontend
sudo -u youfeed npm ci
sudo -u youfeed npm run build  # output in dist/

# 7. systemd units
sudo cp /opt/youfeed/infra/systemd/yf-*.service /etc/systemd/system/
sudo cp /opt/youfeed/infra/systemd/yf-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yf-api yf-scheduler yf-activity-log
sudo systemctl enable --now yf-worker@email yf-worker@fetch_rss yf-worker@fetch_wp \
    yf-worker@process_article yf-worker@image_processor
sudo systemctl enable --now yf-manage-partitions.timer

# 8. Apache vhost
sudo cp /opt/youfeed/infra/apache/youfeed.conf /etc/apache2/sites-available/
sudo a2ensite youfeed
sudo a2enmod proxy proxy_http proxy_wstunnel headers
sudo systemctl reload apache2
```

## Deploy update (deployment ricorrente)

```bash
sudo -u youfeed /opt/youfeed/infra/scripts/deploy.sh
```

Il script fa: `git pull`, `pip install`, `alembic upgrade head`, `npm ci && npm run build`, `systemctl restart yf-*`.

## Restart selettivo

```bash
sudo systemctl restart yf-api               # API soltanto
sudo systemctl restart yf-worker@fetch_rss  # un singolo worker
sudo systemctl restart yf-scheduler
```

## Monitoraggio

```bash
# Status di tutti i servizi YouFeed
systemctl list-units 'yf-*' --type=service

# Log live di un servizio
journalctl -u yf-api -f
journalctl -u yf-worker@process_article -f --since '1 hour ago'

# Code RQ
redis-cli -n 1 LLEN rq:queue:fetch_rss
redis-cli -n 1 LLEN rq:queue:process_article
redis-cli -n 1 LLEN yf:activity:queue       # buffer activity log

# Stato DB partizioni activity_log
psql -h localhost -U youfeed -d youfeed -c "
  SELECT inhrelid::regclass AS partition
  FROM pg_inherits WHERE inhparent='activity_log'::regclass
  ORDER BY 1 DESC LIMIT 10;
"
```

## Healthcheck

```bash
curl -fs http://127.0.0.1:8000/yf_health | jq .
# Atteso: {"status":"ok","checks":{"postgres":"ok","redis":"ok"}}
```

In caso di errore: `journalctl -u yf-api -n 200` e verifica che PG/Redis/Manticore siano up.

## Backup & restore

```bash
# Backup notturno (cron)
/opt/youfeed/infra/scripts/backup.sh

# Restore (procedura emergenza)
# 1. Postgres: psql + pg_restore dal dump più recente
# 2. Manticore: ripristino dei file `*.spi/*.spl/*.spd` da backup
# 3. Riavvio dei servizi: systemctl restart yf-*
```

## Incidenti tipici

### "L'API non risponde"

1. `systemctl status yf-api` — è running?
2. `journalctl -u yf-api -n 100` — errori in log?
3. `curl localhost:8000/yf_health` — backend ok ma Apache no? `sudo systemctl status apache2`
4. PG/Redis down? `systemctl status postgresql redis-server manticore`

### "Le code RQ accumulano"

1. `redis-cli -n 1 LLEN rq:queue:<nome>` per vedere quanto profondo
2. `systemctl status yf-worker@<nome>` — il worker è up?
3. `journalctl -u yf-worker@<nome> -n 200` — sta fallendo job specifici?
4. Worker bloccato da risorsa esterna (HTTP timeout, fonte morta)? Verifica connettività dal server

### "Sources tutte broken"

1. Test manuale fetch: `curl -A "YouFeed/1.0 (+https://www.youfeed.it/bot)" <url_feed>`
2. La nostra IP è bannata? Verifica con strumenti tipo `httpstat.us`
3. Reset failures: `psql ... -c "UPDATE sources SET status='active', consecutive_failures=0 WHERE status='broken';"`

### "Disk full"

1. `df -h /var/lib/youfeed` — immagini WebP saturate?
2. Pulisci immagini orfane (articoli vecchi droppati): TODO script
3. `journalctl --vacuum-time=7d` riduce log systemd

### "Manticore non indicizza più"

1. Spazio disco (vedi sopra)
2. `mysql -h127.0.0.1 -P9306 -e "SELECT COUNT(*) FROM articles_rt;"` — index integro?
3. Re-process articoli sospesi: `python -m app.utils.reindex --suspicious`
4. Drop+create RT index e ri-indicizza tutto: `python -m app.utils.reindex --all` (lungo)

## Variabili `.env` chiave

Vedi `.env.example` per la lista completa. Quelle che cambiano per ambiente:
- `YF_ENV` (`development|staging|production`) — controlla logging, OpenAPI, cookie secure
- `YF_DEBUG` (`true|false`) — verbose SQL, FastAPI docs
- `SESSION_COOKIE_SECURE` — `true` in prod (HTTPS)
- `LOG_JSON` — `true` in prod per log strutturati

## Contatti

- Owner: Francesco Mastrogiovanni (mastro.francesco@gmail.com)
