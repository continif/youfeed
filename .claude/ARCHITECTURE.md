# Architettura YOUFEED

## Panoramica
YOUFEED è composto da tre livelli indipendenti che comunicano tra loro:

1. **Ingestion** (Python) — recupero, parsing e normalizzazione dei contenuti dalle fonti (RSS, scraping siti)
2. **Backend** (Python) — API per il frontend, gestione utenti, feed personalizzati, notifiche, esportazione RSS
3. **Frontend** (Vue.js) — interfaccia utente per gestire feed, categorie, notifiche e visualizzare contenuti

## Diagramma logico

```
[Fonti esterne: RSS / Siti web]
              |
              v
        [Ingestion Python]  --->  [Database notizie]
                                         ^
                                         |
[Frontend Vue.js] <---HTTP/JSON--- [Backend Python] <---> [Database utenti/feed]
                                         |
                                         v
                                   [Notifiche / Export RSS]
```

## Componenti principali

### Ingestion
Diviso in due sottosistemi:
- **Elaborazione URL** (on-demand): qualifica una URL utente come `rss`, `wordpress_api` o `invalid`
- **Ingestion vera e propria** (schedulata): due pipeline parallele (WP API + RSS) che convergono nel salvataggio articolo + estrazione entità
- L'output alimenta il **Knowledge Graph** (entità, topic, relazioni)
- Vedi [INGESTION.md](INGESTION.md) e [KNOWLEDGE-GRAPH.md](KNOWLEDGE-GRAPH.md)

### Backend
- API REST/GraphQL per il frontend
- Autenticazione (email + Google OAuth)
- Gestione feed pubblici/privati e alberatura categorie
- Generazione feed RSS in uscita
- Motore notifiche (argomenti, brand, personaggi)
- Vedi [BACKEND.md](BACKEND.md)

### Frontend
- SPA Vue.js
- Editor alberatura categorie
- Visualizzazione feed e raggruppamento per argomento
- Configurazione notifiche
- Vedi [FRONTEND.md](FRONTEND.md)

### Database
- Storage notizie (alta scrittura, indicizzazione full-text)
- Storage utenti, feed, categorie, preferenze
- Vedi [DATABASE.md](DATABASE.md)

### Pianificazione
- Scope per release (v1.0 / v1.1 / v1.2 / v2.0) in [MVP.md](MVP.md)
- Sequenza task operativa con stato di avanzamento in [STATUS.md](STATUS.md)

## Comunicazione tra i livelli
- Frontend ↔ Backend: HTTP/JSON
- Backend ↔ Ingestion: condivisione tramite database; eventuale message queue per richieste on-demand di nuove fonti
- Ingestion → Database: scritture batch

## Stack fissato
- **Backend**: FastAPI + SQLAlchemy + Alembic
- **Reverse proxy / TLS**: Apache (mod_proxy)
- **CDN / WAF**: Cloudflare
- **Geo/ASN filtering**: MaxMind MMDB
- **Code asincrone**: RQ (Redis)
- **Sessioni / cache**: Redis
- **Database transazionale**: PostgreSQL (utenti, fonti, categorie, alert, knowledge graph, activity log)
- **Content store + search**: Manticore (titolo/descrizione/contenuto degli articoli vivono qui, non in Postgres)
- **Email**: SMTP OVH (casella su dominio youfeed.it)
- **Auth**: cookie session + FingerprintJS, Bearer token su stessa sessione per app mobile
- **Web push**: VAPID
- **Frontend**: Vue.js (vedi [FRONTEND.md](FRONTEND.md))
- **Ingestion**: Python (vedi [INGESTION.md](INGESTION.md))

## Hosting e deployment

**Hosting**: server singolo Ubuntu (già provisioned). Tutti i componenti coabitano sullo stesso host:
- Apache (HTTPS, mod_proxy, serve `/images/*` e static Vue build)
- FastAPI Uvicorn (multi-worker via systemd unit)
- Worker RQ (un'unit systemd per ruolo: scheduler, fetcher_rss, fetcher_wp, processor, image_processor, ecc.)
- PostgreSQL
- Manticore
- Redis
- File MaxMind MMDB in `/var/lib/youfeed/maxmind/`
- File immagini articoli in `/var/lib/youfeed/images/`

**Deployment**: manuale via SSH, no CI/CD.
1. `git pull origin main` su `/opt/youfeed/`
2. `cd backend && pip install -r requirements.txt`
3. `alembic upgrade head`
4. `cd ../frontend && npm ci && npm run build`
5. `sudo systemctl restart yf-api yf-worker-* yf-scheduler`

Rollback: `git checkout <tag>` + ripeti steps 2-5.

**Migration policy**: schema backward-compatible quando possibile (no rinomina/drop colonne in mid-deploy senza step di transizione), così la finestra "vecchio codice + nuovo schema" non rompe.

## Da definire
- Backup destination (offsite via rsync? S3-compatible?)
- Monitoring concreto (Sentry? Grafana? log centralizzati?)
- Strumenti di ingestion ulteriori e classificazione topic (parametri fini)
