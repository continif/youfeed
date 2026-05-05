# STATUS — pianificazione operativa YOUFEED

Sequenza dei task per arrivare alla v1.0 e oltre. Aggiornare quando una fase parte, finisce o cambia priorità.

## Stato corrente

- **Fase**: scaffolding v1.0 Phase 0-8 completato (config, infra, data prep, DB schema, backend skeleton, middleware, auth, email, categorie/sources CRUD, discovery URL)
- **Codice scritto**: backend bootable (`app.main:app`), ~20 endpoint operativi, smoke test passing su 6 file (passwords, slugify, app start, email templates, category tree, discovery parsers)
- **Prossimo step concreto**: Phase 9 v1.0 — pipeline ingestion articoli (scheduler + fetch RSS/WP + normalize + classify + Manticore sync)

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

- [✓] Creare struttura repo `youfeed/` con `backend/`, `frontend/`, `infra/`, `docs/` (i Claude/*.md restano)
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

## Phase 9 — Ingestion: pipeline articoli

→ richiede Phase 8
- [ ] `ingestion/scheduler.py`: tick + dispatch su code per `kind`, politeness lock Redis per host
- [ ] `ingestion/fetch_rss.py`: `feedparser` + ETag/If-Modified-Since + retry
- [ ] `ingestion/fetch_wp.py`: WP API client con `_embed=1`, paginazione `?after=`
- [ ] `ingestion/normalize.py`: URL canonical, dedup hash, internal_links, HTML strip → content_text, date UTC, image fallback
- [ ] `ingestion/classify.py`: Step A taxonomy + Step B dizionario + Step C regexp (con stopwords IT)
- [ ] `ingestion/manticore_sync.py`: REPLACE INTO RT index idempotente
- [ ] RQ workers: `fetcher_rss`, `fetcher_wp`, `process_article` (collassato MVP), `indexer`
- [ ] Test E2E: aggiungi fonte → polling → articolo apparso in PG + Manticore + topic estratti
- [ ] Job riconciliazione PG↔Manticore (notturno)

## Phase 10 — Ingestion: image processing

→ richiede Phase 9
- [ ] `ingestion/image.py`: fetch (10s timeout, 10MB cap), Pillow open, resize Lanczos 370/1200, WebP encode q=80
- [ ] Sharding path `{hash[:2]}/{hash[2:4]}/{hash}_{m,d}.webp`
- [ ] RQ worker `image_processor`
- [ ] Apache Alias `/images/*` con Cache-Control immutable
- [ ] Test su 50 articoli reali con varietà di formati

## Phase 11 — Articles read API

→ richiede Phase 9
- [ ] `services/timeline_service.py`: query articoli per user_sources con pagination cursor
- [ ] Endpoint `GET /yf_home/me` (loggato, timeline + categorie sidebar)
- [ ] Endpoint `GET /yf_home/public` (anonimo, ultime news raggruppate per topic)
- [ ] Endpoint `GET /yf_topics`, `GET /yf_topics/{slug}`
- [ ] Endpoint `POST /yf_track` (batch eventi: impression, click, dwell, scroll)
- [ ] Worker `activity_log` batch insert + aggregati read_count/open_count/last_read_at
- [ ] Test query plan timeline (EXPLAIN ANALYZE su corpus seed)

## Phase 12 — Public dispatcher (Jinja2)

→ richiede Phase 11
- [ ] `templates/base.html` con meta tag completi + theme inline script
- [ ] Macros: `_meta.html`, `_header.html`, `_footer.html`, `_article_card.html`, `_category_tree.html`
- [ ] Template `home_public.html` (raggruppata per topic)
- [ ] Template `user/profile.html`, `user/category.html`, `user/topic.html`
- [ ] Template `rss/feed.xml` (macro per tutte le varianti RSS)
- [ ] Template `errors/404.html`, `403.html`, `500.html`
- [ ] Dispatcher catch-all `/{username}/{rest:path}` con risoluzione username + reserved check
- [ ] Endpoint `GET /sitemap.xml` dinamica
- [ ] Endpoint `GET /robots.txt` statico
- [ ] Pagine statiche: `/about`, `/privacy`, `/terms`

## Phase 13 — Frontend foundation (Vue SPA)

→ richiede Phase 5 (per API contracts)
- [ ] Vite project + struttura cartelle (vedi [FRONTEND.md](FRONTEND.md))
- [ ] Tailwind config condiviso (Vue + Jinja templates folder in `content`)
- [ ] Theme switcher con `useDark()` + localStorage `yf_theme` + inline init script in `index.html`
- [ ] API client `services/api.ts` con `ky`, baseURL `/yf_`, credentials include, interceptors
- [ ] Auth store Pinia + guards Vue Router
- [ ] Layout shell `<App.vue>` con `<Header>`, `<MainContent>`, `<Footer>`
- [ ] Componenti UI base: `Button`, `Input`, `Select`, `Modal`, `Toast`, `Spinner`
- [ ] Componente `<CookieBanner>` (senza FingerprintJS gating ancora)

## Phase 14 — Auth pages SPA

→ richiede Phase 13
- [ ] `LoginPage.vue` con form Zod + VeeValidate
- [ ] `RegisterPage.vue`
- [ ] `VerifyEmailPendingPage.vue` (post-register)
- [ ] `VerifyEmailTokenPage.vue` (link da mail)
- [ ] Toast su errori API + redirect post-login

## Phase 15 — User app SPA: timeline & sources

→ richiede Phase 14
- [ ] Componente `<ArticleCard>` masonry con bordo categoria, `<picture>` srcset mobile/desktop, fallback URL originale
- [ ] Componente `<TimelineFeed>` con cursor pagination + masonry CSS columns
- [ ] `TimelinePage.vue` (default + filtro categoria + filtro topic)
- [ ] `SourcesPage.vue` (lista + bottone aggiungi)
- [ ] `<SourceWizard>` 3-step con OG preview e link a Featured
- [ ] `<FeaturedSourcesGallery>` con filtro per category_hint
- [ ] `AddSourcePage.vue` che ospita il wizard

## Phase 16 — User app SPA: categorie

→ richiede Phase 15
- [ ] Componente `<CategoryColorPicker>` con 16 swatch + hex custom + ruota colori complementari (`colord`) + validazione contrasto WCAG AA
- [ ] Componente `<CategoryTree>` drag-drop con `vue-draggable-plus`
- [ ] `CategoriesPage.vue`

## Phase 17 — User app SPA: settings & GDPR

→ richiede Phase 16
- [ ] `AccountSettingsPage.vue`: change password form
- [ ] `PrivacySettingsPage.vue`: toggle tracking + revoke consenso
- [ ] FingerprintJS dynamic import gated da consenso
- [ ] Endpoint `GET /yf_me/export` (ZIP con JSON multipli: utente, categorie, fonti, sessioni)
- [ ] Endpoint `DELETE /yf_me` con cascade + anonimizzazione activity_log
- [ ] Bottoni "Scarica i miei dati" e "Elimina account" in AccountSettingsPage

## Phase 18 — Onboarding tour

→ richiede Phase 17
- [ ] Componente `<OnboardingTour>` con `driver.js`
- [ ] 7 step: welcome → categorie suggerite (multi-select) → fonti suggerite → color picker → privacy → feed pubblico → fine
- [ ] `PATCH /yf_me` per `onboarding_completed_at`
- [ ] Skip in qualsiasi momento

## Phase 19 — SEO & sitemap

→ richiede Phase 12
- [ ] Sitemap.xml dinamica con `lastmod` corretto (max published_at per pagina)
- [ ] Structured data JSON-LD nelle pagine pubbliche (`CollectionPage`, `NewsArticle`)
- [ ] Open Graph + Twitter Card meta tag su tutte le pagine pubbliche
- [ ] Canonical URLs corretti
- [ ] Ping a Google Search Console + Bing dopo deploy v1.0

## Phase 20 — Operational hardening

→ richiede tutte le precedenti
- [ ] Tutti i systemd units configurati con `Restart=on-failure`, `RestartSec=5`, log su journald
- [ ] Script `infra/deploy.sh`: git pull + pip + alembic + npm build + systemctl restart
- [ ] Script `infra/backup.sh`: pg_basebackup + manticore BACKUP + rsync verso destinazione (TBD)
- [ ] RQ worker `manage_partitions` schedulato daily
- [ ] Healthcheck endpoint integrato con monitoring esterno (TBD)
- [ ] Documentazione runbook in `docs/runbook.md` (avvio/stop, restore backup, incidenti tipici)

## Phase 21 — Definition of Done v1.0

- [ ] 28 endpoint testati con fixture pytest
- [ ] Ingestion stabile su almeno 50 fonti reali per 7 giorni continui
- [ ] Dedup verificata (no duplicati su URL canonicalizzata su 10K+ articoli)
- [ ] Image processing produce entrambe le varianti WebP per >90% degli articoli con immagine
- [ ] Topic seed di almeno 200 entità caricato e usato dalla classificazione
- [ ] Cookie banner + privacy policy live
- [ ] GDPR export ZIP + delete testati end-to-end
- [ ] Sitemap accessibile, ping a Google effettuato
- [ ] Backup PG + Manticore schedulati e restore testato una volta
- [ ] Rate limit attivo, blocco MaxMind verificato su scrittura
- [ ] Theme switcher e tour testati su Chrome + Firefox + Safari (desktop e mobile)
- [ ] Lighthouse score ≥ 90 su `/{username}` campione (perf + a11y + SEO)
- [ ] Almeno 5 utenti beta effettivi con feedback raccolto

---

# v1.1 — Polish & search

## Phase 1.1.A — Google OAuth

→ richiede v1.0 stabile
- [ ] Configurazione Google Cloud Console (client_id, secret, redirect URI)
- [ ] `services/oauth_service.py` con `authlib`
- [ ] Endpoint `GET /yf_auth/google/authorize` + `GET /yf_auth/google/callback`
- [ ] Frontend `OAuthCallbackPage.vue`
- [ ] Bottone "Accedi con Google" su LoginPage e RegisterPage
- [ ] Test E2E con account test

## Phase 1.1.B — Forgot/reset password

- [ ] Migration: tabella `password_reset_tokens`
- [ ] Endpoint `POST /yf_auth/forgot-password` (genera token + invia email)
- [ ] Endpoint `POST /yf_auth/reset-password` (consuma token + cambia password)
- [ ] Template email reset
- [ ] Frontend `ForgotPasswordPage.vue` + `ResetPasswordPage.vue`

## Phase 1.1.C — Device management

- [ ] Endpoint `GET /yf_me/devices` (sessioni con fingerprint, last_seen, geo)
- [ ] Endpoint `DELETE /yf_me/devices/{id}` (revoca sessione)
- [ ] Frontend `DevicesPage.vue` con lista + bottone revoca
- [ ] Notifica email opzionale su nuova sessione (TBD)

## Phase 1.1.D — Search Manticore

- [ ] Query helper Manticore con filtro condizionale (loggato → user_sources)
- [ ] Endpoint `GET /yf_search`, `GET /yf_search/suggest`, `GET /yf_search/sources`
- [ ] Frontend `SearchPage.vue` con highlight risultati
- [ ] Componente `<SearchBar>` in header
- [ ] Test relevance review su corpus 10K+ articoli

## Phase 1.1.E — Centro notifiche in-app

- [ ] Migration: tabella `notifications`
- [ ] Cron daily che genera digest "il tuo feed ha N nuovi articoli oggi" per utenti attivi
- [ ] Endpoint `GET /yf_me/notifications`, `PATCH /yf_me/notifications/{id}/read`
- [ ] Frontend `NotificationsPage.vue` + badge contatore in header

## DoD v1.1
- [ ] Login Google end-to-end con almeno 2 account test
- [ ] Search restituisce risultati pertinenti su 10K+ articoli (relevance manuale)
- [ ] Centro notifiche mostra digest giornaliero per utenti con almeno una fonte

---

# v1.2 — Engagement

## Phase 1.2.A — NER spaCy + pre-lemmatizzazione

→ richiede v1.1 stabile
- [ ] Installazione modello `it_core_news_lg` su server
- [ ] Sostituzione/affiancamento Step C (regexp) con NER spaCy
- [ ] Pre-lemmatizzazione `content_text` durante extraction → indice Manticore aggiornato
- [ ] A/B su qualità search prima/dopo
- [ ] Reindicizzazione completa Manticore una tantum

## Phase 1.2.B — Wikidata enrichment topic

- [ ] Modulo `services/wikidata.py`: search + SPARQL
- [ ] RQ worker `enrich_wikidata` triggerato a creazione/curation topic
- [ ] Soglia confidenza match (TBD a fronte di test reali)
- [ ] Update `topics.description`, `topics.aliases` (merge), `topics.external_refs`

## Phase 1.2.C — LLM fallback

- [ ] Anthropic SDK + chiave API + budget
- [ ] Prompt template per estrazione brand/persone/argomenti
- [ ] Trigger: solo articoli senza topic dopo dict+regexp+NER
- [ ] Cache Redis su risposte (TTL alto)
- [ ] Rate limit + circuit breaker

## Phase 1.2.D — Alert personalizzati

- [ ] Migration: `alerts`, `alert_matches`
- [ ] Endpoint CRUD alerts (5 endpoint)
- [ ] RQ worker `alerts_matcher` triggerato per ogni nuovo articolo
- [ ] Frontend `AlertsPage.vue`, `AlertEditorPage.vue`
- [ ] Selettore di tipo (string / brand / person) con autocomplete topic

## Phase 1.2.E — Web push (VAPID)

- [ ] Generazione chiavi VAPID, persistenza in env
- [ ] Migration: `push_subscriptions`
- [ ] Endpoint `GET /yf_push/vapid-key`, `POST /yf_me/push/subscriptions`, `DELETE /yf_me/push/subscriptions/{id}`
- [ ] Service Worker `sw.js` con handler `push` e `notificationclick`
- [ ] RQ worker `push` invio web push via `pywebpush`
- [ ] Frontend `NotificationsSettingsPage.vue` con toggle subscribe/unsubscribe + test push
- [ ] Integrazione con `alerts_matcher`: su match con `'push' in channels`, accoda push job

## Phase 1.2.F — Admin dashboard (basic)

- [ ] Aggiungere `users.role` ('user' | 'admin'), guard backend
- [ ] Pagina `/yf_admin/entities` con lista entità non risolte ordinate per `occurrence_count`
- [ ] Action: promuovi a topic / collega ad alias / ignora
- [ ] Lista featured_sources con add/remove
- [ ] Lista source con `status='broken'` per intervento manuale

## Phase 1.2.G — Retention sweep

- [ ] RQ worker `retention_sweep` schedulato weekly
- [ ] Drop articoli > 12 mesi senza engagement (no read, no open, no alert match)
- [ ] Cleanup file immagini locali per articoli droppati
- [ ] Dry-run mode per primi cicli

## DoD v1.2
- [ ] Alert testato su almeno 20 utenti, latency < 60s dall'ingestion
- [ ] Push delivery testato su Chrome+Firefox desktop e Chrome Android
- [ ] NER aumenta copertura `article_topics` di almeno il 30% rispetto a regexp+dict
- [ ] Wikidata popola description/image/aliases per il 90% dei topic curati con confidenza alta

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
