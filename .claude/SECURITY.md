# SECURITY — gestione del traffico indesiderato

YouFeed è **IT-only** per audience e contenuti. Il traffico utile arriva dall'Italia
(e in misura minore da paesi europei limitrofi); il resto è quasi sempre rumore:
scanner di vulnerabilità, scraper, brute-force su `/yf_auth/*`, crawler che non
rispettano `robots.txt`.

Questa sezione descrive il layer di blocco a livello applicativo per:

1. **Bloccare per country o ASN** (mossa massiccia: niente dall'AS-XXXX di un VPS
   russo, niente dalla Cina, ecc.)
2. **Raccogliere telemetria** sui blocchi per spottare anomalie (picchi improvvisi
   da un paese, traffico raro ma costante da un ASN).

## Architettura

```
┌────────────┐  CF-Connecting-IP                                       │
│ Cloudflare │ ───────────┐                                            │
└────────────┘            ▼                                            │
                ┌─────────────────────┐                                │
                │ GeoIPMiddleware     │  popola request.state.country  │
                │ (MaxMind MMDB)      │  e .asn                        │
                └─────────────────────┘                                │
                          │                                            │
                          ▼                                            │
                ┌─────────────────────┐  ┌──────────────────────────┐  │
                │ TrafficBlockMW      │←─│ blocked_countries (PG)   │  │
                │ (questo modulo)     │  │ blocked_asns      (PG)   │  │
                │                     │  │ cache in-memory 60s      │  │
                │  country ∈ block?   │  └──────────────────────────┘  │
                │  asn ∈ block?       │                                │
                │   ↓ sì              │                                │
                │  403 + log SQLite   │──▶ /var/lib/youfeed/security.db│
                │   ↓ no              │                                │
                └─────────────────────┘                                │
                          │                                            │
                          ▼                                            │
                  resto del middleware                                 │
```

## Componenti

### 1. Tabelle Postgres — config (admin gestisce)

- **`blocked_countries`**: `iso_code` (PK, char(2)), `note` (text, opz.),
  `created_at`. Esempio: `('RU', 'scanner brute-force 2026-05-14')`.
- **`blocked_asns`**: `asn` (PK, integer), `note`, `created_at`. Esempio:
  `(14061, 'DigitalOcean VPS scraper')`.

Modifiche via `/yf_admin/security/blocks` (CRUD form-POST classico). Il
middleware ricarica la lista ogni 60s (TTL in-memory) — in alternativa, dopo
ogni add/remove il router chiama una `invalidate_block_cache()` esplicita.

### 2. SQLite — eventi (forensics)

File: `/var/lib/youfeed/security.db` (path da `settings.security_db_path`).
WAL mode (`PRAGMA journal_mode=WAL`) per consentire scritture concorrenti
dai 4 uvicorn worker.

Schema:

```sql
CREATE TABLE block_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,            -- unix timestamp
    ip        TEXT,
    country   TEXT,                        -- ISO-2 (es. 'RU')
    asn       INTEGER,
    method    TEXT,
    path      TEXT,
    user_agent TEXT,
    reason    TEXT NOT NULL                -- 'country' | 'asn'
);
CREATE INDEX ix_block_events_ts ON block_events(ts DESC);
CREATE INDEX ix_block_events_country_ts ON block_events(country, ts DESC);
CREATE INDEX ix_block_events_asn_ts ON block_events(asn, ts DESC);
CREATE INDEX ix_block_events_ip_ts ON block_events(ip, ts DESC);
```

Perché SQLite e non Postgres? Tre motivi:

1. **Isolamento**: gli eventi di sicurezza non devono inquinare il DB applicativo
   né rischiare di rallentarlo se sotto attacco.
2. **Ricerche libere**: una singola tabella append-only è perfetta per query
   ad hoc (`WHERE country='RU' AND ts > strftime('%s', 'now', '-1 day')`).
3. **Retention semplice**: vacuum/drop di righe vecchie senza toccare il
   partition manager del main DB.

Volume atteso: 1 write per ogni richiesta bloccata. Per traffico tipico
(VPS scanner, scraper) attesi <10k eventi/giorno → SQLite WAL gestisce
tranquillamente.

### 3. TrafficBlockMiddleware

Posizionato **dopo** `GeoIPMiddleware` nello stack (così `request.state.country`
e `.asn` sono già popolati). Logica:

```python
country = request.state.country
asn = request.state.asn
if country in BLOCKED_COUNTRIES or asn in BLOCKED_ASNS:
    await log_block_event(request, reason="country" if country in ... else "asn")
    return PlainTextResponse("Forbidden", status_code=403)
return await call_next(request)
```

Niente eccezioni per `/yf_admin/*`: decisione del proprietario (vedi sotto).

### 4. Admin UI — `/yf_admin/security/*`

Sotto un nuovo top-level "Security" nel menù admin:

- **`/security/blocks`** — due liste (country + ASN) con form di aggiunta
  inline + delete. Niente edit (le note sono cosmetiche; per cambiarle si
  cancella e ricrea).
- **`/security/events`** — eventi recenti con filtri per country/ASN/IP/path
  + finestra temporale. Default: ultime 24h, ordinato per ts desc.
- **`/security/stats`** — aggregati: top country bloccati ultimi 7g, top ASN,
  top IP (per spottare scanner singoli), top path (per capire cosa cercano).

## Decisioni operative

### Admin NON è esente dal blocco

Se accidentalmente blocchi il tuo paese o ASN, perdi accesso a `/yf_admin`.
Recovery: SSH al server + `psql youfeed -c "DELETE FROM blocked_countries
WHERE iso_code = 'IT'"` (o equivalente per ASN). Il middleware ricarica la
cache entro 60s.

Alternativa più sicura considerata e scartata: allowlist di IP admin in env.
Aggiunge complessità (rotazione IP residenziali, VPN dinamiche) per un caso
limite gestibile a mano. Riapriremo se diventa frequente.

### Cosa NON blocchiamo qui

- **IP singoli o CIDR**: scope futuro. Per ora si fa via Cloudflare WAF se
  serve (gestito fuori da YouFeed).
- **Rate limit per IP**: già esiste `RateLimitMiddleware` (60/min anon,
  600/min user) — quello vive a un layer diverso.
- **User-agent / pattern URI**: niente WAF applicativo. Cloudflare basta.

### Performance

- Lookup country/ASN: hash-set in memoria, O(1).
- Reload cache: una `SELECT` da due tabelle piccole (~decine di righe attese).
  Costo ammortizzato su tutte le richieste del minuto.
- Write SQLite: solo su 403, async via `aiosqlite`. In caso di errore di
  scrittura → log warning, niente fallimento user-facing (the block itself
  still happens).

## Future work

- **Log di tutto il traffico** (non solo blocchi) per anomaly detection
  "rare-but-constant": esiste già `activity_log` in Postgres (vedi
  [middleware/activity_log.py](../backend/app/middleware/activity_log.py)),
  che cattura ip/country/asn/route/status. Aggiungere query e dashboard
  admin sopra a quella tabella invece di duplicare nel SQLite.
- **CIDR blocking**: estendere `blocked_asns` con tabella `blocked_cidrs`
  e check con `ipaddress.ip_network`.
- **Auto-suggest blocks**: cron che analizza `activity_log` e propone in
  admin "i 5 ASN che ti hanno fatto più 4xx ieri".
- **TTL/expiry sui blocchi**: blocchi temporanei (`expires_at`) per
  campagne di scanner brevi senza dover ricordare di ripulire.

## Recovery / unblock veloce

```bash
# Da SSH, su prod:
sudo -u postgres psql youfeed -c "DELETE FROM blocked_countries WHERE iso_code = 'IT';"
sudo -u postgres psql youfeed -c "DELETE FROM blocked_asns WHERE asn = 1234;"
# La cache in-memory si refresha entro 60s; se urgente:
./infra/scripts/restart.sh api
```

Per ispezionare gli eventi senza UI:

```bash
sqlite3 /var/lib/youfeed/security.db "SELECT datetime(ts, 'unixepoch'), country, asn, ip, path FROM block_events ORDER BY ts DESC LIMIT 20;"
```
