# YOUFEED — MVP Scope

Documento di pianificazione delle release. Definisce cosa entra in v1.0 (primo lancio), v1.1, v1.2, v2.0. Aggiornare quando una decisione di scope cambia.

## Principi di taglio

1. Il MVP deve permettere all'utente di fare la cosa fondamentale: aggiungere fonti, leggerle, condividere il feed pubblico.
2. Tutto ciò che richiede massa di dati per funzionare bene (search, alert, recommendation) può aspettare la seconda release: al lancio non avremo abbastanza articoli né sessioni per giudicarne la qualità.
3. Tutto ciò che è hygiene di sicurezza (auth, fingerprint, MaxMind base, reserved words, rate limit) non si taglia mai.
4. Tutto ciò che è obbligo legale (GDPR: cookie banner, privacy policy, data export, account deletion) non si taglia mai.
5. La **vista per topic** `/{username}/topic/{name}` è il tratto distintivo di YOUFEED: resta in v1.0 anche al costo di pre-popolare manualmente i topic curati.

---

## Roadmap

| # | Funzionalità / componente | v1.0 | v1.1 | v1.2 | v2.0 |
|---|---|:-:|:-:|:-:|:-:|
| 1 | Registrazione email/password + verifica | ✅ | | | |
| 1 | Google OAuth login | | ✅ | | |
| 2 | Cambio password (loggato) | ✅ | | | |
| 2 | Forgot/reset password | | ✅ | | |
| 2 | Device management (lista sessioni, revoca) | | ✅ | | |
| 3 | Categorie ricorsive + aggiunta fonti (RSS+WP API discovery) | ✅ | | | |
| 4 | Alert personalizzati (string/brand/person) | | | ✅ | |
| 5 | Home loggata (timeline) | ✅ | | | |
| 5 | Home pubblica raggruppata per topic | ✅ | | | |
| 6 | URL pubblici `/{username}`, `/{username}/{cat}/{sub}` + RSS | ✅ | | | |
| 6 | URL pubblici `/{username}/topic/{name}` + RSS | ✅ | | | |
| 7 | Search full-text Manticore | | ✅ | | |
| 8 | Web push (VAPID) | | | ✅ | |
| 8 | Centro notifiche in-app | | ✅ | | |
| — | Activity log raw + aggregati read/open su articles | ✅ | | | |
| — | Estrazione: origin taxonomy + dizionario + regexp | ✅ | | | |
| — | Estrazione: NER spaCy | | | ✅ | |
| — | Pre-lemmatizzazione spaCy del `content_text` per Manticore | | | ✅ | |
| — | Estrazione: Wikidata enrichment topic curati | | | ✅ | |
| — | Estrazione: LLM fallback (Claude Haiku) | | | ✅ | |
| — | Recommendation engine | | | | ✅ |
| — | Topic correlati (`topic_relations` + UI) | | | | ✅ |
| — | Admin dashboard (entity review, topic candidates) | | | ✅ | |
| — | Cookie banner + GDPR data export/erasure | ✅ | | | |
| — | SEO (sitemap.xml, robots.txt, structured data) | ✅ | | | |
| — | Image local processing (WebP mobile+desktop) | ✅ | | | |
| — | Theme switcher (dark/light/system) | ✅ | | | |
| — | Color per categoria (UI bordo articolo) | ✅ | | | |
| — | Tour guidato primo login (Driver.js) | ✅ | | | |
| — | Categorie suggerite a scopo introduttivo | ✅ | | | |
| — | Fonti popolari italiane (`<FeaturedSourcesGallery>`) | ✅ | | | |
| — | Open Graph preview in source wizard | ✅ | | | |
| — | Layout masonry tipo Pinterest | ✅ | | | |
| — | Mobile Android app | | | | ✅ |
| — | Cron retention sweep (utile solo >12 mesi) | | | ✅ | |

---

## v1.0 — MVP usable (primo lancio pubblico)

### Cosa fa l'utente

- Si registra con email/password, riceve mail di verifica via SMTP OVH, clicca il link, può fare login
- Cambia la propria password dal proprio profilo (richiede password attuale)
- Crea categorie e sottocategorie (alberatura ricorsiva via `parent_id`)
- Aggiunge fonti incollando URL: il sistema fa discovery (WP API → RSS → invalid). Se ci sono più candidati, sceglie da una lista con anteprima
- Vede la propria timeline cronologica con filtro per categoria
- Apre un articolo (clic registrato in `activity_log`, aggregato in `articles.open_count`)
- Il proprio feed `/luca` è pubblico; `/luca/sport`, `/luca/sport/serieA` funzionano. Tutti hanno la versione `.../rss` per export
- `/luca/topic/inter` mostra tutti gli articoli sull'Inter dalle fonti dell'utente
- Home pubblica `youfeed.it/`: ultime news raggruppate per topic curato (24h, top per # fonti)
- Accetta cookie banner; può scaricare i propri dati ed eliminare l'account

### Sotto il cofano

- Backend FastAPI con auth cookie + fingerprint (FingerprintJS), Bearer non ancora abilitato (mobile rimandato)
- Apache reverse proxy + Cloudflare in front
- Postgres + Manticore content store sincronizzati via job RQ idempotente
- Ingestion: pipeline WP API + RSS, normalization (URL canonical, dedup, internal links extraction, HTML strip), dictionary classification + regexp heuristics (no NER, no LLM)
- **Image processing pipeline**: fetch + resize WebP in 2 varianti (mobile 370px, desktop max 1200px) salvate su filesystem locale con sharding hash; URL originale conservato come fallback
- ~200-500 topic curati pre-caricati a mano via SQL/seed (squadre Serie A, partiti, top brand IT, personaggi politici/calciatori top)
- Activity log raw partizionato per giorno + worker che aggrega `read_count`/`open_count`/`last_read_at` su `articles`
- MaxMind block base: paesi a rischio sui soli endpoint scrittura, `CF-Connecting-IP` rispettato
- Rate limit base via Redis: 60 req/min per IP anonimo, 600 req/min per utente loggato
- Reserved words enforcement su `username-available` e `register`
- Cookie banner pre-fingerprint (FingerprintJS solo dopo consenso)
- Privacy policy + ToS pubblicate
- Data export: endpoint `GET /yf_me/export` ritorna ZIP con JSON multipli (utente, categorie, fonti, sessioni, alert, notifiche)
- Account deletion: `DELETE /yf_me` cancella user + cascade su categorie/user_sources/sessioni; activity_log anonimizzato (user_id → NULL)
- Sitemap.xml dinamica per `/{username}` di profili pubblici + `/{username}/topic/{name}`; robots.txt
- Email transazionali via SMTP OVH (casella dedicata su dominio youfeed.it, es. `noreply@youfeed.it`)
- **Theme dark/light/system** con toggle utente (persistito in localStorage), inline script anti-FOIT in `<head>`
- **Layout masonry** Pinterest-like su timeline e topic page; bordo card colorato per categoria
- **Tour guidato primo login** con Driver.js (welcome → aggiungi prima fonte → categorie → privacy → feed pubblico)

### Endpoint backend (v1.0)

Auth (6):
- `POST /yf_auth/register`
- `GET /yf_auth/verify-email`
- `POST /yf_auth/resend-verification`
- `GET /yf_auth/username-available`
- `POST /yf_auth/login`
- `POST /yf_auth/logout`

Profilo (4):
- `GET /yf_me`
- `POST /yf_me/change-password`
- `GET /yf_me/export` *(GDPR)*
- `DELETE /yf_me` *(GDPR)*

Categorie (4):
- `GET /yf_me/categories`
- `POST /yf_me/categories`
- `PATCH /yf_me/categories/{id}`
- `DELETE /yf_me/categories/{id}`

Fonti (6):
- `POST /yf_sources/discover`
- `GET /yf_sources/featured` *(gallery onboarding, raggruppato per category_hint)*
- `GET /yf_me/sources`
- `POST /yf_me/sources`
- `PATCH /yf_me/sources/{id}`
- `DELETE /yf_me/sources/{id}`

Home (2):
- `GET /yf_home/public`
- `GET /yf_home/me`

Topic catalog (2):
- `GET /yf_topics`
- `GET /yf_topics/{slug}`

Activity (1):
- `POST /yf_track`

Trasversali (2):
- `GET /yf_health`
- `GET /yf_version`

Public dispatcher (1 path catch-all):
- `GET /{username}/{path:path}` con sub-routing HTML/RSS

**Totale v1.0: 28 endpoint applicativi.**

### Tabelle DB (v1.0)

Postgres:
- `users`, `auth_sessions`, `email_verification_tokens`, `reserved_usernames`
- `sources`, `user_sources`, `categories`, `featured_sources`
- `articles` (con `read_count`, `open_count`, `last_read_at`, `internal_links`, `image_*`)
- `topics`, `entities`, `article_topics`, `article_entities`
- `activity_log` (PARTITION BY RANGE (ts), partizioni daily)

Manticore:
- `articles_rt` (RT index)

### Worker RQ (v1.0)

- `url_processor` (coda `discover`)
- `scheduler` (1 istanza)
- `fetcher_rss` + `fetcher_wp`
- `normalizer` + `extractor` + `indexer` *(in MVP collassati in `process_article`)*
- `image_processor` (fetch + resize WebP in 2 varianti)
- `activity_log` (batch insert + aggregati)
- `manage_partitions` (cron daily)

### Definition of Done v1.0

- [ ] 28 endpoint testati con fixture pytest
- [ ] Ingestion stabile su almeno 50 fonti reali (mix RSS + WP API italiane) per 7 giorni
- [ ] Dedup verificata (no duplicati su URL canonicalizzata)
- [ ] Image processing produce entrambe le varianti WebP per >90% degli articoli con immagine
- [ ] Topic curati seed di almeno 200 entità (squadre, partiti, brand, persone IT)
- [ ] Cookie banner + privacy policy live
- [ ] GDPR export ZIP + delete testati end-to-end
- [ ] Sitemap accessibile e ping a Google
- [ ] Backup Postgres + Manticore schedulati e restore testato una volta
- [ ] Rate limit attivo, blocco MaxMind verificato su scrittura
- [ ] Theme switcher e tour guidato testati su Chrome + Firefox + Safari (desktop e mobile)
- [ ] Lighthouse score ≥ 90 su `/{username}` campione (perf + a11y + SEO)

---

## v1.1 — Polish & search

### Aggiunte funzionali

- **Google OAuth**: registrazione e login con Google (riduce attrito di iscrizione)
- **Forgot/reset password**: flusso "ho dimenticato la password" via mail
- **Device management**: l'utente vede le proprie sessioni attive (web/mobile, fingerprint, ultimo accesso, geo) e può revocarle
- **Search full-text Manticore**: barra di ricerca attiva, comportamento condizionale (utente loggato cerca solo nei propri feed; anonimo cerca su tutto)
- **Centro notifiche in-app**: tabella `notifications` + UI per leggere/contrassegnare. In v1.1 le notifiche sono solo "il tuo feed ha N nuovi articoli oggi" (digest). Niente push ancora.

### Endpoint nuovi (v1.1)

- `GET /yf_auth/google/authorize`
- `GET /yf_auth/google/callback`
- `POST /yf_auth/forgot-password`
- `POST /yf_auth/reset-password`
- `GET /yf_me/devices`
- `DELETE /yf_me/devices/{id}`
- `GET /yf_search`
- `GET /yf_search/suggest`
- `GET /yf_search/sources`
- `GET /yf_me/notifications`
- `PATCH /yf_me/notifications/{id}/read`

**+11 endpoint → 38 totali**

### Tabelle nuove

- `password_reset_tokens`
- `notifications`

### DoD v1.1

- [ ] Login Google flow end-to-end con almeno 2 account test
- [ ] Search restituisce risultati pertinenti su corpus di almeno 10K articoli (relevance review manuale)
- [ ] Centro notifiche mostra digest giornaliero per utenti con almeno una fonte

---

## v1.2 — Engagement

### Aggiunte funzionali

- **Alert personalizzati**: stringhe / brand / persone. Ogni nuovo articolo ingerito viene matchato contro gli alert attivi.
- **Web push (VAPID)**: subscription da browser, delivery via `pywebpush`, rispetto delle preferenze utente
- **NER spaCy** sostituisce/raffina i risultati regexp dello step di estrazione
- **Wikidata enrichment**: topic curati arricchiti automaticamente da Wikidata via job RQ
- **LLM fallback**: Claude Haiku per articoli ancora senza topic dopo dictionary+regexp+NER
- **Admin dashboard**: vista (anche basic) per moderare entità candidate, promuoverle a topic, mergere alias
- **Cron retention sweep**: drop articoli >12 mesi senza engagement. Diventa rilevante solo dopo 12 mesi di vita del prodotto.

### Endpoint nuovi (v1.2)

Alert (5):
- `GET /yf_me/alerts`
- `POST /yf_me/alerts`
- `PATCH /yf_me/alerts/{id}`
- `DELETE /yf_me/alerts/{id}`
- `GET /yf_me/alerts/{id}/matches`

Web push (3):
- `GET /yf_push/vapid-key`
- `POST /yf_me/push/subscriptions`
- `DELETE /yf_me/push/subscriptions/{id}`

**+8 endpoint → 46 totali (l'intera tabella di [BACKEND.md](BACKEND.md))**

### Tabelle nuove

- `alerts`, `alert_matches`
- `push_subscriptions`

### Worker nuovi

- `alerts_matcher`
- `enrich_wikidata`
- `retention_sweep`

### DoD v1.2

- [ ] Alert testato su almeno 20 utenti, latenza match < 60s dall'ingestion
- [ ] Push delivery testato su Chrome + Firefox desktop e Chrome Android
- [ ] NER aumenta la copertura `article_topics` di almeno il 30% rispetto a regexp+dict
- [ ] Wikidata enrichment popola description/image/aliases per il 90% dei topic curati con confidenza alta

---

## v2.0 — Personalizzazione + estensioni

### Aggiunte funzionali

- **Recommendation engine**:
  - Profilo utente come vettore di topic letti (recency-weighted)
  - Espansione via `topic_relations` per scoperta di topic correlati
  - Ranking articoli combinato (match topic + freshness + source affinity + co-occorrenza)
  - Cold start per nuovo utente (popolarità globale + topic delle categorie create)
  - Tabelle nuove: `user_topic_affinity`, `user_source_affinity`
- **Topic correlati esposti in UI**: nella pagina `/{username}/topic/{name}`, sidebar con topic correlati alimentata da `topic_relations`
- **Statistiche di engagement esposte**: dashboard utente con i propri trend di lettura (privacy: solo l'utente vede i propri dati)
- **Mobile Android app**: app nativa con auth via Bearer token sulla stessa sessione web. Featurmap simile alla web app.
- **API pubbliche per integrazioni**: opzionale, esposizione di un sottoinsieme delle proprie API a key esterne

### Tabelle nuove

- `user_topic_affinity`, `user_source_affinity`
- `topic_relations` (riempita dal job batch già predisposto in v1.2)

### DoD v2.0

- [ ] Reco offline metrics: nDCG@10 misurato su set di valutazione manuale > soglia X (TBD)
- [ ] Mobile app pubblicata su Play Store
- [ ] Topic correlati testati su almeno 50 topic e validati a campione

---

## Cosa non è in roadmap (per ora)

- **Subscription / monetization**: piani free/paid, billing — da decidere quando capiremo retention reale
- **Performance budget / SLO formali**: misurazioni continue ma niente impegni contrattuali
- **iOS app**: subordinata al successo Android
- **Federazione / ActivityPub**: interessante per un aggregatore RSS, ma fuori scope iniziale

---

## Effort indicativo

Ordine di grandezza, sviluppatore singolo full-time. Da rifinire a fronte dello stack di esperienza:

| Release | Effort indicativo |
|---|---|
| v1.0 | 8-12 settimane |
| v1.1 | 3-4 settimane |
| v1.2 | 4-6 settimane |
| v2.0 | 6-10 settimane (recommendation richiede iterazioni) |

I numeri non includono devops/hosting/monitoring iniziale, che da soli pesano 1-2 settimane.

---

## Aggiornamenti

Quando una decisione di scope cambia, aggiorna **questo file** prima di toccare i documenti tecnici. È la fonte di verità sulla pianificazione.
