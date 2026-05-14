# Backend

Descrizione tecnica del backend Python di YOUFEED.

## Stack
- **Framework**: FastAPI (async, OpenAPI integrato, type hints)
- **ORM**: SQLAlchemy 2.x (async) + Alembic per le migrazioni
- **Validazione**: Pydantic v2
- **Reverse proxy**: Apache (HTTPS termination interna, mod_proxy)
- **CDN/WAF**: Cloudflare davanti ad Apache
- **Geo/ASN filtering**: MaxMind MMDB (GeoLite2 ASN + Country) caricati in memoria
- **Code asincrone**: RQ (Redis Queue) — invio email, fetch ingestion on-demand, web push, batch activity log
- **Cache / sessioni / RQ broker**: Redis
- **Search**: Manticore (full-text)
- **Database**: PostgreSQL (vedi [DATABASE.md](DATABASE.md))
- **Email**: SMTP OVH (casella email su dominio `youfeed.it`, server `ssl0.ovh.net`, STARTTLS porta 587 o SSL/TLS porta 465) per verifica e reset password
- **Auth Google**: `authlib` per OAuth
- **Web push**: `pywebpush` con chiavi VAPID
- **Template HTML**: Jinja2 (incluso in FastAPI) per pagine pubbliche `/{username}/...`, home pubblica, RSS, sitemap, error pages — vedi [FRONTEND.md](FRONTEND.md) per la divisione Jinja vs Vue SPA
- **Test**: pytest + httpx AsyncClient

## Architettura di deploy
```
Internet → Cloudflare → Apache (HTTPS, mod_proxy) → FastAPI (Uvicorn workers)
                                                  → Static Vue (build) servito da Apache
                                  ↓
                            Redis (sessioni, RQ, cache)
                                  ↓
                        Worker RQ (Python, stessa codebase)
                                  ↓
                          PostgreSQL + Manticore
```

## Autenticazione e sessioni

### Sessione server-side, due transport
Una sola tabella `auth_sessions` lato server, accessibile in due modi:
- **Web**: cookie `yf_session` (`HttpOnly; Secure; SameSite=Lax`)
- **App Android (futuro)**: header `Authorization: Bearer <token>` — stesso `session_id`, restituito nel body di `/yf_auth/login` quando il client invia `X-YF-Client: android`

Vantaggio: revoca, scadenza e device management identici per web e mobile.

### Device fingerprint
- Lato client: **FingerprintJS** (open source) genera un hash deterministico
- Inviato come header `X-YF-Fingerprint` su login e su tutte le richieste successive
- Salvato in `auth_sessions.fingerprint`
- Permette: distinguere device dello stesso utente, riconoscere session theft (cookie usato da altro fingerprint), popolare `/yf_me/devices`

### Reserved usernames
- Lista in `.claude/reserved-words.txt` (base iniziale, espandibile)
- Validata in `POST /yf_auth/register` e `GET /yf_auth/username-available`
- Nessuna collisione con `/yf_*` perché tutti gli username che iniziano con `yf_` sono riservati di default

## Routing

Tutte le rotte applicative iniziano con prefisso **`/yf_`** per non collidere con `/{username}` pubblico.

### Tabella endpoint

#### Auth (8)
| Metodo | Path | Note |
|---|---|---|
| POST | `/yf_auth/register` | username + email + password → invia email verifica |
| GET | `/yf_auth/verify-email` | query `?token=...` |
| POST | `/yf_auth/resend-verification` | |
| GET | `/yf_auth/username-available` | query `?u=...` |
| GET | `/yf_auth/google/authorize` | redirect a Google |
| GET | `/yf_auth/google/callback` | |
| POST | `/yf_auth/login` | email/username + password + fingerprint |
| POST | `/yf_auth/logout` | |

#### Profilo / password (4)
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_me` | profilo utente corrente |
| POST | `/yf_me/change-password` | autenticato |
| POST | `/yf_auth/forgot-password` | invia email reset |
| POST | `/yf_auth/reset-password` | token + nuova password |

#### Device management (2)
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_me/devices` | sessioni attive (fingerprint, last_seen, geo) |
| DELETE | `/yf_me/devices/{id}` | revoca sessione |

#### Categorie (4) — alberatura `parent_id`
| Metodo | Path |
|---|---|
| GET | `/yf_me/categories` |
| POST | `/yf_me/categories` |
| PATCH | `/yf_me/categories/{id}` |
| DELETE | `/yf_me/categories/{id}` |

#### Fonti (5) — relazione 1:N con categorie via `category_id`
| Metodo | Path | Note |
|---|---|---|
| POST | `/yf_sources/discover` | URL → ritorna feed RSS trovati (no scrittura) |
| GET | `/yf_me/sources` | |
| POST | `/yf_me/sources` | crea, deve avere `category_id` |
| PATCH | `/yf_me/sources/{id}` | rinomina, sposta in altra categoria |
| DELETE | `/yf_me/sources/{id}` | |

#### Alert (5)
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_me/alerts` | |
| POST | `/yf_me/alerts` | type: `string` \| `brand` \| `person` |
| PATCH | `/yf_me/alerts/{id}` | |
| DELETE | `/yf_me/alerts/{id}` | |
| GET | `/yf_me/alerts/{id}/matches` | articoli che hanno fatto match |

#### Notifiche utente (2)
| Metodo | Path |
|---|---|
| GET | `/yf_me/notifications` |
| PATCH | `/yf_me/notifications/{id}/read` |

#### Web push (3)
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_push/vapid-key` | chiave pubblica VAPID |
| POST | `/yf_me/push/subscriptions` | endpoint, p256dh, auth |
| DELETE | `/yf_me/push/subscriptions/{id}` | |

#### Home (2)
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_home/public` | non loggato: news raggruppate per topic |
| GET | `/yf_home/me` | loggato: timeline + categorie |

#### Search (3) — Manticore
| Metodo | Path | Note |
|---|---|---|
| GET | `/yf_search` | se loggato → solo feed dell'utente; altrimenti globale |
| GET | `/yf_search/suggest` | autocomplete topic/brand/persona |
| GET | `/yf_search/sources` | autocomplete fonti |

#### Topic catalog (2) — per home pubblica
| Metodo | Path |
|---|---|
| GET | `/yf_topics` |
| GET | `/yf_topics/{slug}` |

#### Activity tracking (1)
| Metodo | Path | Note |
|---|---|---|
| POST | `/yf_track` | batch eventi client (impression, click, dwell, scroll, search) |

#### Trasversali (2)
| Metodo | Path |
|---|---|
| GET | `/yf_health` |
| GET | `/yf_version` |

#### Pagine pubbliche `/{username}/...` (HTML + RSS)
Servite con un **dispatcher** unico via path catch-all `/{username}/{rest:path}`:

| Path | Risposta |
|---|---|
| `/{username}` | HTML profilo + ultime news pubbliche |
| `/{username}/rss` | RSS feed completo |
| `/{username}/{category}` | HTML news categoria |
| `/{username}/{category}/rss` | RSS categoria |
| `/{username}/{category}/{subcategory}` | HTML sottocategoria |
| `/{username}/{category}/{subcategory}/rss` | RSS sottocategoria |
| `/{username}/topic/{name}` | HTML articoli su topic |
| `/{username}/topic/{name}/rss` | RSS topic |

Il dispatcher distingue:
1. `username` validato contro la reserved-words list e la tabella `users`
2. ultimo segmento = `rss` → render RSS, altrimenti HTML
3. secondo segmento = `topic` → branch dedicato

**Totale: ~46 endpoint applicativi + 8 path pubblici parametrici.**

## Middleware (applicati a tutto il traffico)

1. **Cloudflare-aware client IP**: legge `CF-Connecting-IP` quando dietro Cloudflare
2. **MaxMind filter**: lookup ASN + Country, blocca/allowlist secondo policy (ASN cloud provider note, paesi ad alto rischio per scrittura). Caricamento MMDB in memoria allo startup, refresh schedulato
3. **Rate limit**: per IP + per session_id, backed by Redis
4. **CSRF**: solo per richieste cookie-based con metodo non-safe (token in header `X-YF-CSRF`)
5. **Activity log**: ogni richiesta autenticata accodata su RQ → batch insert in `activity_log` (vedi [DATABASE.md](DATABASE.md)). Campi: user_id, session_id, fingerprint, route, method, target_id, query_params, status, latency_ms, ip, country, asn, ua, ts. Eventi frontend (`POST /yf_track`) confluiscono nella stessa tabella.

## Worker RQ

Code separate per priorità:
- `email` — verifica, reset, alert digest
- `push` — invio web push
- `ingestion_ondemand` — discover/preview di una nuova fonte
- `activity_log` — batch insert eventi + aggregazione `articles.read_count`/`open_count`/`last_read_at`
- `alerts_match` — quando arrivano nuovi articoli, valuta le regole alert e accoda push/email
- `image_processor` — fetch + resize WebP delle immagini articoli (vedi INGESTION.md)
- `enrich_wikidata` — arricchimento topic da Wikidata su creazione/curation
- `manage_partitions` — manutenzione partizioni daily di `activity_log`
- `retention_sweep` — drop articoli senza engagement oltre soglia + cleanup file immagini locali (vedi DATABASE.md)

## Strutturazione del codice
```
backend/
  app/
    main.py                # FastAPI app, lifespan, middleware
    config.py              # pydantic-settings
    deps.py                # dependency injection (current_user, db, redis)
    middleware/
      cloudflare.py
      maxmind.py
      ratelimit.py
      activity_log.py
    routers/
      auth.py
      me.py
      sources.py
      categories.py
      alerts.py
      push.py
      search.py
      home.py
      topics.py
      track.py
      public.py            # dispatcher /{username}/...
    services/              # logica di dominio (auth_service, feed_service, ...)
    repositories/          # accesso DB
    schemas/               # Pydantic in/out
    models/                # SQLAlchemy
    workers/               # job RQ
    rss/                   # generazione RSS feed
  alembic/
  tests/
  pyproject.toml
```

## Scelte fissate
- FastAPI ✓
- Apache + Cloudflare ✓
- RQ + Redis ✓
- PostgreSQL ✓
- Manticore ✓
- MaxMind MMDB ✓
- Cookie session + fingerprint (FingerprintJS) ✓
- Bearer token su stessa sessione per app Android ✓
- 1:N categorie→fonti ✓
- Web push (VAPID) ✓
- OVH SMTP per email (casella su dominio youfeed.it) ✓
- Activity log su Postgres partizionato per giorno

## Da definire
- Strategia partizionamento `activity_log` (manuale per data o `pg_partman`)
- Versioning API (per ora niente, in futuro `/yf_v2_*`)
- Politica MaxMind: lista esplicita di ASN/country da bloccare o allowlist
- Quando esporre OpenAPI schema (`/yf_docs` solo in dev?)
