# Cheatsheet — comandi quotidiani

Riferimento rapido per sviluppo e operatività YOUFEED. Path assoluti riferiti
a `/home/francesco/code/youfeed`. Quando dico "alla root" intendo quella dir.

---

## Avvio sviluppo (3 shell)

```bash
# Shell A — Servizi di supporto (Postgres + Redis + Manticore)
cd /home/francesco/code/youfeed
docker-compose up -d
docker-compose ps             # verifica che siano "healthy"
docker-compose logs -f manticore   # tail di un servizio specifico
docker-compose down           # stop (i dati restano nei volume)
docker-compose down -v        # stop + cancella i dati (reset totale)

# Shell B — Backend FastAPI
cd /home/francesco/code/youfeed
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Shell C — Frontend Vite (HMR)
cd /home/francesco/code/youfeed/frontend
npm run dev                   # http://localhost:5173 (proxy /yf_ → :8000)
```

Apache fa da reverse proxy in dev su `http://www.youfeed.it/`. Vedi
[001.youfeed.it.conf](../infra/apache/001.youfeed.it.conf).

---

## Backend Python

Tutti i comandi vanno eseguiti **dalla cartella `backend/`** con il venv attivo.

### Quality

```bash
ruff check app tests          # lint (warning/errori)
ruff check --fix app tests    # autofix dove possibile
ruff format app tests         # formatter
pyright app                   # type checker
```

### Test

```bash
pytest                        # tutti
pytest -v tests/unit          # solo unit, verbose
pytest -m "not integration"   # esclude i test che richiedono PG/Redis/Manticore live
pytest tests/unit/test_passwords.py::test_hash_and_verify_round_trip  # singolo
pytest --cov=app tests/       # coverage (richiede pytest-cov)
```

### Alembic — migrazioni schema Postgres

```bash
alembic current               # rivision applicata sul DB corrente
alembic history               # catena delle migration
alembic upgrade head          # applica tutte le pending
alembic upgrade +1            # applica solo la prossima
alembic downgrade -1          # rollback ultima
alembic downgrade base        # azzera tutto (drop)

# Crea nuova migration manuale
alembic revision -m "aggiunge campo X"
# Crea nuova migration autogenerata dal diff modelli ↔ DB
alembic revision --autogenerate -m "aggiunge campo X"

# Genera SQL senza applicare (per review prima di andare in prod)
alembic upgrade head --sql > /tmp/migration.sql
```

### Seed loader (idempotente)

```bash
# Dalla cartella backend/
python -m app.utils.seed_loader \
    --reserved-words ../Claude/reserved-words.txt \
    --topics ../infra/seed/topics.yaml \
    --featured ../infra/seed/featured_sources.yaml
```

Esegue upsert: rieseguibile in sicurezza dopo aver aggiunto entry ai file YAML.

---

## Frontend (Vue + Vite)

Tutti i comandi dalla cartella `frontend/`.

```bash
npm install                   # solo la prima volta o quando cambia package.json
npm run dev                   # dev server con HMR su :5173
npm run build                 # build di produzione → dist/
npm run preview               # serve la build per smoke test
npm run lint                  # eslint
npm run lint:fix              # eslint --fix
npm run format                # prettier
npm run type-check            # vue-tsc (controllo tipi sul codice Vue)
npm run test:unit             # vitest (unit)
npm run test:unit:watch       # vitest in watch
npm run test:e2e              # playwright
npm run test:e2e:ui           # playwright con UI
```

---

## Postgres

### Setup iniziale (una tantum)

```bash
# 1. utente + database
sudo -u postgres psql <<'SQL'
CREATE USER youfeed WITH ENCRYPTED PASSWORD 'youfeed';
CREATE DATABASE youfeed OWNER youfeed;
GRANT ALL PRIVILEGES ON DATABASE youfeed TO youfeed;
SQL

# 2. Postgres 15+: il proprietario del DB NON ha automaticamente privilegi sullo
#    schema `public`. Senza questo, Alembic fallisce con
#    "permission denied for schema public":
sudo -u postgres psql -d youfeed <<'SQL'
GRANT ALL ON SCHEMA public TO youfeed;
ALTER SCHEMA public OWNER TO youfeed;
SQL

# 3. Estensioni Postgres usate dal nostro schema. Vanno create da superuser
#    una volta sola (le migration usano IF NOT EXISTS, quindi sono idempotenti).
sudo -u postgres psql -d youfeed <<'SQL'
CREATE EXTENSION IF NOT EXISTS citext;     -- email/username case-insensitive
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
SQL
```

### Operazioni quotidiane

```bash
# Connessione via container (docker-compose)
docker exec -it yf-postgres psql -U youfeed youfeed

# Connessione locale (se hai psql installato)
psql postgresql://youfeed:youfeed@localhost:5432/youfeed

# Query frequenti dentro psql:
\dt                           # lista tabelle
\d articles                   # schema di una tabella
\d+ articles                  # schema + indici + statistiche
\di                           # lista indici
SELECT count(*) FROM articles;
SELECT * FROM activity_log_2026_05_05 LIMIT 5;   # query su una partizione specifica
\q                            # quit

# Dump/restore manuali
pg_dump --format=custom --no-owner -f /tmp/yf.dump \
    postgresql://youfeed:youfeed@localhost:5432/youfeed
pg_restore --clean --if-exists -d \
    postgresql://youfeed:youfeed@localhost:5432/youfeed /tmp/yf.dump
```

### Gestione partizioni `activity_log`

```sql
-- Crea partizione per una data specifica
SELECT yf_create_activity_partition('2026-05-15');

-- Drop partizioni > 180 giorni (ritorna numero di tabelle droppate)
SELECT yf_drop_old_activity_partitions(180);

-- Vedi tutte le partizioni esistenti
SELECT inhrelid::regclass FROM pg_inherits
WHERE inhparent = 'activity_log'::regclass;
```

---

## Manticore

```bash
# Apply DDL (riapplicabile, è IF NOT EXISTS)
mysql -h 127.0.0.1 -P 9306 < backend/manticore/articles_rt.sql

# Connessione SQL (porta 9306, protocollo MySQL)
mysql -h 127.0.0.1 -P 9306

# Query dalla CLI
SHOW TABLES;
DESC articles_rt;
SELECT id, title FROM articles_rt LIMIT 10;
SELECT count(*) FROM articles_rt;

# Inserimento manuale (per smoke test)
INSERT INTO articles_rt (id, title, description, content_text, source_id, source_domain,
                         topic_ids, topic_slugs_csv, published_at, kind)
VALUES (1, 'titolo prova', 'descrizione', 'corpo testo prova',
        1, 'example.com', (1,2), 'inter,milan', UNIX_TIMESTAMP(), 'rss');

# Search full-text
SELECT id, title FROM articles_rt WHERE MATCH('inter milano') ORDER BY published_at DESC LIMIT 20;

# Backup nativo (output su disco del server Manticore)
BACKUP TABLE articles_rt TO '/var/lib/manticore/backups';

# HTTP/JSON (alternativa al SQL, porta 9308)
curl -s 'http://127.0.0.1:9308/cli' -d 'SHOW TABLES'
```

---

## Redis

```bash
# CLI nel container
docker exec -it yf-redis redis-cli
# Oppure locale
redis-cli -h 127.0.0.1 -p 6379

# Query frequenti
PING                          # → PONG
KEYS yf:*                     # lista chiavi YOUFEED (no in produzione, usa SCAN)
GET yf:rl:anon:127.0.0.1:29345678   # rate limit corrente
LLEN yf:activity:queue        # eventi pendenti per il worker activity_log
LRANGE yf:activity:queue 0 4  # primi 5 eventi (più recenti)
DBSIZE                        # numero totale chiavi
FLUSHDB                       # azzera (solo in dev!)
```

---

## Apache

```bash
# Verifica sintassi conf prima di applicarla
sudo apache2ctl configtest

# Restart / reload
sudo systemctl restart apache2
sudo systemctl reload apache2     # ricarica conf senza droppare connessioni

# Log tail
tail -f logs/access.$(date +%F).log
tail -f logs/error.$(date +%F).log

# Lista moduli caricati
sudo apache2ctl -M

# Abilita/disabilita modulo
sudo a2enmod headers
sudo a2dismod headers
sudo a2enmod proxy_wstunnel       # WS per HMR Vite

# Abilita/disabilita vhost
sudo a2ensite 001.youfeed.it
sudo a2dissite 001.youfeed.it
```

---

## Workflow Git

```bash
git status
git diff
git diff --staged
git log --oneline -20
git checkout -b feat/nome-feature
git add <file>
git commit -m "messaggio"
git push -u origin feat/nome-feature
```

Mai forzare push su `main` senza essere sicurissimi.

---

## Deploy in produzione

Sul server, come utente `youfeed`:

```bash
cd /opt/youfeed
./infra/scripts/deploy.sh     # git pull + pip + alembic + npm build + restart
```

Setup iniziale e configurazione systemd in
[../infra/systemd/README.md](../infra/systemd/README.md).

---

## Backup / restore

```bash
# Backup notturno completo (cron suggerito, vedi script per opzioni)
./infra/scripts/backup.sh

# Restore Postgres (su DB pulito)
pg_restore --clean --if-exists -d postgresql://youfeed:youfeed@.../youfeed \
    /var/backups/youfeed/2026-05-05-030000/postgres.dump

# Restore Manticore: i file in /var/backups/youfeed/<ts>/manticore vanno
# copiati nella data_dir di Manticore con il searchd fermo, poi riavviare.
```

---

## MaxMind MMDB (refresh mensile)

```bash
# Una tantum: registrati su https://www.maxmind.com/en/geolite2/signup,
# ottieni la license key e mettila in .env (MAXMIND_LICENSE_KEY=...).

./infra/scripts/maxmind-refresh.sh

# Cron suggerito (utente youfeed):
# 0 3 1 * * /opt/youfeed/infra/scripts/maxmind-refresh.sh >> /var/log/youfeed/maxmind.log 2>&1
```

---

## Troubleshooting frequente

| Sintomo | Probabile causa | Cosa fare |
|---|---|---|
| `Invalid command 'Header'` | mod_headers non abilitato | `sudo a2enmod headers && sudo systemctl restart apache2` |
| 502 sui path SPA in dev | Vite dev server non in esecuzione | `cd frontend && npm run dev` |
| 502 su `/yf_*` | Backend FastAPI non in esecuzione | `cd backend && uvicorn app.main:app --reload --port 8000` |
| Alembic: "target database is not up to date" | Modello modificato senza migration | `alembic revision --autogenerate -m "..."` poi `alembic upgrade head` |
| `cannot connect to postgres` | Container PG fermo o porta occupata | `docker-compose ps` poi `docker-compose up -d postgres` |
| `permission denied for schema public` | PG15+, owner DB senza grant sullo schema | `sudo -u postgres psql -d youfeed -c "GRANT ALL ON SCHEMA public TO youfeed; ALTER SCHEMA public OWNER TO youfeed;"` |
| `permission denied to create extension "citext"` | Estensione richiede privilegi superuser | `sudo -u postgres psql -d youfeed -c "CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pgcrypto;"` |
| `KeyError: 'YF_SECRET_KEY'` all'avvio | `.env` non caricato o variabile mancante | `cp .env.example .env` e popola `YF_SECRET_KEY` |
| Pyright: errori a raffica su `models/*` | Lib non installate nell'env corrente | Verifica `which python` punti al `.venv`; reinstalla `pip install -e "./backend[dev]"` |
| HMR Vite non aggiorna passando per Apache | mod_proxy_wstunnel non abilitato | `sudo a2enmod proxy_wstunnel && sudo systemctl restart apache2` |
| Cookie sessione non viene impostato in dev | `SESSION_COOKIE_SECURE=true` con HTTP | In `.env` metti `SESSION_COOKIE_SECURE=false` (true solo in prod HTTPS) |
| `429 rate_limited` durante test | Rate limit attivo | Pulisci con `redis-cli FLUSHDB` (DB 0) |
| Manticore: `unknown option 'lemmatize_it_all'` | Lemmatizer IT non esiste | Usa `morphology = libstemmer_it` (vedi [DATABASE.md](DATABASE.md)) |

---

## Ambiente Python — gestione `.venv`

```bash
# (Re)crea da zero
cd /home/francesco/code/youfeed
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e "./backend[dev]"

# Aggiorna deps dopo cambio pyproject.toml
pip install -e "./backend[dev]" --upgrade

# Disattiva venv
deactivate

# Genera requirements lock (opzionale, per CI o deploy senza pip install -e)
pip freeze > backend/requirements.lock.txt
```

---

## Generazione segreti

```bash
# YF_SECRET_KEY (32+ byte casuali, base64 url-safe)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# VAPID keypair (Phase 1.2 — push notifications)
python3 -c "from py_vapid import Vapid01; v = Vapid01(); v.generate_keys(); \
    print('PUBLIC:', v.public_key.public_numbers()); \
    print('PRIVATE:', v.private_key.private_numbers())"
# (richiede py-vapid: pip install py-vapid)
```

---

## Note finali

- Tutti i comandi presumono `.venv` attivo per Python e Node 20+ disponibile.
- I comandi `docker-compose ...` richiedono `docker compose` v2 o `docker-compose` v1.
- Quando aggiungi nuovi comandi quotidiani, mettili qui — è la fonte di verità per
  i task ricorrenti, non STATUS.md (che invece traccia l'avanzamento delle phase).
