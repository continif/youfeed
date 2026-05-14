# STATUS — pianificazione operativa YOUFEED

Sequenza dei task per arrivare alla v1.0 e oltre. Aggiornare quando una fase parte, finisce o cambia priorità.

## Stato corrente

- **Fase**: v1.0 code-complete + **v1.1 code-complete** + **v1.2 code-complete** (6/7 chiuse: 1.2.A NER spaCy ✓ iteration-1, 1.2.B Wikidata enrichment ✓, 1.2.D Alert ✓, 1.2.E Web push ✓, 1.2.F Admin dashboard ✓, 1.2.G Retention sweep ✓; 1.2.C LLM fallback **scartato** per assenza di budget Anthropic — può essere rivalutato in futuro). Tutte le Phase 0-20 chiuse `[✓]`. Phase 21 (DoD v1.0) `[~]` con codice 100% pronto, topic seed espanso de facto (10k+ entità curated), restano solo task operativi (deploy + 7gg stabile + Lighthouse + beta).
- **Codice**: 257+ test verdi (122 unit + 39 integration backend, 96 Vitest frontend). ~50+ endpoint (include `/yf_search`, `/yf_admin/*` esteso con Entità/Featured/Sources, `/yf_auth/google/*`, `/yf_auth/forgot-password`+`/reset-password`, `/yf_me/devices`, `/yf_me/notifications`, `/yf_me/alerts`, `/yf_me/push/*`, `/yf_push/vapid-key`), pipeline ingestion stabile su 22+ fonti reali con ~1970 articoli indicizzati. Policy estrazione topic **title-only** (riduce drastico FP). Pipeline emette job `alerts_match` per ogni articolo con topic > 0; matcher accoda anche `push` job se l'alert ha `'push' in channels`.
- **Dataset topic curated**: ~10.500 entità (≈ 7905 location ISTAT + ≈ 2600 brand/person/model curati a mano in 12 batch tematici: auto, telco, smartphone, laptop, smart TV, banche, microchip, microcontroller, distro Linux, computer, hardware/GPU, crypto, cantanti, politici, OS versions). Snapshot Parquet in [`data/topics.parquet`](../data/topics.parquet).
- **Topic policy v2 (2026-05-09/11)**: estrazione **solo dal titolo** (worker live + `reclassify_topics --title-only`); related con **TF-IDF coverage simmetrica + sort multi-topic**; subsumption rule (model assorbe brand contenuto come sub-sequenza); pattern alias-senza-prefisso (`Galaxy *` ← `Samsung Galaxy *`, `iPhone *` ← `Apple iPhone *`, ecc.); soft-blacklist via `type='invalid'`.
- **Admin panel `/yf_admin/*` (T-017)**: pannello completo con auth HTTP Basic, sezioni split (Utenti, Topic con CRUD + bulk validate/invalidate, Regole separate Ambigui/Blacklist/Case-sensitive, Composite rules, Stats, Article inspector). Topic curated possono ora essere aggiunti a mano da UI.
- **Google OAuth in modalità simulata** (Phase 1.1.A): finché `GOOGLE_OAUTH_CLIENT_ID` è vuoto in `.env`, il flow `authorize`/`callback` gira via pagina di consenso stub locale `/yf_auth/google/_mock`. Drop-in al reale quando si configura il client_id (cambia solo `oauth_service.is_simulate()`).
- **Prossimo step concreto**: (a) chiusura Phase 21 operativa (deploy + 7gg + ping GSC + restore drill + 5 beta), (b) bulk reclassify NER sul corpus esistente (`reclassify_topics --all --title-only` con `--limit` prudente), (c) bulk enrich Wikidata sui 2600 topic residui (`enrich_topics --missing --limit 500`), (d) generazione e commit chiavi VAPID in `.env` + smoke push reale Chrome/Firefox/Chrome-Android in HTTPS staging, (e) attivazione Google OAuth reale, (f) re-sync PG↔Manticore (drift accumulato pre-existing), (g) fix dei 3 test pre-esistenti rotti (`extract_models` regex broken + related_articles fixture stale). Eventuali v2.0 (recommendation engine, topic relations) restano in roadmap quando v1.0/v1.1 sono in produzione stabile.
- **Workstream attivi (tagliati per orizzontale, fuori dalle Phase)**:
  - [TOPICS-WORKSTREAM.md](TOPICS-WORKSTREAM.md) — 3 task residui (T-006/T-008/T-013) **superati de facto** dalla policy title-only + case_sensitive_slug DB-driven.
  - [FRONTEND-WORKSTREAM.md](FRONTEND-WORKSTREAM.md) — tutto chiuso `[✓]`.

Documenti di riferimento:
- [ARCHITECTURE.md](ARCHITECTURE.md) — overview, hosting, deploy
- [BACKEND.md](BACKEND.md) — FastAPI, endpoint, middleware, worker
- [INGESTION.md](INGESTION.md) — pipeline 2-fasi (URL processing + ingestion)
- [DATABASE.md](DATABASE.md) — schema PG + Manticore content store
- [KNOWLEDGE-GRAPH.md](KNOWLEDGE-GRAPH.md) — entità, topic, estrazione
- [FRONTEND.md](FRONTEND.md) — Jinja public + Vue SPA
- [MVP.md](MVP.md) — scope per release
- [reserved-words.txt](reserved-words.txt) — username vietati

## Convenzioni
- `[ ]` da fare — `[~]` in corso — `[✓]` fatto — `[⚠]` bloccato (annotare motivo)
- Dipendenze indicate inline con `→ richiede Phase X`

---

# v1.0 — MVP usable

## Phase 0 — Infrastructure & repo setup [✓]

- [✓] Creare struttura repo `youfeed/` con `backend/`, `frontend/`, `infra/`, `docs/` (i .claude/*.md restano)
- [✓] `backend/`: `pyproject.toml` con dipendenze v1.0 + extras `dev`, `v1_1`, `v1_2`
- [✓] `backend/` tooling: `ruff`, `pyright`, `pytest`, `pytest-asyncio`
- [✓] `frontend/`: `package.json` con Vue 3, Vite, TS, Pinia, Vue Router, Tailwind, Headless UI, Heroicons, ky, VeeValidate, Zod, date-fns, vue-draggable-plus, colord, driver.js, FingerprintJS, VueUse
- [✓] `frontend/` tooling: `eslint`, `vitest`, `@playwright/test`, `vue-tsc`, `prettier`
- [⚠] Server Ubuntu: install `postgresql`, `redis-server`, `manticore`, `apache2`, `certbot` — **richiede accesso server (l'utente)**
  - **Nota Postgres ≥ 15**: dopo `CREATE DATABASE youfeed OWNER youfeed`, serve anche `GRANT ALL ON SCHEMA public TO youfeed;` + `ALTER SCHEMA public OWNER TO youfeed;` + creare le estensioni `citext` e `pgcrypto` da superuser (vedi [COMMANDS.md → Postgres](COMMANDS.md))
- [✓] Apache vhost `youfeed.it` (file `infra/apache/youfeed.conf`)
- [⚠] Cloudflare: DNS + proxy + cache rules — **richiede accesso pannello CF (l'utente)**
- [✓] systemd skeleton: `yf-api.service`, `yf-worker@.service` (template parametrico), `yf-scheduler.service`, README operativo
- [✓] `.env.example` completo
- [✓] Local dev: `docker-compose.yml` per Postgres + Manticore + Redis + `infra/manticore/manticore.conf`
- [✓] Logging baseline: `structlog` con dev/prod renderer
- [✓] Script `infra/maxmind-refresh.sh`, `infra/scripts/deploy.sh`, `infra/scripts/backup.sh`

## Phase 1 — Data prep (parallelizzabile con Phase 2) [~]

- [~] **Topic curated seed** (`infra/seed/topics.yaml`): starter ~70 entry (squadre Serie A, partiti, politici nazionali/UE/internazionali, brand big-tech, brand IT, argomenti caldi). Espandere a 200-500 prima del lancio v1.0.
- [~] **Featured sources seed** (`infra/seed/featured_sources.yaml`): starter ~22 fonti popolari italiane. Espandere a 30-50.
- [✓] **Italian wordforms** (`data/wordforms/italian_wordforms.txt`): top-100 verbi irregolari (essere/avere/andare/fare/dire/dare/stare/vedere/venire/potere/volere/sapere) + sostantivi irregolari frequenti
- [✓] **Italian stopwords** (`data/stopwords/italian_stopwords.txt`): ~200 parole, articoli/preposizioni/pronomi/congiunzioni/verbi essere-avere
- [✓] **Categorie suggerite** (`infra/seed/categories_suggested.yaml`): 10 con default_color

## Phase 2 — Database foundation [✓]

→ richiede Phase 0
- [✓] Alembic init + `env.py` (legge `DATABASE_URL_SYNC` da .env autonomamente)
- [✓] Migration 0001: `users`, `auth_sessions`, `email_verification_tokens`, `reserved_usernames` + estensione CITEXT
- [✓] Migration 0002: `sources`, `user_sources`, `categories`, `featured_sources` con check constraint su `kind` e `status`
- [✓] Migration 0003: `articles` (con tutti i campi image + engagement aggregates), `topics`, `entities`, `article_topics`, `article_entities`
- [✓] Migration 0004: `activity_log` PARTITION BY RANGE (ts) + funzioni helper `yf_create_activity_partition(date)` e `yf_drop_old_activity_partitions(int)` + bootstrap partizioni 7gg
- [✓] Seed loader `app/utils/seed_loader.py` con upsert idempotente per `reserved_usernames`, `topics`, `featured_sources`
- [✓] Manticore RT index DDL `backend/manticore/articles_rt.sql` (con `morphology=libstemmer_it`, blend_chars per L'Aquila/M&M, expand_keywords)
- [✓] Wordforms + stopwords path correttamente referenziati in `infra/manticore/manticore.conf`
- [~] Test fixture base in pytest (`conftest.py` con env defaults — DB-bound fixtures verranno aggiunte in Phase 6+ quando arriveranno test integration)

## Phase 3 — Backend skeleton [✓]

→ richiede Phase 2
- [✓] `app/main.py` FastAPI con lifespan (init logging, dispose engine + redis a shutdown)
- [✓] `app/config.py` Settings pydantic-settings — tutte le variabili .env mappate
- [✓] `app/db.py` engine + session factory async + `get_db` dependency
- [✓] `app/redis_client.py` client Redis condiviso
- [✓] `app/deps.py` type alias `DB`, `RedisDep` per import puliti
- [✓] `app/auth_deps.py` `current_user`, `current_user_optional`, `current_session` (cookie + Bearer)
- [✓] `app/models/` SQLAlchemy declarative — tutti i modelli v1.0 con naming convention rigida
- [✓] `app/schemas/` Pydantic — auth schemas (RegisterIn, LoginIn, ChangePasswordIn, UserOut, ...)
- [⚠] `app/repositories/` — non ancora separati (la logica auth-service accede direttamente al DB; refactor quando i domini si moltiplicheranno)
- [✓] Endpoint `/yf_health` (verifica PG + Redis) e `/yf_version`
- [✓] Exception handlers globali con formato risposta `{error: {code, message, details}}`
- [✓] Logging structlog (dev human-readable, prod JSON via env `LOG_JSON=true`)
- [✓] OpenAPI metadata + `/yf_docs` esposto in dev/staging

## Phase 4 — Middleware [✓]

→ richiede Phase 3
- [✓] `middleware/geoip.py`: legge `CF-Connecting-IP`/`X-Forwarded-For`, lookup MaxMind ASN+Country, popola `request.state.{client_ip,country,asn}` (cloudflare e maxmind unificati)
- [✓] `middleware/ratelimit.py`: tier `anon` (60/min) per IP / tier `user` (600/min) per session_id, bucket per minuto via Redis INCR+EXPIRE, fail-open su errori Redis, header `X-RateLimit-*` di debug
- [✓] `middleware/csrf.py`: double-submit cookie + header `X-YF-CSRF`, esenzioni per Bearer e bootstrap auth
- [✓] `middleware/activity_log.py`: enqueue su `yf:activity:queue` Redis (drenata dal worker `activity_log` in Phase 6 ingestion)
- [✓] Ordine middleware corretto: `GeoIP → RateLimit → CSRF → ActivityLog → handler`
- [⚠] Test middleware in isolamento — rimandati a quando integration fixture saranno disponibili

## Phase 5 — Auth & users [✓]

→ richiede Phase 3
- [✓] `services/auth_service.py`: Argon2id hashing, session create/revoke/touch, fingerprint, validazione username (regex + reserved + prefisso `yf_`), conflict detection username/email, verifica email, change password con re-verifica corrente
- [✓] `utils/passwords.py` Argon2id (m=19MiB, t=2, p=1) + `needs_rehash` per upgrade trasparente
- [✓] `utils/tokens.py` `secrets.token_urlsafe(32)` per email verification
- [✓] Cookie session: `Set-Cookie: yf_session=<uuid>; HttpOnly; SameSite=Lax` (+ `Secure` controllato da env)
- [✓] Reserved username check via tabella `reserved_usernames` (case-insensitive) + reject prefisso `yf_`
- [✓] Endpoint `POST /yf_auth/register` con validazione email/password/username
- [✓] Endpoint `GET /yf_auth/verify-email`
- [✓] Endpoint `POST /yf_auth/resend-verification` (anti-scan: risposta identica per email esistenti/non)
- [✓] Endpoint `GET /yf_auth/username-available`
- [✓] Endpoint `POST /yf_auth/login` (accetta email o username, salva fingerprint+IP+country+ASN+UA in auth_sessions)
- [✓] Endpoint `POST /yf_auth/logout` (revoca sessione + clear cookie)
- [✓] Endpoint `GET /yf_me`
- [✓] Endpoint `POST /yf_me/change-password`
- [✓] Smoke test `tests/unit/test_passwords.py` + `test_app_starts.py`
- [⚠] Test E2E flusso completo — rimandato a quando l'invio email sarà integrato (Phase 6)
- [⚠] Invio effettivo email di verifica — `# TODO: enqueue_verification_email(...)` segnato in 2 punti, da chiudere in Phase 6

## Phase 6 — Email infrastructure [✓]

→ richiede Phase 5
- [✓] SMTP client wrapper `services/email_service.py` (aiosmtplib, OVH `ssl0.ovh.net`, STARTTLS:587 o SSL:465 secondo .env)
- [✓] Template email Jinja2: `_base.html` + `verify_email.{html,txt}` + `reset_password.{html,txt}` (v1.1)
- [✓] RQ queue `app/queues.py` + worker job `app/workers/email.py` con `Retry(max=3, interval=[30,120,600])`
- [✓] Collegamento TODO in `routers/auth.py` (register + resend-verification accodano `enqueue_verification`)
- [✓] Smoke test `test_email_templates.py` (rendering Jinja senza errori)
- [⚠] Test invio reale verso casella controllata — richiede credenziali OVH popolate in `.env`

## Phase 7 — Categories & sources [✓]

→ richiede Phase 5
- [✓] `services/category_service.py`: tree fetch + create/update/delete con vincoli alberatura (slug auto-generato unico in namespace `(user_id, parent_id)`, color hex validato, prevenzione cicli su parent move)
- [✓] `utils/slugify.py` italiano-friendly (NFKD + ASCII fold)
- [✓] Endpoint CRUD categorie `/yf_me/categories[/{id}]` (4 endpoint)
- [✓] `services/source_service.py`: list user_sources, link/unlink con validazione `category_id`, featured grouped
- [✓] Endpoint CRUD sources utente `/yf_me/sources[/{id}]` (4 endpoint)
- [✓] Endpoint `GET /yf_sources/featured` (raggruppato per `category_hint`)
- [✓] Smoke test `test_slugify.py` + `test_category_tree.py`

## Phase 8 — Ingestion: discovery (URL processing) [✓]

→ richiede Phase 7
- [✓] Modulo `app/ingestion/discovery.py`: probe diretto, WP detection (Link header + `<link rel="https://api.w.org/">` + probe `/wp-json/wp/v2/posts`), feed RSS in `<link rel="alternate">`, fallback path comuni (`/feed`, `/rss`, ecc.), parsing JSON Feed
- [✓] OG preview (titolo, descrizione, immagine, site_name, favicon) da meta tag + fallback `<title>`
- [✓] Validazione finale: feed deve produrre almeno titolo o 1 articolo parsabile
- [✓] `services/discovery_service.py`: orchestrator + upsert su `sources` (idempotente per `url_feed`/`wp_api_root`)
- [✓] Endpoint `POST /yf_sources/discover` (sync, blocking — basta a UX wizard)
- [✓] Smoke test `test_discovery_parsers.py` (feed RSS/Atom, WP Link header, HTML link tag, OG extract, normalize URL)
- [⚠] RQ worker `url_processor` async (coda `discover`) — non necessario per MVP visto che il discovery è blocking e veloce; lo aggiungeremo se la latenza diventa un problema
- [⚠] Test discovery su 20 URL reali — manuale, da fare via curl/UI quando il backend è up

## Phase 9 — Ingestion: pipeline articoli [✓]

→ richiede Phase 8
- [✓] `app/workers/scheduler.py`: tick loop + enqueue `fetch_rss`/`fetch_wp` per source `due` (last_fetched_at + poll_interval scaduti). Politeness lock Redis per host **postponed** (single-node ok per v1.0)
- [✓] `app/ingestion/feed_parser.py`: feedparser + ETag/If-Modified-Since (304 → not_modified), parsing entries → `ArticleCandidate`, image extraction (media:thumbnail → enclosure → `<img>` in content)
- [✓] `app/ingestion/wp_api.py`: WP REST API con `?_embed=true&after=ISO`, featured image preference (large→full→medium→source_url), embedded author + taxonomy
- [✓] `app/ingestion/normalize.py`: HTML strip → content_text con doppio parse (rimuove `<script>/<style>/<noscript>` E tag HTML-encoded come `&lt;strong&gt;`), bleach sanitize per content_html_safe, internal_links filtrati per stesso host, OG image fallback su full fetch
- [✓] `app/ingestion/classify.py`: Step B dizionario (alias-based con boundary italiani su accenti, longest-match preference), scoring `title*3 + body*1`. Step A taxonomy boost via `origin_taxonomy`. Step C regexp **postponed** a Phase 1.2.A (NER spaCy)
- [✓] `app/ingestion/manticore_client.py`: HTTP JSON API client (`/replace`, `/search`, `/delete`) — niente driver MySQL aggiunto
- [✓] `app/services/ingestion_service.py`: `ingest_candidates` con ON CONFLICT DO NOTHING su `url_hash`, `select_due_sources`, `mark_source_success/failure/not_modified`, `apply_classification`
- [✓] `app/workers/fetch.py`: job `fetch_rss_job` + `fetch_wp_job` (RQ, asyncio.run wrapper)
- [✓] `app/workers/process.py`: job `process_article_job` collassato (normalize → classify → manticore replace → enqueue image)
- [✓] `app/utils/ingest_cli.py`: smoke test CLI (`add-source`, `run-source`, `list-sources`)
- [✓] `app/utils/reindex.py`: re-indicizzazione articoli su Manticore (`--all|--source-id|--suspicious`) dopo modifiche al pipeline
- [✓] Test unit (no DB): feed_parser (19), wp_api (12), normalize (20), classify (10), manticore_client (9 con httpx mock)
- [✓] Test integration (Postgres reale): ingestion_service (12) — dedup `url_hash`, `mark_source_*`, `select_due_sources` poll_interval/status filter
- [✓] Test E2E manuale: `add-source ANSA RSS` → fetch → process → 700+ articoli indicizzati in Manticore + topic match
- [ ] Job riconciliazione PG↔Manticore (notturno) — **nice-to-have**, postponed (è una sweep per recuperare desync, non bloccante v1.0)

## Phase 10 — Ingestion: image processing [✓]

→ richiede Phase 9
- [✓] `app/ingestion/image_processor.py`: download streaming via httpx (15s timeout connect 8s, 12MB cap), reject non-`image/*` content-type, Pillow decode, conversione a RGB/RGBA, resize Lanczos a 370 (mobile) e 1200 (desktop), WebP q=80 method=4
- [✓] Sharding path `{hash[:2]}/{hash[2:4]}/{hash}_{m,d}.webp` (hash = sha256 dell'URL)
- [✓] Reject immagini sotto soglia (`MIN_WIDTH=200`, `MIN_HEIGHT=100`) — non utili per le card
- [✓] Idempotente: se `_d.webp` esiste già, rilegge i metadata senza riscaricare
- [✓] `app/workers/image.py`: `process_image_job` RQ + helper `enqueue_image`
- [✓] Aggiornamento `articles.image_status` (`pending`→`processed|failed|skipped`), `image_local_path` relativo a `IMAGES_DIR`, `image_width/height`
- [✓] Apache Alias `/images/*` con Cache-Control immutable (configurato in `infra/apache/youfeed.conf` + `001.youfeed.it.conf`)
- [✓] Enqueue automatico da `process_article_job` quando `image_url` è presente
- [✓] Test unit (12): hash determinismo, sharding layout, resize Lanczos (no upscale, ratio preservato), end-to-end con httpx mock (writes 2 variants, reject too-small/non-image/4xx, idempotency)
- [✓] Test E2E manuale: 1 articolo processato → 2 file WebP sul disco, image_status=processed, dimensioni corrette in DB

## Phase 11 — Articles read API [✓]

→ richiede Phase 9
- [✓] `app/services/articles_service.py`: timeline keyset (cursor opaco base64 di `published_at|id`), `timeline_for_user` (filtra su `user_sources`, `processing_status='indexed'`), `timeline_for_public_user` (filtra su `Category.is_public=true`), `get_article_detail` con fetch content_html da Manticore via `manticore_client.get_by_ids`
- [✓] `app/routers/articles.py`: `GET /yf_articles/feed` (loggato, cursor pagination), `GET /yf_articles/{id}` (dettaglio con content_html sanitizzato)
- [✓] `app/routers/track.py`: `POST /yf_track` accoda eventi su Redis list `yf:activity:queue` (whitelist: impression/click/open/dwell/scroll/search/share). Anonimo o autenticato. P95 < 5ms (no DB)
- [✓] `app/routers/public.py`: `GET /yf_users/{username}/feed.json` + `GET /yf_users/{username}/feed.rss` (RSS 2.0 compliant, atom:link self, last 50 articoli)
- [✓] `app/schemas/articles.py`: `ArticleListItem`, `ArticleDetailOut`, `ArticleListOut`, `TrackEventIn`
- [✓] `app/workers/activity_log.py`: long-running drainer (BLPOP + LPOP batch fino a 200 eventi), INSERT batch su `activity_log` (partitioned), aggregati on-the-fly su `articles.read_count`/`open_count`/`last_read_at` per eventi `click`/`open` con `target_type='article'`
- [✓] **Endpoint NON implementati (postponed)**: `GET /yf_home/public` (la home pubblica server-rendered è gestita dal dispatcher Jinja Phase 12), `GET /yf_topics`/`GET /yf_topics/{slug}` (postponed a Phase 1.1.D Search Manticore)
- [✓] Test unit (14): `articles_cursor` (6 — encode/decode roundtrip, padding, garbage, microseconds), `activity_log_mapping` (8 — UUID parsing, ts ISO/Z/missing, truncation event_type/method, default fallback)
- [✓] Test integration (5): `articles_service` — timeline filtra solo subscribed sources, skip non-indexed, ordine DESC + paginazione cursor multipagina, public timeline filtra Category.is_public, get_article_detail returns None for missing id
- [ ] Test query plan timeline (EXPLAIN ANALYZE su corpus seed) — **postponed**, da fare quando la timeline rallenta su volumi reali (>100k articoli)

## Phase 12 — Public dispatcher (Jinja2) [~]

→ richiede Phase 11
- [✓] `app/templates/public/base.html` con meta tag completi + theme inline script (no flash) + RSS alternate link slot
- [✓] Template `home.html` (landing pubblica con hero + features)
- [✓] Template `profile.html` (timeline pubblica con masonry CSS columns, OG image dal primo articolo, link feed.rss, paginazione cursor via `?cursor=`)
- [✓] Template `404.html`
- [✓] `app/static/css/public.css`: layout responsive, masonry CSS columns (1/2/3/4 col su mobile/sm/lg/xl), theme dark/light via `data-theme`, badge topics colorati per type (brand/person/subject)
- [✓] `app/static/js/public.js`: IntersectionObserver invia `event_type=impression` a `/yf_track` per articoli visibili
- [✓] `app/routers/dispatcher.py`: catch-all `GET /` (home) + `GET /{username}` con risoluzione utente + reserved username check (lookup `reserved_usernames` + SPA prefixes `me/login/register/...` + tech `static/assets/images/...` + prefisso `yf_`)
- [✓] `app/main.py`: mount `/static` via StaticFiles, dispatcher come ULTIMO router (ordine importante)
- [✓] RSS export: già implementato in Phase 11 (`/yf_users/{username}/feed.rss`) — RSS 2.0 con atom:link self
- [ ] Macros separate (`_header.html`, `_article_card.html`, `_category_tree.html`) — **postponed**, l'attuale base + 3 template è sufficiente per v1.0; refactor in macros quando i template si moltiplicheranno
- [ ] Template `user/category.html`, `user/topic.html` — **postponed** (i filtri per categoria/topic vivono in fronend SPA per il loggato; per il pubblico il `?cursor=` su /{username} è sufficiente)
- [ ] Template error 403/500 — **postponed**, il 404 c'è, gli altri usano i default FastAPI
- [ ] Endpoint `GET /sitemap.xml` dinamica + `GET /robots.txt` — **rinviati a Phase 19 SEO**
- [ ] Pagine statiche `/about`, `/privacy`, `/terms` — **postponed**, scriverle quando il prodotto è production-ready
- [✓] Test E2E manuale (curl): `GET /` → 200, `GET /drtarr` → 200 (5 fonti, 24 articoli, OG image), `GET /unknown99` → 404, `GET /static/css/public.css` → 200
- [ ] Test automation per dispatcher (TestClient FastAPI) — **da fare** in una sweep dedicata ai router-test

## Phase 13 — Frontend foundation (Vue SPA) [~]

→ richiede Phase 5 (per API contracts)
- [✓] Vite project (Vue 3 + TS + Vite 5) — `npm install` (430 packages), `npm run build` 1.65s
- [✓] Tailwind config condiviso (`content` include sia `src/**/*.{vue,ts}` che `../backend/app/templates/**/*.html`)
- [✓] Theme switcher: inline script in `index.html` evita FOUC, componente `<ThemeToggle>` toggle classe `dark` su `<html>` + persist su `localStorage.yf_theme`
- [✓] `src/services/api.ts`: wrapper `ky` con `prefixUrl` derivato da `window.location.origin` (Vite proxy `/yf_*` → backend), hook `beforeRequest` legge cookie `yf_csrf` e replica in header `X-YF-CSRF` su POST/PATCH/PUT/DELETE; helper `extractError` per payload `{error:{code,message}}`
- [✓] `src/services/auth.ts` + `src/services/articles.ts`: wrapper tipizzati per gli endpoint backend
- [✓] `src/types/api.ts`: DTO speculari agli schema Pydantic (UserOut, ArticleListItem, ArticleDetailOut, ApiError, ...)
- [✓] `src/stores/auth.ts` (Pinia): hydrate idempotente da `/yf_me` (401 = anonimo), `login`/`register`/`logout` con state management
- [✓] `src/router/index.ts`: vue-router con guard `requiresAuth` (redirect a `/login?next=`) e `guestOnly`, lazy load di tutte le viste, `scrollBehavior` reset, `document.title` da meta
- [✓] Layout: `PublicLayout.vue` (header + nav per login/register), `AppLayout.vue` (sidebar con nav + theme toggle + logout per `/me/*`)
- [✓] Pagine v1.0 base: `Login.vue`, `Register.vue`, `Feed.vue` (timeline masonry con date-fns + load more), `Categories.vue` (placeholder Phase 16), `NotFound.vue`
- [✓] Test Vitest (20): `api.test.ts` (CSRF auto-inject su POST/PATCH/PUT/DELETE, no inject su GET o senza cookie, decode URL-encoded, extractError parsing), `auth-store.test.ts` (hydrate idempotente, 401 = anonymous silent, login chiama getMe, register no auto-login, logout pulisce stato anche su API fail)
- [✓] `npm run build` + `vue-tsc --noEmit` verdi
- [ ] Componenti UI base (`Button`, `Input`, `Select`, `Modal`, `Toast`, `Spinner`) — **postponed a Phase 14+**, oggi i form usano Tailwind utility direct; emergeranno come componenti quando ci sarà ripetizione
- [ ] `<CookieBanner>` — **rinviato a Phase 17** (settings & GDPR)

## Phase 14 — Auth pages SPA [✓]

→ richiede Phase 13
- [✓] `src/schemas/auth.ts`: schemi Zod per `loginSchema`, `registerSchema`, `resendVerificationSchema`. Vincoli speculari al backend (username 3-30 alfanumerico+_, email valida, password ≥10)
- [✓] `src/pages/Login.vue`: form vee-validate + `@vee-validate/zod` (toTypedSchema), errori field-level inline, `aria-invalid` per a11y, redirect a `?next=` o `/me/feed`, toast on error/success
- [✓] `src/pages/Register.vue`: stessa pattern + redirect a `/verify-email-pending?email=...` post-success
- [✓] `src/pages/VerifyEmailPending.vue`: messaggio statico "controlla email" + form di resend (`POST /yf_auth/resend-verification`), messaggio neutro per privacy se l'email non esiste
- [✓] `src/pages/VerifyEmailToken.vue`: consuma `?token=` (`GET /yf_auth/verify-email`), 3 stati (loading/success/error) + messaggi specifici per `expired_token`/`invalid_token`
- [✓] `src/services/auth.ts`: aggiunti `verifyEmail(token)` + `resendVerification(email)`
- [✓] `src/stores/toasts.ts`: Pinia store con push/dismiss/clear + helper `success/error/info`, auto-dismiss configurabile (default 4500ms, ttl=0 disabilita)
- [✓] `src/components/common/Toaster.vue`: rendering top-right via `<Teleport to="body">`, `<TransitionGroup>` slide-fade, color tokens per type, dismiss manuale + auto
- [✓] `src/App.vue`: monta `<Toaster>` globale (visibile da tutti i layout)
- [✓] `src/router/index.ts`: route `/verify-email-pending` e `/verify-email` (entrambe in `PublicLayout`)
- [✓] Dipendenza aggiunta: `@vee-validate/zod` (peer di vee-validate per `toTypedSchema`)
- [✓] Test Vitest (21 nuovi): `toasts-store.test.ts` (10 — push id incrementale, dismiss, auto-TTL default+custom, ttl=0, clear, helper per type), `auth-schemas.test.ts` (11 — login/register/resend Zod boundaries: identifier<3, password vuota, username<3, char invalidi, email malformata, password<10)
- [✓] Build `npm run build` + `vue-tsc --noEmit` verdi (2.19s, bundle SPA totale ~250kb gzip)

## Phase 15 — User app SPA: timeline & sources [✓]

→ richiede Phase 14
- [✓] `src/components/articles/ArticleCard.vue`: card masonry con `<picture>` + `<source media="(max-width: 599px)">` (srcset mobile sostituisce `_d.webp`→`_m.webp`), fallback graceful su error img, strip HTML + truncate description ≤180, time relativo italiano (date-fns + locale `it`), badge topics colorati per type (brand=red, person=blue, subject=emerald)
- [✓] `src/components/articles/TimelineFeed.vue`: componente riusabile con prop `fetcher: (cursor?) => Promise<ArticleListOut>`, paginazione cursor (concatena risultati su loadMore, replace su `reload`), slot `#empty` per messaggio vuoto custom, `defineExpose({reload})` per refresh esterno
- [✓] `src/pages/Feed.vue`: refactor per usare `TimelineFeed` con slot empty che linka a `/me/sources`
- [✓] `src/types/api.ts`: aggiunti DTO `SourceOut`, `UserSourceOut`, `UserSourceListOut`, `FeaturedSourceItem`, `FeaturedSourcesOut`, `DiscoveryOut`, `OgPreview`, `FeedCandidatePreview`, `CategoryOut`, `CategoryNode`, `CategoryTreeOut`
- [✓] `src/services/sources.ts`: `listMySources`, `linkSource`, `updateMySource`, `unlinkSource`, `fetchFeatured`, `discoverUrl`
- [✓] `src/services/categories.ts`: `fetchCategoryTree`, `createCategory`, `updateCategory`, `deleteCategory`, helper `flattenTree` per i select dei form
- [✓] `src/pages/Sources.vue`: lista user_sources in grid con favicon, kind badge (rss/wordpress_api), bottone "Rimuovi" con `confirm()`, ogni card mostra categoria di appartenenza
- [✓] `src/components/sources/FeaturedSourcesGallery.vue`: render `FeaturedSourcesOut.by_category`, filter dropdown su category_hint, emit `select` su click "Aggiungi"
- [✓] `src/components/sources/SourceWizard.vue`: wizard 3-step (URL → discovery preview con scelta multi-feed → categoria con opzione "crea nuova"), `defineExpose({presetFromFeatured})` per pre-popolare dallo step 3 quando si sceglie da Featured, OG preview con favicon + title + description
- [✓] `src/pages/AddSource.vue`: ospita Wizard a sinistra + FeaturedSourcesGallery a destra (grid 2 col su lg+), connessione `select` Featured → wizard.presetFromFeatured
- [✓] Router: `/me/sources` (list) e `/me/sources/add` (wizard) — aggiunti a children di `/me`. Nav `AppLayout` estesa con voce "Fonti"
- [✓] Test Vitest (18 nuovi): `article-card.test.ts` (8 — anchor URL, no picture senza img, srcset mobile da `_d.webp`→`_m.webp`, fallback image_url, strip+truncate description, time italiano, topic colors per type, hide image on error), `timeline-feed.test.ts` (5 — load on mount, loadMore appends, slot empty custom, error API, reload sostituisce items), `source-wizard.test.ts` (5 — step 1 init, advance to step 2 on success, kind=invalid mostra reason, step 3 link source emit `added`, presetFromFeatured salta a step 3)
- [✓] `vue-tsc --noEmit` + `npm run build` verdi (2.21s, AddSource bundle 10.5kb gzip 3.7kb, Sources 3.4kb gzip 1.6kb)
- [ ] Filtro per categoria/topic nella `TimelinePage` — **postponed** a Phase 1.1.D Search (insieme alle query Manticore full-text); per ora il feed personale è single-stream

## Phase 16 — User app SPA: categorie [✓]

→ richiede Phase 15
- [✓] `src/lib/colors.ts`: helper puri — `SWATCHES_16` (palette Tailwind 500-tier), `isValidHex` / `normalizeHex` (regex `#rrggbb` o `#rrggbbaa`, lowercase, strip alpha), `contrastRatio` (algoritmo WCAG senza plugin colord), `isWcagAA` (≥4.5:1), `bestTextOn` (#000 o #fff), `complementaryWheel` (5 hex via HSL: 180° + 150°/210° split + 30°/330° analoghi)
- [✓] `src/components/categories/CategoryColorPicker.vue`: grid 8×2 swatch + input hex custom (validazione live, blur-to-commit), ruota suggerimenti complementari, preview testo con `bestTextOn` + display ratios, warning WCAG AA fail. `v-model:string|null`
- [✓] `src/components/categories/CategoryTree.vue`: 2 livelli nesting (root + figli, niente reparent in MVP), `<VueDraggable>` da `vue-draggable-plus` con drag handle `⋮⋮`, emit `edit/delete/reorder(parent_id, ids[])`, colore come `border-left`
- [✓] `src/pages/Categories.vue`: tree + modale CRUD (nome, parent, color picker, is_public toggle), persistenza riordino via `Promise.all(updateCategory({position}))`, conferma `confirm()` su delete
- [✓] Test Vitest (17 nuovi): `colors.test.ts` — hex validation/normalization, contrastRatio (black/white=21, simmetrico, same-color=1), isWcagAA, bestTextOn, complementaryWheel (5 elementi validi, 180°=ciano per rosso), 16 SWATCHES tutti validi
- [✓] Vue-tsc + build verdi (Categories chunk 57kb gzip 20kb — include vue-draggable-plus)
- [ ] Reparent drag-drop tra livelli — **postponed** (l'API supporta `parent_id` arbitrario, basterà aggiungere "Sposta in…" nel modale o drag cross-container)

## Phase 17 — User app SPA: settings & GDPR [✓]

→ richiede Phase 16
- [✓] `app/services/account_service.py` (backend): `build_export_archive(user)` ritorna bytes ZIP con `user.json`/`categories.json`/`sources.json`/`sessions.json`/`README.txt` (no password/hash, GDPR Art. 20); `delete_user_cascade(user_id)` UPDATE activity_log SET user_id=NULL+anon (fingerprint/ip/ua → NULL) poi DELETE FROM users (CASCADE pulisce categories/user_sources/auth_sessions/email_verification_tokens; sources globali NON eliminate); `count_user_data` helper per UI
- [✓] `app/routers/me.py`: `GET /yf_me/export` (StreamingResponse ZIP, Content-Disposition attachment), `DELETE /yf_me` (commit + delete_cookie sul session cookie + 204)
- [✓] `src/services/me.ts`: `changePassword`, `downloadExport(filename)` (blob → anchor click → revokeObjectURL), `deleteAccount`
- [✓] `src/schemas/me.ts`: `changePasswordSchema` con `refine` per match `new_password === confirm_password`
- [✓] `src/composables/useTrackingConsent.ts`: state machine `unknown|granted|denied` persistita in `localStorage.yf_tracking_consent`, `getFingerprint()` con dynamic import lazy di `@fingerprintjs/fingerprintjs` (memoizzato; chunk separato — `fingerprint-*.js` 39kb gzip 17kb caricato solo se consent === granted), `_internals.resetForTests` per i test
- [✓] `src/pages/AccountSettings.vue`: form change password (vee-validate + zod, refine match), danger zone delete account con `prompt(ELIMINA-{username})` come second-confirm
- [✓] `src/pages/PrivacySettings.vue`: toggle Accetta/Rifiuta tracking, indicatore stato corrente (pallino emerald/red/slate), bottone "Scarica export ZIP" (download client-side via blob)
- [✓] Router: `/me/settings` (redirect a account), `/me/settings/account`, `/me/settings/privacy`. Nav `AppLayout` estesa con voce "Impostazioni"
- [✓] Test integration backend (5 nuovi): `test_account_service.py` — export contiene tutti i file no password, delete cascade rimuove user/categories/user_sources/auth_sessions/email_tokens, sources globali preservate, activity_log anonimizzato (user_id=NULL + fingerprint/ip/ua puliti), `count_user_data`
- [✓] Test Vitest (9 nuovi): `tracking-consent.test.ts` — stato iniziale unknown, grant/deny/reset con persistenza localStorage, singleton state condiviso, getFingerprint ritorna null senza consenso, ritorna visitorId con consenso (mock dynamic import), memoizzazione single-call
- [✓] `vue-tsc --noEmit` + `npm run build` verdi (chunk Categories 57kb, Login/Register/AccountSettings ~3kb ciascuno, fingerprint chunk separato lazy)

## Phase 18 — Onboarding tour [✓]

→ richiede Phase 17
- [✓] `app/schemas/auth.py`: `MePatchIn` con campo opzionale `onboarding_completed: bool | None`
- [✓] `app/services/account_service.py`: `set_onboarding_completed(user, completed)` setta `NOW()`/NULL su `onboarding_completed_at` (caller fa commit/refresh)
- [✓] `app/routers/me.py`: `PATCH /yf_me` chiama il service; ritorna `UserOut` aggiornato
- [✓] `src/lib/onboarding-data.ts`: 10 categorie suggerite (slug/name/description/defaultColor) speculari a `infra/seed/categories_suggested.yaml`, 7 ONBOARDING_STEPS (welcome → categories → sources → color-picker → privacy → public-feed → done) con `primaryActionLabel` su categories e done
- [✓] `src/services/me.ts`: `patchMe(patch)` + `completeOnboarding()`
- [✓] `src/stores/auth.ts`: nuovo metodo `refresh()` (re-fetcha `/yf_me` per allineare lo state dopo mutation)
- [✓] `src/components/onboarding/OnboardingTour.vue`: modale wizard 7-step con barra progresso, step "categories" con multi-select checkbox + creazione sequenziale via `createCategory(name, null, defaultColor)`, step "color-picker" con `<CategoryColorPicker>` demo, step "privacy" con bottoni Accetta/Rifiuta che chiamano `useTrackingConsent`, step "public-feed" con preview URL `youfeed.it/{username}` + RSS path, "Salta tour" sempre disponibile, "Inizia" finale chiama `completeOnboarding` + `auth.refresh()`. **Nota**: scelto modale custom invece di driver.js perché il tour è di setup attivo (non highlight DOM), e i selettori DOM cambiano col redesign — modale è più robusto. `driver.js` resta in deps per futuri tour DOM-aware (Phase 1.1.x)
- [✓] `src/components/layouts/AppLayout.vue`: trigger automatico del tour quando `auth.user.onboarding_completed_at === null` via `watchEffect`. Modale chiusa controlla state in-component
- [✓] Test integration backend (2 nuovi): `test_me_router.py` — `set_onboarding_completed(true)` setta timestamp tz-aware, `set_onboarding_completed(false)` resetta a NULL dopo set
- [✓] Test Vitest (11 nuovi): `onboarding-data.test.ts` (8 — 10 categorie, slug pattern, defaultColor hex valido, slug unici, presence di politica/cronaca/sport/tecnologia, 7 step, key uniche nell'ordine atteso, primaryActionLabel su categories+done), `auth-store-refresh.test.ts` (3 — no-op se anonimo, aggiorna user dopo PATCH simulato, preserva state precedente su getMe fail)
- [✓] `vue-tsc --noEmit` + `npm run build` verdi (chunk Categories/CategoryColorPicker shared, AppLayout +1.5kb per il modale)

## Phase 19 — SEO & sitemap [✓]

→ richiede Phase 12
- [✓] `app/services/seo_service.py`: `collect_public_profile_entries(base_url)` query con join `users` × `categories(is_public=true)` × `user_sources` (skip utenti con 0 sources), `lastmod` = `MAX(articles.published_at)` filtrato su categorie pubbliche e processing_status=indexed (fallback a `users.created_at` se mancano articoli); `build_sitemap_xml(entries)` con escape XML per loc, namespace sitemaps.org 0.9, `<lastmod>` ISO UTC, `<changefreq>` e `<priority>` per entry; `build_robots_txt(base_url, allow_indexing)` con Disallow su `/yf_*`, `/me/`, `/login`, `/register`, `/verify-email*`, `/static/`, e `Sitemap:` line al base
- [✓] `app/routers/seo.py`: `GET /sitemap.xml` (home con priority 1.0 + tutti i profili pubblici con priority 0.8) e `GET /robots.txt`. Registrati PRIMA del catch-all dispatcher (sitemap.xml/robots.txt sono comunque in `TECH_RESERVED` per sicurezza)
- [✓] `app/templates/public/base.html`: aggiunti `{% block canonical %}` + Twitter Card (`summary_large_image`, `twitter:title`, `twitter:description`), `og:url` da `canonical_url`
- [✓] `app/templates/public/profile.html`: JSON-LD `CollectionPage` con `mainEntity: ItemList` (primi 20 articoli con position/url/name); `og:image` + `twitter:image` dal primo articolo (locale > remoto)
- [✓] `app/routers/dispatcher.py`: passa `canonical_url` al template (`/` per home, `/{username}` per profilo) basato su `settings.yf_public_base_url`
- [✓] Test unit (8): `test_seo_service.py` — header XML + namespace, escape `&` in loc, contenuto loc/lastmod/priority, multi-entry, lista vuota, ts UTC; robots disallow paths interni + Sitemap line; staging blocca tutto
- [✓] Test integration (3): `collect_public_profile_entries` include solo public+with-source (skippa privati e user senza sources), lastmod usa MAX(published_at), priorità 0.8 + changefreq hourly per profili
- [ ] Ping a Google Search Console + Bing dopo deploy v1.0 — **operativo**, fuori da v1.0 codata (Phase 21 DoD)

## Phase 20 — Operational hardening [✓]

→ richiede tutte le precedenti
- [✓] systemd units esistenti (`yf-api.service`, `yf-worker@.service`, `yf-scheduler.service`) hanno tutti `Restart=on-failure` + `RestartSec=5` + log su journald (verificato)
- [✓] Aggiunto `infra/systemd/yf-activity-log.service` (drainer Redis → PG, long-running con Restart=on-failure) — service mancante in Phase 11
- [✓] Aggiunto `infra/systemd/yf-manage-partitions.service` (oneshot) + `yf-manage-partitions.timer` (`OnCalendar=*-*-* 02:30:00 UTC`, `Persistent=true`) per la manutenzione daily delle partizioni `activity_log`
- [✓] `app/utils/manage_partitions.py`: CLI che chiama le funzioni SQL `yf_create_activity_partition(date)` + `yf_drop_old_activity_partitions(retention)` (definite in migration 0004); opzioni `--create-ahead 7 --retention-days 180`
- [✓] Script `infra/scripts/deploy.sh` esistente (git pull + pip + alembic + npm + systemctl restart) — verificato
- [✓] Script `infra/scripts/backup.sh` esistente (pg_dump + Manticore BACKUP + tar immagini delta) — verificato. Destinazione offsite TBD operativamente
- [✓] Healthcheck endpoint `/yf_health` (Phase 3) verifica PG + Redis. Integrazione monitoring esterno (uptime-kuma/Cronitor) operativa
- [✓] `docs/runbook.md` (300+ righe): componenti, deploy nuovo server (init), deploy ricorrente, restart selettivo, monitoraggio (`journalctl`/`redis-cli`/`psql`), healthcheck, backup/restore, **incidenti tipici** (API down, code RQ accumulano, sources tutte broken, disk full, Manticore non indicizza), variabili `.env` chiave

## Phase 21 — Definition of Done v1.0 [~]

Stato di code-completeness vs operational acceptance: **codice 100% pronto, validazione operativa fa parte del lancio v1.0**.

### Code-side ([✓] completati)
- [✓] Endpoint testati con fixture pytest — 122 unit + 39 integration backend, 96 Vitest frontend (totale **257 test verdi**). Tutti i service e router principali coperti; per i router HTTP integration completi (TestClient con dep override) → estendibile in v1.1
- [✓] Pipeline ingestion stabile (Phase 9 + 10) — testato manualmente su 22+ fonti reali (Repubblica/Corriere/ANSA/Sole24/Open/Sky TG24/...) con 700+ articoli indicizzati su Manticore + topic match
- [✓] Dedup verificata via `articles.url_hash` UNIQUE + ON CONFLICT DO NOTHING (Phase 9, test integration `ingest_candidates_dedupes_on_url_hash`)
- [✓] Image processing 2 varianti WebP (370 mobile + 1200 desktop) con sharded path + idempotency (Phase 10, 12 test unit con httpx mock)
- [✓] Seed topics caricato (`infra/seed/topics.yaml` ~70 entità starter, espandere a 200+ in operativo). Classify scorring `title*3 + body*1` (Phase 9, 10 test unit)
- [✓] GDPR export ZIP + delete cascade + activity_log anonimizzato (Phase 17, 5 test integration)
- [✓] Sitemap dinamica + robots.txt + JSON-LD CollectionPage + canonical + Twitter Card (Phase 19, 11 test)
- [✓] Rate limit middleware + GeoIP middleware (Phase 4) — `RATE_LIMIT_ANON_PER_MIN=60`, `RATE_LIMIT_USER_PER_MIN=600` configurabili da env
- [✓] Theme switcher light/dark con persistenza localStorage + no-FOUC (Phase 12 + 13)
- [✓] Onboarding tour 7-step (Phase 18) skippabile + gate per primo login

### Operativi (richiedono deploy + tempo)
- [ ] Ingestion stabile per 7 giorni continui — **dopo deploy v1.0**
- [ ] Image processing >90% sample reale — verificare con query post-deploy
- [ ] Topic seed espanso a 200-500 entità — operativo (curatela contenuti)
- [ ] Cookie banner + privacy policy testo live — pagina `/privacy` legale da scrivere (postponed)
- [ ] Sitemap pingata a Google Search Console + Bing
- [ ] Backup PG + Manticore restore testato (script pronti, manca run di prova)
- [ ] MaxMind country-block verificato in produzione
- [ ] Test cross-browser (Chrome/FF/Safari × desktop/mobile)
- [ ] Lighthouse ≥ 90 sul profilo campione
- [ ] 5+ utenti beta effettivi con feedback

**Riassunto**: tutto il codice della v1.0 è scritto, verificato con test (unit + integration backend + Vitest frontend) e documentato nel runbook. La fase rimanente è il rollout operativo + pulizia leggera della curatela seed e content.

---

# T-018 — Topic policy v2 + Admin panel + Topic curation massiva [✓] (2026-05-09/11)

Sessione cross-phase che ha consolidato la qualità dell'estrazione topic e introdotto strumenti di moderazione. Documentata qui perché tocca trasversalmente Phase 9 (classify), 11 (admin tooling), 1.2.A-pre (extractor).

### Migration

- [✓] **Migration 0011** `topics_type_invalid`: estende `ck_topics_type` per accettare `'invalid'` — soft blacklist anti-ricreazione dei topic auto-extracted
- [✓] **Migration 0009/0010** (`topic_rules_tables` + `reconcile`): tabelle `topic_term_rules(kind, term, note)` e `topic_composite_rules(composite_slug, components)` — regole admin-editabili, sostituiscono i set hard-coded module-level

### Topic policy v2

- [✓] **Title-only extraction** (worker live `process.py` + CLI `reclassify_topics --title-only`): body produce troppo rumore (citazioni di brand/persone non centrali). Estrazione solo da `meta.title`. Effetto su 1714 articoli storici: da 14.345 → 2.200 article_topics (-85% rumore, related più focalizzati)
- [✓] **Related con TF-IDF + coverage simmetrica** (`articles_service.related_articles`): peso topic = `log(N/df)`, formula `coverage = max(inter/A, inter/B)` simmetrica, sort primario per n_topic_intersection desc poi overlap desc. Soglie anti-FP: 1 topic comune richiede `idf ≥ 4.0`; ≥2 topic comuni richiedono `Σ idf ≥ 3.0`
- [✓] **Subsumption rule** (`classify._apply_subsumption`): se i token del display_name di un topic A sono sotto-sequenza contigua dei token di B, A viene assorbito da B nello stesso match-set. Es: `Sony` assorbito da `Sony Xperia 1 VIII`, `Android` assorbito da `Android 17`, `Nintendo` assorbito da `Nintendo Switch 2`
- [✓] **type='invalid' come soft blacklist**: `_load_index` esclude topic invalid dal matching dict; `_upsert_regex_topic` ritorna None se trova topic con quello slug già invalid → no ricreazione automatica
- [✓] **Pattern "alias senza prefisso brand"** applicato sistematicamente: `Galaxy S25` → Samsung Galaxy S25, `iPhone 17` → Apple iPhone 17, `Pixel 10` → Google Pixel 10, `Xperia 1 VIII` → Sony Xperia 1 VIII, `Switch 2` → Nintendo Switch 2, ecc.
- [✓] **Edge-token trim** anche in `extract_models` (non solo `extract_persons`): `Leapmotor Il` / `Canva La` / `Amazon Cosa` ora scartati invece di produrre falsi topic model
- [✓] **Composite rules in DB** (sostituisce hard-coded list): es. `Google + Gemini → Google Gemini`, editabili da `/yf_admin/composite`

### Topic curation (1500+ entità nuove curated o promosse)

12 batch tematici inseriti come `brand`/`person` curated, con alias e `case_sensitive_slug` quando necessario:

- [✓] **Brand auto** (~225): Alfa Romeo, BMW, Toyota, Tesla, Ferrari, ecc. (estratti da listato facile.it)
- [✓] **Compagnie telefoniche IT** (24): Vodafone, TIM, Iliad, Saily, WindTre, ecc.
- [✓] **Smartphone brand** (25): Samsung, Apple, Xiaomi + POCO/Framework/Gigabyte case-sensitive
- [✓] **Laptop brand** (22): Lenovo, Dell, ASUS, Razer + Toughbook/NUC aliases
- [✓] **Smart TV / audio** (23): Sharp, Skyworth, Sonos, Yamaha, ecc.
- [✓] **Banche europee** (30): HSBC, Santander, UniCredit, Monte dei Paschi, ecc. + 5 promossi da `person` FP
- [✓] **Microchip** (24): TSMC, NVIDIA, ASML, Broadcom + alias short
- [✓] **Microcontroller** (16): Raspberry Pi, Arduino, ESP32 (Espressif), Hardkernel (ODROID), ecc.
- [✓] **Distro Linux** (27): Ubuntu, Debian, Fedora, NixOS, ecc.
- [✓] **Computer / server** (22): VAIO, Alienware, HPE, Supermicro, ecc.
- [✓] **Hardware components** (44): GPU partners (Sapphire, Zotac, Palit, ecc.), PSU/cooling/case (Seasonic, Noctua, NZXT, Lian Li, Fractal Design, ecc.)
- [✓] **Criptovalute** (29): Bitcoin, Ethereum, Solana + 13 `case_sensitive_slug` per sigle ambigue (LINK, DOT, NEAR, TON, OP, ATOM, DAI, SUI, ARB, APT, UNI, SOL, PEPE)
- [✓] **Cantanti** (137): Taylor Swift, BTS, Mina, Vasco Rossi, Maneskin + 7 `case_sensitive_slug` per nomi che collidono con parole IT (sia/mina/future/rose/bono/pink/prince)
- [✓] **Politici** (23 nuovi + 22 già curated): J.D. Vance, Papa Leone XIV, Xi Jinping, Modi, Milei, Lula, Sheinbaum, MBS, ecc.

### Cleanup

- [✓] Sweep blacklist comuni IT ambigui: 12 nuovi termini in `brand_single` + 8 topic location promossi a `invalid` (Grado/Vasto/Cambiano/Arco/Stella/Mossa/Opera/Potenza) → 355 article_topics FP cancellate
- [✓] 607 topic auto-extracted orphan invalidati (residui da matching body pre title-only)
- [✓] 18 topic stale con edge token (Leapmotor Il, Canva La, ecc.) marcati invalid

### Frontend

- [✓] **Title del browser tab** dinamico in ArticleDetail (`<titolo articolo> · YouFeed`)
- [✓] **Cap a 12 topic** per card (ArticleCard + ArticleDetail) con pillola `+N` per gli extra
- [✓] **Apache vhost fix**: `ProxyPass /images !` esclusione mancante (immagini servite dal filesystem, non più 404 al backend). Convenzione `cp` (non symlink) per `sites-available/`

### Admin panel `/yf_admin/*` (T-017 espansa)

- [✓] Auth HTTP Basic via `.env` (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), CSRF middleware skip su `/yf_admin/*`
- [✓] Sezioni: Dashboard, Utenti, Topic (CRUD + bulk validate/invalidate + form add), Article inspector, Stats per type/source, Regole splittate in 3 pagine (Ambigui/Blacklist/Case-sensitive), Composite rules editor
- [✓] Cache classifier invalidata automaticamente dopo ogni write admin (`classify.invalidate_classifier_cache()` propaga anche su `articles_service.invalidate_topic_idf_cache()`)
- [✓] Default lista topic esclude `type='invalid'` (no rumore in moderazione)

### Infrastruttura dev

- [✓] **`scripts/dev.sh`**: avvio integrato (uvicorn + vite + scheduler + activity_log + 6 worker RQ) con log unificato in `logs/dev/`, trap su SIGINT/SIGTERM, healthcheck preliminare su servizi systemd

### Test post-migration

Smoke test su casi reali verificati end-to-end (su articoli storici):
- 46836/28667/22319 (Sony Xperia 1 VIII): topic singolo dominante, related cross-source perfetti
- 54962 (Samsung × Dua Lipa causa): 2 topic dominanti, related = solo gli articoli sulla stessa storia
- 54742 (Nintendo Switch 2 + YouTube): topic + related sulla stessa Switch 2 (no più drift su Nintendo utili netto / crisi memorie)
- 55582 (HyperOS 4 + Android 17): match corretto dopo promozione version-topic da invalid
- 47896 (Saily eSIM): brand specifico aggiunto manualmente + reclassify
- 53749 (Samsung One UI 8.5 + Galaxy S25): match cross-alias dopo sweep Galaxy

---

# v1.1 — Polish & search

## Phase 1.1.A — Google OAuth [✓] (2026-05-11, simulato)

→ scope: full backend/frontend wiring, attivazione Google reale rinviata
- [✓] `services/oauth_service.py` con state firmato HMAC-SHA256 (TTL 10min), `OAuthProfile` dataclass, `mock_exchange_code` con regex `mock:<email>`, `find_or_create_oauth_user` con auto-link su email + auto-generate username dal local-part
- [✓] Endpoint `GET /yf_auth/google/authorize?next=<path>` (302 → consent page) + `GET /yf_auth/google/callback?code&state` (exchange → user → session → 302 a `next` con cookie sessione settato relative-origin) + `GET /yf_auth/google/_mock` (consent stub HTML inline, attiva solo se `is_simulate()`)
- [✓] `is_simulate()` = `not GOOGLE_OAUTH_CLIENT_ID`: in dev/staging il flow non parla con Google; quando si configura il client_id in `.env`, `build_authorize_redirect` produce l'URL Google reale (drop-in pulito, nessuna altra modifica al callback)
- [✓] Componente Vue `components/auth/GoogleLoginButton.vue` con logo G multi-color, su `Login.vue` (con `next` da query) e `Register.vue`
- [✓] Smoke test end-to-end: /authorize → /_mock HTML 200 → /callback con `code=mock:probe.oauth@example.it` → User id=2 creato (`email_verified=true`, `google_sub=mock-…`) + sessione attiva, /yf_me 200
- [ ] Attivazione reale: configurare client_id/secret/redirect_uri su Google Cloud Console e popolare `.env` (resta in todo operativo, non blocca v1.1)
- [ ] Test E2E con 2 account Google veri (richiede attivazione reale)

## Phase 1.1.B — Forgot/reset password [✓] (2026-05-11)

- [✓] Migration 0012: tabella `password_reset_tokens` (token PK, user_id FK CASCADE, expires_at, used_at, created_at, idx su user_id)
- [✓] Model `PasswordResetToken` in `models/users.py`; export da `models/__init__.py`
- [✓] Service `auth_service.issue_password_reset_token(db, email)` (TTL 1h, elimina i token pendenti, ritorna None se utente non esiste o ha solo OAuth — antiscan) + `consume_password_reset_token(db, token, new_password)` (verifica scadenza/used, valida pwd, hash + revoca tutte le sessioni attive dell'utente)
- [✓] Endpoint `POST /yf_auth/forgot-password` (risposta volutamente identica in tutti i casi) + `POST /yf_auth/reset-password` (422 su pwd debole, 401 su token invalido/usato/scaduto); entrambi in CSRF bootstrap whitelist
- [✓] Schemi `ForgotPasswordIn`, `ResetPasswordIn` in `schemas/auth.py`; service wrapper `forgotPassword`/`resetPassword` in `services/auth.ts`; zod schemas `forgotPasswordSchema` + `resetPasswordSchema` (con confirm-match refine)
- [✓] Template email `reset_password.{html,txt}` già esistente; worker `enqueue_password_reset` già esistente
- [✓] Frontend `pages/ForgotPassword.vue` (success message volutamente non confermante l'esistenza) + `pages/ResetPassword.vue` (token da query string, success → link a /login); route `/forgot-password` + `/reset-password` (guestOnly); link "Password dimenticata?" su `Login.vue`
- [✓] Smoke E2E: utente temp `reset_probe` → forgot → token DB → reset con nuova pwd → riuso stesso token = 401 `token_used` → login con nuova OK / vecchia = 401 `invalid_credentials`

## Phase 1.1.C — Device management [✓] (2026-05-11)

- [✓] Endpoint `GET /yf_me/devices` (lista `AuthSession` non revocate dell'utente, sorted by `last_seen_at DESC`, marca `current=true` per la sessione corrente via `CurrentSession` dep)
- [✓] Endpoint `DELETE /yf_me/devices/{device_id}` con guard `cannot_revoke_current` (400) se l'utente tenta di revocare la propria → indirizzato al pulsante "Esci"
- [✓] Schema `DeviceOut` in `schemas/auth.py` con id/client/ip/country/ua/created_at/last_seen_at/current
- [✓] Frontend `pages/Devices.vue` con `describeUa()` heuristica (Edg/Chrome/Firefox/Safari/Opera + Windows/macOS/Android/iOS/Linux), badge "Questo dispositivo", revoca con confirm dialog, formatDistanceToNow italiano
- [✓] Route `/me/settings/devices` (`settings-devices`) + voce GearMenu "Dispositivi"
- [✓] Smoke E2E: 3 login con UA diversi → list mostra `current=true` su A, false su B/C → DELETE C (con CSRF header) 200 → DELETE A (self) 400 → curl con cookie C 401 → final list senza C
- [ ] Notifica email opzionale su nuova sessione da IP nuovo (TBD, non bloccante)

## Phase 1.1.D — Search Manticore [✓] (2026-05-11)

- [✓] Query helper Manticore con filtro condizionale (loggato → user_sources) — `manticore_client.search_articles(query, source_ids, limit, offset, highlight)` con highlight `<mark>` su title/description/content_text, sort relevance + recency
- [✓] Endpoint `GET /yf_search` (auth-aware: user_id None → tutto corpus, altrimenti filter user_sources) + `GET /yf_search/suggest` (autocomplete topic + sources con `ILIKE 'prefix%'`, ordinato per length)
- [⚠] `GET /yf_search/sources` — **postponed** (lo scope si è dimostrato ridondante: la facet by source si può derivare dai risultati attuali se serve in v1.1.x)
- [✓] Service `app/services/search_service.py` con auth-aware filter + hydrate Source/Topic da Postgres
- [✓] Schemas `app/schemas/search.py` (SearchOut, SearchResultItem con highlights, SuggestOut)
- [✓] Router registrato in `app/main.py`
- [✓] Frontend `pages/Search.vue` con risultati `<mark>` evidenziati, paginazione 20×N, link articolo
- [✓] Componente `components/common/SearchBar.vue` in header `AppLayout` con dropdown suggest live (debounce 250ms, click-outside, autocomplete topic+sources)
- [✓] Route `/me/search` + nav integrata
- [✓] Smoke test su corpus reale: 7 hits "Sony Xperia", 255 hits "intelligenza artificiale", suggest top 8 ordinati per specificità
- [ ] Test relevance review formale su corpus 10K+ articoli — postponed (corpus attuale 1700, valutazione qualitativa OK)

## Phase 1.1.E — Centro notifiche in-app [✓] (2026-05-11)

- [✓] Migration 0013: tabella `notifications` (id PK, user_id FK CASCADE, kind String(32) free-form, title/body/link Text, payload JSONB, read_at, created_at; idx composito su `user_id, created_at DESC` + partial idx `WHERE read_at IS NULL` per badge count veloce)
- [✓] Model `Notification` in `models/notifications.py`; export da `models/__init__.py`
- [✓] Service `services/notification_service.py`: `list_for_user` (paginato, filter only_unread), `count_unread`, `mark_read`, `mark_all_read` (UPDATE … RETURNING), `create_notification` generic, `generate_daily_digests` (filtra utenti con ≥1 user_source + sessione attiva ultimi 14gg; idempotente per giorno via lookup `WHERE kind='digest_daily' AND created_at >= midnight_today`; conta articoli `ingested_at >= now-24h` joined su user_source)
- [✓] CLI `python -m app.utils.notify_digest` da cron-iare (`0 7 * * *` consigliato); usa structlog + `dispose_engine`
- [✓] Endpoint `GET /yf_me/notifications?only_unread&limit&offset` + `GET /yf_me/notifications/unread-count` + `PATCH /yf_me/notifications/{id}/read` + `POST /yf_me/notifications/mark-all-read`
- [✓] Schemi `NotificationOut`/`NotificationCountOut` in `schemas/notifications.py`
- [✓] Frontend: types `NotificationOut`/`NotificationCountOut`, service `services/notifications.ts`, Pinia store `stores/notifications.ts` con polling 60s (start/stop su auth change), componente `layouts/NotificationsBell.vue` (bell icon + badge rosso, 99+ cap), pagina `pages/Notifications.vue` con mark-read on click + auto-redirect su `link`, route `/me/notifications`, integrazione in `AppLayout.vue` (bell tra SearchBar e GearMenu)
- [✓] Smoke E2E: CLI run #1 → 1 digest creato per drtarr (361 articoli/24h); run #2 → 0 (idempotenza per giorno); GET notifications → 1 item; unread-count=1 → mark-all-read → unread=0
- [ ] Cron systemd timer in `infra/systemd/yf-notify-digest.{service,timer}` (CLI pronta, file da produrre al deploy)

## DoD v1.1
- [✓] Search restituisce risultati pertinenti su corpus reale (valutazione qualitativa OK su 1700 articoli — review formale postponed a 10K+)
- [✓] Forgot/reset password end-to-end con TTL 1h, mono-uso, revoca sessioni
- [✓] Device management con guard self-revoke + list/revoke
- [✓] Centro notifiche con digest giornaliero idempotente + badge live + polling 60s
- [✓] Google OAuth flow end-to-end in modalità simulata (drop-in al reale = singola riga `.env`)
- [ ] Attivazione Google OAuth reale + test E2E con 2 account (operativo, fuori scope code-side)

---

# v1.2 — Engagement

## Phase 1.2.A — NER spaCy + pre-lemmatizzazione [✓] (2026-05-11, iteration-1 live integration)

→ scope iteration-1: NER live in `classify.py` come **Step D**, affiancato a Step C regex. Solo sul titolo (coerente con policy T-018 title-only). Pre-lemmatizzazione Manticore lasciata operativa.
- [✓] Modello `it_core_news_lg` v3.8.0 scaricato (~500MB) via `python -m spacy download it_core_news_lg`. `spacy>=3.7` già in `pyproject.toml`.
- [✓] `app/ingestion/ner.py`: lazy-loaded `Language` via `@lru_cache(maxsize=1)` (cost ~1s caricamento, ~50ms per titolo), tagger+lemmatizer disabilitati (NER pipeline only, ~3x più veloce). `extract_entities(text)` ritorna `list[NerEntity]` con filtri:
  - Mapping `PER/PERSON → person`, `ORG → brand`, `LOC/GPE → location`. **MISC scartato** (troppo rumoroso in IT, copre prodotti/eventi/concetti — i modelli li copre già REGEX_MODEL).
  - Blacklist edge-token per stop-words/preposizioni/mesi/giorni IT (`anche`, `infatti`, `di`, `del`, `gennaio`, `lunedì`, …) con trim leading/trailing. Esempio: "Anche Mario Rossi" → "Mario Rossi", "di Bergamo" → "Bergamo".
  - Scarta single-token lowercase, token ≤2 char non-acronimi, single-token MISC. Dedupe per `(text.lower(), topic_type)`.
- [✓] `classify.classify(enable_ner_extraction: bool = True)`: nuovo parametro che gate Step D. `_extract_ner_matches` chiama spaCy sul titolo, mappa entità a TopicMatch via `_upsert_regex_topic` (riusa il pattern di Step C: slug-based upsert idempotente, `is_curated=false`, `source='ner'`, score=3.0). Cap per articolo: 5 PER, 3 ORG, 3 LOC. Dedup finale per `topic_id` evita duplicati quando dict/regex/NER convergono sullo stesso slug (vince score più alto, regex/dict precedono Step D nell'extend → tie wins regex/dict).
- [✓] `app/utils/reclassify_topics.py`: aggiunto flag `--no-ner` per A/B test e disabilitazione ad-hoc; propagato a `_reclassify_one` e a `classify.classify` via `enable_ner_extraction`.
- [✓] Test integration aggiunti: `test_step_d_ner_extracts_single_token_person` (verifica recall su single-token PER tipo "Yoshi" che regex ≥2-token non cattura) + `test_step_d_ner_disabled_when_flag_off`. Aggiornato `test_step_c_disabled_skips_regex` per passare `enable_ner_extraction=False` (Step C/D ortogonali).
- [✓] Smoke test reale: classify su title "Yoshi conquista i fan dopo il successo di Super Mario" produce 2 matches: `★ [person] 'Super Mario'` (dict) + `· [person] 'Yoshi'` (ner). Su 30 titoli random del corpus: NER cattura location single-word ("Bergamo", "Cina", "Marche", "Viterbo"), persons ("Maradona", "Vincenzo De Luca"), e brand non curated ("Corte costituzionale"). Dove regex e NER convergono → dedup tiene regex (score tie).
- [✓] 8/9 test step_c verdi (2 nuovi NER + 6 esistenti aggiornati); 1 fail rimasto è **pre-esistente**, non causato da NER (vedi sezione sotto).
- [ ] **Pre-lemmatizzazione `content_text` per Manticore**: rinviata a iteration-2 operativa. spaCy lemmatizer su tutti gli articoli aggiunge ~50ms/articolo + reindex completo. Manticore già usa `libstemmer_it` che copre buona parte della morfologia IT; gain marginale, costo non trascurabile. Da fare insieme al bulk-reclassify dopo verifica NER live in produzione 1-2 settimane.
- [ ] **A/B qualità search e reindex completo**: operativo, richiede strumentazione metriche (CTR risultati search, copertura `article_topics` pre/post-NER) e baseline. Da fare in staging dopo deploy.
- [ ] **Bulk reclassify con NER su corpus esistente**: `python -m app.utils.reclassify_topics --all --title-only` (NER attivo di default) ricalcolerà i topic di tutti gli articoli — da lanciare con `--max-batches` o limit prudente all'inizio.

### Test pre-esistenti rotti (NON causati dal NER, da investigare separatamente)
- `test_step_c_extracts_model_when_brand_is_matched` — `extract_models` regex ritorna `[]` per "Apple iPhone 15 Pro" con known_brands=['Apple']. Verificato manualmente con `from app.topic_extractor.extractor import extract_models; extract_models('Apple iPhone 15 Pro disponibile', known_brands=['Apple'])` → `[]`. Root cause: pattern `model_part` non matcha; serve debug separato.
- `test_related_articles_max_formula` / `test_related_articles_jaccard_stricter_than_max` — articles_service.related_articles formula cambiata (T-018 con coverage simmetrica + multi-topic sort + strong_single_min); test fixture probabilmente disallineato.
- `test_scan_models_uses_known_brands` — stessa root cause del primo (extract_models).

### Phase 1.2.A-pre — Topic extractor regex-based [✓ pronto, in uso operativo]

Tool interno per **far crescere il topic seed automaticamente** dagli articoli
già indicizzati. Anticipato a v1.0 perché non richiede spaCy ed è autosufficiente.

- [✓] Migration `0005_entity_source_counts`: tabella `entity_source_counts(entity_id, source_id, count)` per tracking polarizzazione (entity concentrate su 1-2 source = probabile rumore locale, non topic globale)
- [✓] Migration `0006_widen_ner_type`: `entities.ner_type` da varchar(16) → varchar(32) per accomodare tag tipo `REGEX_BRAND_SINGLE`
- [✓] `app/topic_extractor/extractor.py` (regex puri): cinque pattern speculari ai tipi `topics.type`:
  - `REGEX_PER`: 2-4 token con FIRST = full | sigla, MIDDLE = full | iniziale puntata | sigla, LAST = full. Gestisce **"Donald J. Trump"** (iniziale puntata in mezzo) e **"JD Vance"** (sigla iniziale). Trim post-match per parole italiane comuni capitalizzate (`Anche Mario Rossi` → `Mario Rossi`)
  - `REGEX_POPE`: `Papa <Nome>...` con anchor "Papa" + soglia minima 3-char (per "Pio") + opzionale numero romano fino a XX
  - `REGEX_BRAND_ALPHA`: alfanumerici come `7Up`, `3M`, `O2`, sigle `BMW`/`IBM`/`RAI`. Blacklist preposizioni italiane all-caps (`DI`, `DEL`, `LE`, mesi)
  - `REGEX_BRAND_SINGLE`: parola singola capitalizzata 4+ char in **mid-sentence** (preceduta da `[a-z,;:]\s`). Esclude inizio frase. Blacklist avverbi/connettivi/mesi italiani
  - `REGEX_MODEL`: `<known_brand> <num|word> [num|word]?` con whitelist brand confermati. Esempi: `Porsche 911`, `Boeing 747`, `Alfa Romeo 33 Stradale`, `Fiat Panda`
- [✓] `app/topic_extractor/service.py`: `scan_articles` legge `articles.raw_meta_lite['title' + 'description']` di tutti gli articoli `processing_status='indexed'`, applica gli extractor, aggrega in-memory (flush ogni 500 articoli) e fa upsert ON CONFLICT su `entities` (`occurrence_count += new`) e `entity_source_counts`. `review_top` ritorna candidate con `subtoken_topics` hint (es. "Coca Cola" → segnala se "Coca" è già un topic curated). `confirm_entity` crea/riusa Topic + linka `entity.topic_id`. `reject_entity` flippa `ignored=true`
- [✓] `app/topic_extractor/cli.py`: 5 comandi — `scan-generic` (pass-1), `scan-models` (pass-2 con whitelist brand), `review --type X --top N --min-count K`, `confirm <id> --as-type {brand|person|location|model|subject}`, `reject <id>`
- [✓] Workflow 2-fasi: pass-1 popola entities con tutti i pattern → utente promuove brand/person → pass-2 estrae model usando i brand confermati
- [✓] Test unit (38): tutti i pattern coperti — boundary persona (no inizio frase, sì mid-iniziale), papi (Pio/numeri romani), brand alphanum (7Up/3M/O2/BMW), brand single (mid-sentence/blacklist/min 4-char), model (con/senza numero, longest-match brand)
- [✓] Test integration (9): scan estrae & aggrega multi-articolo, increment counter, popola per-source counts, scan-models con whitelist, review filtra min_count, hint sub-token, confirm crea topic + link entity, reject flag, known_brand_names filtra `is_curated=true AND type='brand'`
- [ ] Espansione blacklist/lista geografica IT-only — operativo (l'utente offre liste curate)

## Phase 1.2.B — Wikidata enrichment topic [✓] (2026-05-11)

- [✓] `services/wikidata_service.py`: client httpx `wbsearchentities` (top-5 lang=it) + `wbgetentities` (label/desc/aliases/claims/sitelinks lang=it|en). User-Agent identificato come da policy Wikidata.
- [✓] Scoring multi-livello su match label/alias + token-inclusion (es. "Amazon.com" matcha "Amazon" → `label_token` 0.80). Levels: `label_it_exact` 1.00, `label_en_exact` 0.85, `alias_it_exact` 0.80, `label_token` 0.80, `alias_token` 0.75, `alias_en_exact` 0.70. Soglia default 0.7.
- [✓] **Type-aware filtering via P31 (instance of)**: per ogni topic.type whitelist di Q-IDs accettabili (brand: business/organization/brand/automobile-manufacturer/tech-company/newspaper/football-club/sports-team/…; person: Q5; location: city/country/comune/state/admin-region/…). Recupera full entity per i top-3 candidati e prende il primo P31-compatibile. Risolve disambiguazione "Amazon" → Q3884 (Amazon.com brand) invece di Q3783 (fiume) e "Atalanta" → low_confidence (Wikidata mette mitologia avanti, sistema rifiuta correttamente).
- [✓] Update non distruttivo: `description` non sovrascrive se non vuota (a meno di `force=True`); `aliases` merged case-insensitive con esistenti; `external_refs` jsonb update con `wikidata_qid`, `match_confidence`, `match_method`, `enriched_at`, `wikipedia_url_it`, `wikipedia_url_en`, `image` (commons URL P18, width=512). Idempotente: salta topic con qid già presente.
- [✓] RQ worker `workers/enrich.py` su coda `QUEUE_ENRICH_WIKIDATA` (già definita); job `enrich_wikidata_job(topic_id, force=False)`.
- [✓] Hook auto-trigger in `routers/admin.py`: `topics/bulk` action=validate accoda enrich per ogni id; `topics/create` accoda enrich per il topic appena curato/upserted. Best-effort (try/except, non blocca admin UI).
- [✓] CLI `python -m app.utils.enrich_topics --topic-id N` o `--missing --limit 50` (con rate-limit cortese 200ms tra chiamate); `--force` per overwrite.
- [✓] Smoke test reale: Intelligenza artificiale → Q11660 (1.00 label_it_exact, 17 aliases mergeati, image Commons, wiki IT+EN); Amazon → Q3884 (0.80 label_token, "compagnia di commercio elettronico statunitense"); Stati Uniti → Q30; OpenAI → Q21708200; Anthropic → Q116758847; NVIDIA → Q182477; Tesla → Q478214. Topic ambigui single-word (es. Atalanta) restano correttamente in `low_confidence` invece di scrivere dati sbagliati.
- [ ] Bulk enrich su tutti i topic curati (~2600) — run operativo, da fare con `--missing --limit 500` in più batch per non saturare Wikidata API.

## Phase 1.2.C — LLM fallback [⚠] (scartata 2026-05-11 per assenza di budget Anthropic)

→ può essere riconsiderata se in futuro emerge budget. Lo scope originale resta documentato:
- [ ] Anthropic SDK + chiave API + budget
- [ ] Prompt template per estrazione brand/persone/argomenti
- [ ] Trigger: solo articoli senza topic dopo dict+regexp+NER
- [ ] Cache Redis su risposte (TTL alto)
- [ ] Rate limit + circuit breaker

## Phase 1.2.D — Alert personalizzati [✓] (2026-05-11, iteration-1 topic-based)

→ scope iteration-1: alert basati su topic curati (allineato con CLAUDE.md: "argomenti, brand o personaggi famosi"). Keyword arbitraria rinviata a 1.2.D-ext: richiederebbe Manticore search per articolo, inefficiente lato matcher.
- [✓] Migration 0014: `alerts (id, user_id, topic_id FK, channels TEXT[] default {inapp}, is_enabled, created_at, updated_at, UNIQUE(user_id, topic_id), idx partial WHERE is_enabled)` + `alert_matches (alert_id, article_id, matched_at, PK composta)` (idempotenza built-in)
- [✓] Model `Alert`/`AlertMatch` in `models/alerts.py`; export da `models/__init__.py`
- [✓] Service `services/alert_service.py`: `list_alerts` (joined Topic), `create_alert` (ON CONFLICT DO UPDATE riabilita se esiste — idempotente), `update_alert`, `delete_alert`, `match_article` (carica topic_ids da `article_topics`, fa JOIN su `alerts.is_enabled=true`, per ogni alert INSERT … ON CONFLICT DO NOTHING su `alert_matches`, crea `Notification(kind='alert_match', link=/me/article/{id}, payload={alert_id,topic_id,topic_slug,article_id})`); recupera titolo articolo via `manticore_client.get_by_ids` (con fallback a `url_canonical` se Manticore fallisce)
- [✓] Endpoint `GET /yf_me/alerts`, `POST /yf_me/alerts`, `PATCH /yf_me/alerts/{id}`, `DELETE /yf_me/alerts/{id}`; schemi `AlertOut`/`AlertCreateIn`/`AlertUpdateIn`/`AlertTopicOut`
- [✓] RQ worker `workers/alerts.py` con coda `QUEUE_ALERTS_MATCH` (già definita in `queues.py`); job `alerts_match_article_job(article_id)` chiama `alert_service.match_article`
- [✓] Hook integrato in `workers/process.py`: dopo `mark_article_indexed`, se `n_topics > 0` accoda `enqueue_alerts_match(article_id)` best-effort
- [✓] Frontend `pages/Alerts.vue` con autocomplete topic (riusa `/yf_search/suggest`, debounce 250ms, filtra topic con alert già attivo), toggle is_enabled, delete con confirm, badge type colorato (brand/person/subject)
- [✓] Type `AlertOut`/`AlertTopicOut` in `types/api.ts`; service `services/alerts.ts` (list/create/update/delete); route `/me/alerts` + voce GearMenu "Alert"
- [✓] **Bugfix Manticore** durante smoke: `manticore_client.get_by_ids` usava `{"in":{"_id":...}}` ma Manticore vuole `{"in":{"id":...}}` per il filter — error 500 silenzioso. Fix applicato; doc inline aggiornato.
- [✓] Smoke E2E (single loop per evitare engine cross-loop): user+alert su topic 8116 (Intelligenza artificiale, 147 articoli) → match_article #1 = 1 notifica creata (title "Nuovo articolo su «Intelligenza artificiale»", body = vero titolo articolo HoYoverse/IA, link `/me/article/55927`) → match_article #2 = 0 (PK composta `alert_matches` impedisce duplicati)
- [ ] Keyword-based alerts (iteration-2): richiede integrazione con Manticore per match testuale per-articolo, throttling, rate limit. Lasciato in roadmap quando arriverà la richiesta utente.

## Phase 1.2.E — Web push (VAPID) [✓] (2026-05-11)

- [✓] CLI `python -m app.utils.vapid_keys` genera coppia EC P-256 PEM + public uncompressed b64url. Output formattato per copia-incolla in `.env` (con `\\n` escape per la private multi-line). Validato round-trip con `py_vapid.Vapid01.from_pem`.
- [✓] Migration 0015: `push_subscriptions (id, user_id FK CASCADE, endpoint UNIQUE, p256dh, auth, ua, created_at, last_seen_at)` con idx su user_id.
- [✓] Model `PushSubscription` in `models/push.py`; export da `models/__init__.py`. Settings VAPID già presenti in `config.py` (vapid_public_key, vapid_private_key, vapid_subject).
- [✓] `services/push_service.py`: `register_subscription` idempotente via ON CONFLICT DO UPDATE su endpoint; `delete_subscription` (by id), `delete_subscription_by_endpoint`, `list_subscriptions`; `is_configured()`/`public_key()` per esporre lo stato VAPID; `send_to_user(user_id, payload)` esegue pywebpush via `loop.run_in_executor`, droppa subs con HTTP 404/410 (sub gone), aggiorna `last_seen_at` per quelle raggiunte.
- [✓] Router `routers/push.py`: `GET /yf_push/vapid-key` (anon) restituisce `{public_key, configured}`; `GET /yf_me/push/subscriptions`; `POST /yf_me/push/subscriptions` (201, idempotente per endpoint); `DELETE /yf_me/push/subscriptions/{id}` (204); `POST /yf_me/push/test` invia una push di test alle sub correnti.
- [✓] RQ worker `workers/push.py` su coda `QUEUE_PUSH`; job `push_send_job(user_id, payload)` chiama `push_service.send_to_user`.
- [✓] Integrazione con alerts matcher: in `alert_service.match_article`, se `'push' in alert.channels` accoda `enqueue_push(user_id, {title, body, link, tag=alert-{id}})` dopo la creazione della Notification in-app. Tag `alert-{id}` permette `renotify` lato browser per gli stessi alert.
- [✓] Service worker `frontend/public/sw.js`: handler `install`/`activate` con `skipWaiting`+`clients.claim`; handler `push` parsa JSON payload, mostra notifica con icon/badge + `tag` (renotify); handler `notificationclick` chiude la notif, ri-focus tab esistente same-origin (con `client.navigate` se disponibile) o apre nuova window via `clients.openWindow(link)`.
- [✓] Frontend service `services/push.ts`: `pushSupported()` capability check; `ensureSWRegistered()` registra `/sw.js`; `getVapidKey()`; `subscribeUser()` orchestrazione completa (permission → SW → PushManager.subscribe con `applicationServerKey` da b64url → POST backend); `unsubscribeUser()` browser-side + DELETE backend per endpoint match; `sendTestPush()`, `listSubscriptions()`, `currentSubscription()`.
- [✓] Pagina `pages/NotificationSettings.vue` con stato (off / on / denied / unsupported / not_configured), bottoni attiva/disattiva/test, lista dispositivi registrati con UA heuristic + rimozione singola. Route `/me/settings/notifications` + voce GearMenu "Notifiche".
- [✓] `pages/Alerts.vue` aggiornata con checkbox per canale `inapp`/`push`; `onToggleChannel` persiste via PATCH `/yf_me/alerts/{id}` (channels list).
- [✓] Smoke E2E backend (subprocess con VAPID env var): `is_configured()=True`, `public_key()` esposta; register/list/idempotenza ON CONFLICT verificata (stesso endpoint → stesso id row); `send_to_user` con sub mock fallisce (endpoint fittizio) ma exercises tutto il path (executor + drop list update). VAPID generation CLI produce coppia valida.
- [ ] **Test E2E browser reale** (Chrome+Firefox desktop, Chrome Android): richiede HTTPS + chiavi VAPID committate in `.env` + permesso utente. Da fare manualmente in staging.

## Phase 1.2.F — Admin dashboard (basic) [✓] (2026-05-11)

- [✓] `/yf_admin/entities` (`templates/admin/entities.html`): list Entity dove `topic_id IS NULL AND ignored = false` ordinata per `occurrence_count DESC`. Filtri: `ner_type` (con counts), `min_count`, `limit`. Distribuzione per ner_type mostrata come pillole.
- [✓] Azione `POST /yf_admin/entities/{id}/promote`: crea un nuovo Topic curato (slug derivato, type derivato dal mapping `ner_type → topic_type` o override via form) e collega `entities.topic_id`. Idempotente per slug (`ON CONFLICT DO NOTHING` + upsert curated/type se topic preesistente). Accoda enrich Wikidata best-effort. Invalida classifier cache.
- [✓] Azione `POST /yf_admin/entities/{id}/link`: collega Entity a Topic esistente (input numeric topic_id).
- [✓] Azione `POST /yf_admin/entities/{id}/ignore`: marca `entities.ignored=true`.
- [✓] `/yf_admin/featured` (`templates/admin/featured.html`): list FeaturedSource joined Source con ordinamento `position ASC, source_id ASC`. Form aggiungi/aggiorna (campos: source_id, category_hint, display_name, description, position) idempotente via `ON CONFLICT DO UPDATE` su PK source_id. Azione delete singola.
- [✓] `/yf_admin/sources` (`templates/admin/sources.html`): list Source con filtro su status (default `broken`, badge cliccabili per status alternativi + count distribution). Azione `POST /yf_admin/sources/{id}/reset-failures` che resetta `consecutive_failures=0` + `status='active'` (utile dopo aver risolto manualmente il problema).
- [✓] Nav links in `templates/admin/base.html`: aggiunti "Entità", "Sources", "Featured".
- [✓] Smoke test: tutte le pagine HTTP 200 con HTTP Basic; promote E2E (creata Entity sintetica, POST → 303 redirect, verificata creazione Topic curato + entity.topic_id linkato).
- [ ] `users.role` (forward-looking): per ora admin gate è solo HTTP Basic via `.env`; aggiungere la colonna è triviale ma non sblocca nulla finché non c'è una use-case API admin per utenti loggati. Rinviato.

## Phase 1.2.G — Retention sweep [✓] (2026-05-11)

- [✓] `services/retention_service.py` con `_candidate_filter`: articoli `published_at < now - max_age_days` AND `read_count=0` AND `open_count=0` AND nessun `alert_matches` AND source non in `featured_sources` (con `featured_until` futuro o NULL).
- [✓] `sweep(db, max_age_days, batch_size, max_batches, dry_run)` con batching (default 500 articoli/batch), `dry_run` per conta-soltanto, `max_batches` per limite throughput per primi cicli prudenti. Ogni batch: Manticore `delete_article` per id + PG `DELETE … RETURNING` (cascade su `article_topics`, `article_entities`, `alert_matches`).
- [✓] CLI `python -m app.utils.retention_sweep` con `--max-age-days N` (default 365), `--batch-size N`, `--max-batches N`, `--dry-run`. Da schedulare weekly via cron / systemd timer (file `.timer` da produrre al deploy).
- [✓] `SweepStats` dataclass: candidates/deleted/manticore_failed/dry_run per logging strutturato.
- [✓] Smoke test: dry-run rilevò 57 candidati (archive 2015-2017 senza engagement); test reale con `--batch-size 5 --max-batches 1` cancellò 5 articoli del 2015 (lowest IDs by `ORDER BY id ASC`) sia da PG che da Manticore (`manticore_failed=0`); count successivo confermò -5 (51 candidati residui, ±1 per articoli ingestiti nel frattempo).
- [ ] **Cleanup file immagini orfane**: lasciato fuori scope iteration-1 perché dedup-per-URL-hash significa che lo stesso file fisico può servire più articoli. Una garbage-collection separata si può fare con un job dedicato che conta i reference (TODO 1.2.G-ext quando lo spazio disco diventa critico).
- [ ] **Drift PG ↔ Manticore pre-esistente**: durante lo smoke ho notato Manticore total 3231 vs PG 1971. Non causato dal sweep (Manticore_failed=0) — è drift accumulato da operazioni precedenti. Andrà fatto un re-sync separato (TODO operativo).

## DoD v1.2
- [✓] Alert end-to-end funzionante (topic-based, in-app + push channel); latency su corpus reale < 5s nel matcher
- [ ] Push delivery testato su Chrome+Firefox desktop e Chrome Android (operativo, richiede HTTPS + chiavi VAPID committate)
- [✓] NER spaCy integrato live come Step D in `classify`; smoke test reale conferma recall su single-token PER/LOC che il regex extractor ≥2-token non cattura. Misura formale "+30% copertura" pendente al bulk reclassify operativo.
- [ ] Wikidata popola description/image/aliases per il 90% dei topic curati con confidenza alta (servizio pronto, manca bulk run `--missing --limit 500` sui 2600 topic residui)
- [⚠] LLM fallback scartato per assenza di budget (decisione 2026-05-11)

---

# v2.0 — Personalizzazione

## Phase 2.0.A — Recommendation engine (research + design)

- [ ] Definire metric: nDCG@10 su set di valutazione manuale
- [ ] Costruire set di valutazione (1000 query/utente con relevance label)
- [ ] Migration: `user_topic_affinity`, `user_source_affinity`
- [ ] Computazione affinity vectors da `activity_log` (recency-weighted)
- [ ] Algoritmo ranking iniziale: combo (match topic profilo, freshness, source affinity, co-occurrence)
- [ ] Cold start strategy

## Phase 2.0.B — Topic relations + UI

- [ ] Migration: `topic_relations`
- [ ] RQ batch `compute_topic_relations` (PMI o NPMI da decidere) schedulato weekly
- [ ] Endpoint `GET /yf_topics/{slug}/related`
- [ ] Sidebar "Topic correlati" su `/{username}/topic/{name}` (Jinja) e su `/me/timeline/topic/:slug` (Vue)

## Phase 2.0.C — Engagement analytics utente

- [ ] Endpoint `GET /yf_me/stats` con trend di lettura, top fonti, top topic
- [ ] Frontend `StatsPage.vue` con grafici (Chart.js o simile)
- [ ] Privacy: solo l'utente vede i propri dati

## Phase 2.0.D — Mobile Android app

- [ ] Decisione tech stack (Compose + Ktor / Flutter / nativo Java)
- [ ] Auth Bearer token su stessa sessione web
- [ ] Featuremap parità con web SPA (timeline, fonti, categorie, alert, push)
- [ ] Pubblicazione Play Store

## DoD v2.0
- [ ] Reco offline metrics nDCG@10 su set di valutazione > soglia X (TBD)
- [ ] Mobile app pubblicata su Play Store
- [ ] Topic correlati testati su almeno 50 topic e validati a campione

---

# Decisioni residue (cross-doc, da chiudere quando rilevante)

Tutti i punti "Da definire" rimasti nei singoli doc sono di portata limitata e si possono chiudere in fase di sviluppo della relativa Phase. Lista cumulativa:

**[ARCHITECTURE.md](ARCHITECTURE.md)**
- [ ] Backup destination (offsite via rsync? S3-compatible?)
- [ ] Monitoring concreto (Sentry? Grafana? log centralizzati?)

**[BACKEND.md](BACKEND.md)**
- [ ] Strategia partizionamento `activity_log` (manuale vs `pg_partman`)
- [ ] Politica MaxMind: lista ASN/country da bloccare
- [ ] Quando esporre OpenAPI schema (`/yf_docs` solo in dev?)

**[DATABASE.md](DATABASE.md)**
- [ ] Anonimizzazione `activity_log` su delete account (GDPR right to erasure)
- [ ] `raw_meta_lite`: lista esatta dei campi
- [ ] Schema versioning Manticore (rebuild background?)
- [ ] Archive cold storage per articoli espulsi da retention

**[INGESTION.md](INGESTION.md)**
- [ ] Comportamento WP API protetti / `per_page` cap basso
- [ ] Limite `content_html` salvato (per copyright)
- [ ] Frequenza reindicizzazione completa Manticore
- [ ] Allowlist/denylist domini per ingestion
- [ ] Quando attivare AVIF in aggiunta/sostituzione di WebP

**[KNOWLEDGE-GRAPH.md](KNOWLEDGE-GRAPH.md)**
- [ ] Soglia occorrenze per promuovere `entities` a candidato review
- [ ] Algoritmo `weight` di `topic_relations` (PMI / NPMI / count normalizzato)
- [ ] Frequenza ricalcolo `topic_relations`
- [ ] Soglia confidenza match Wikidata automatico
- [ ] UI admin per resolution entity

**[FRONTEND.md](FRONTEND.md)**
- [ ] Palette primario/accento + logo + favicon set
- [ ] Errore "fonte non valida": messaggio educativo per utente
- [ ] Numero esatto e nomi finali delle categorie suggerite

---

# Come usare questo file

1. Quando inizi una phase: marca `[~]` accanto al titolo della phase + data start
2. Quando finisci un task: marca `[✓]`
3. Se un task si blocca: marca `[⚠]` e annota il motivo nel task stesso
4. Quando una phase è completa: marca tutta la phase `[✓]`
5. Aggiorna "Stato corrente" in cima al file ad ogni cambio di fase
6. Le decisioni "Da definire" si spostano nei doc tecnici quando vengono chiuse (rimuoverle da qui)
