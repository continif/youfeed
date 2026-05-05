# Database

## Motori

**PostgreSQL** per tutti i dati transazionali e relazionali (utenti, fonti, categorie, alert, topic, knowledge graph, activity log).

**Manticore** come **content store + search index** per gli articoli: titolo, descrizione e contenuto vivono qui — non in Postgres. Le query full-text e le visualizzazioni timeline/articolo combinano sempre i due sistemi.

**Redis** per: cache sessioni (lookup veloce su `auth_sessions`), code RQ, rate limiting, cache hot path (topic correlati, dashboard counters).

**MaxMind MMDB** (GeoLite2-ASN + GeoLite2-Country) come file su disco, caricati in memoria dal backend, refresh schedulato.

## Divisione dei contenuti tra Postgres e Manticore

```
+------------------------------+    +------------------------------+
|         POSTGRES             |    |         MANTICORE            |
|------------------------------|    |------------------------------|
| articles                     |    | articles_rt (RT index)       |
|   id, source_id, kind        |    |   id  (= articles.id in PG)  |
|   url_canonical, url_hash    |    |   source_id, source_domain   |
|   image_url, author          |    |   title (analyzed)           |
|   published_at, updated_at   |    |   description (analyzed)     |
|   ingested_at                |    |   content_html (stored)      |
|   processing_status          |    |   content_text (analyzed)    |
|   origin_taxonomy            |    |   topic_slugs[]              |
|   raw_meta_lite (jsonb)      |    |   topic_ids[]                |
|                              |    |   published_at, kind         |
+------------------------------+    +------------------------------+
       ↑ ID condiviso (1:1) ↑
```

Postgres è **autoritativo** per la presenza dell'articolo (riga in `articles`). Manticore è autoritativo per il **contenuto testuale**.

### Pattern di sync
- **Insert**: 1) PG insert → ottieni `id`. 2) RQ accoda `replace_manticore(id, payload)`. Job idempotente.
- **Update content**: stessa replace su Manticore + UPDATE metadata su PG.
- **Update topics post-extraction**: REPLACE Manticore per aggiornare `topic_slugs[]`/`topic_ids[]` (Manticore RT non supporta partial update, serve replace completo).
- **Delete**: DELETE Manticore + DELETE PG, in quest'ordine.
- **Riconciliazione**: job notturno trova `articles` in PG senza riga Manticore (o viceversa) e ripara.
- **Fallimento Manticore**: l'articolo resta `processing_status='new'`; retry esponenziale fino a `failed`.

### Pattern di lettura
- **Timeline / pagina pubblica**: PG per filtro+sort (categoria, user_sources, published_at DESC), poi `SELECT id, title, description, image_url ... FROM articles_rt WHERE id IN (...)` su Manticore.
- **Search**: Manticore in primis (full-text), poi opzionalmente JOIN su PG per arricchire (es. `category_id` per filtro utente loggato).
- **Singolo articolo**: PG per metadata, Manticore per content.
- **RSS export**: stesso pattern timeline (lookup batch su Manticore).

## Schema Postgres

### Utenti e auth

```
users
  id              bigserial PK
  username        citext UNIQUE NOT NULL  -- validato contro reserved_usernames
  email           citext UNIQUE NOT NULL
  password_hash   text                    -- nullable se solo Google
  google_sub      text UNIQUE             -- nullable
  email_verified  bool DEFAULT false
  onboarding_completed_at timestamptz     -- tour guidato completato/skippato
  created_at      timestamptz
  updated_at      timestamptz

auth_sessions
  id              uuid PK                 -- usato come token (cookie o bearer)
  user_id         bigint FK → users
  fingerprint     text                    -- da FingerprintJS
  client          text                    -- 'web' | 'android' | ...
  ip              inet
  country         text                    -- da MaxMind
  asn             int                     -- da MaxMind
  ua              text
  created_at      timestamptz
  last_seen_at    timestamptz
  revoked_at      timestamptz

email_verification_tokens
  token           text PK
  user_id         bigint FK
  expires_at      timestamptz

password_reset_tokens
  token           text PK
  user_id         bigint FK
  expires_at      timestamptz

reserved_usernames                        -- seed da Claude/reserved-words.txt
  word            citext PK
  reason          text                    -- 'system' | 'profanity' | 'brand' | 'slur'
```

### Fonti e categorie

```
sources                                   -- fonte normalizzata, condivisa tra utenti
  id              bigserial PK
  kind            text NOT NULL           -- 'rss' | 'wordpress_api' | 'invalid'
  url_site        text
  url_feed        text                    -- per kind='rss'
  wp_api_root     text                    -- per kind='wordpress_api'
  title           text
  favicon_url     text
  status          text                    -- 'pending' | 'active' | 'broken' | 'paused'
  poll_interval   int                     -- secondi (adattivo)
  last_fetched_at timestamptz
  last_success_at timestamptz
  consecutive_failures int DEFAULT 0
  etag            text
  last_modified   text
  qualified_at    timestamptz
  discovery_meta  jsonb                   -- diagnostica fase elaborazione URL
  created_at      timestamptz
  updated_at      timestamptz
  UNIQUE (url_feed)
  UNIQUE (wp_api_root)

featured_sources                          -- fonti popolari pre-curate (gallery onboarding)
  source_id       bigint PK FK → sources
  category_hint   text                    -- es. 'Cronaca', 'Sport' per filtro UI
  display_name    text                    -- override del titolo della fonte
  description     text                    -- breve descrizione editoriale
  position        int                     -- ordine visualizzazione
  featured_until  timestamptz             -- nullable per "sempre"

user_sources                              -- relazione utente↔fonte (1:N con categoria)
  id              bigserial PK
  user_id         bigint FK
  source_id       bigint FK
  category_id     bigint FK → categories
  custom_title    text                    -- override per l'utente
  added_at        timestamptz
  UNIQUE (user_id, source_id)

categories                                -- alberatura per utente
  id              bigserial PK
  user_id         bigint FK
  parent_id       bigint FK → categories  -- NULL = root
  name            text
  slug            text                    -- usato in /{username}/{slug}
  position        int
  color           text                    -- hex "#rrggbb", per identificazione visiva (UI)
  is_public       bool DEFAULT true
  UNIQUE (user_id, parent_id, slug)
```

### Articoli (metadata in PG, contenuto in Manticore)

```
articles
  id              bigserial PK
  source_id       bigint FK NOT NULL
  external_id     text                    -- guid RSS o WP post id
  kind            text                    -- snapshot di sources.kind
  url_canonical   text NOT NULL
  url_hash        text NOT NULL           -- sha256(url_canonical)
  image_url       text                    -- URL originale (esterno) sempre conservato
  image_local_path text                   -- path interno "ab/cd/abcdef..." (no suffix variant)
  image_width     int                     -- dimensioni originali (per layout masonry no-CLS)
  image_height    int
  image_status    text DEFAULT 'pending'  -- 'pending' | 'processed' | 'failed' | 'skipped'
  image_processed_at timestamptz
  author          text
  published_at    timestamptz NOT NULL
  updated_at      timestamptz
  ingested_at     timestamptz NOT NULL DEFAULT now()
  processing_status text DEFAULT 'new'    -- 'new' | 'extracted' | 'indexed' | 'failed'
  processing_error text
  origin_taxonomy text[]                  -- categorie/tag dichiarate dalla fonte
  internal_links  jsonb                   -- [{url, anchor, internal: bool}, ...] estratti dal content
  read_count      int DEFAULT 0           -- aggiornato in batch dall'activity_log worker
  open_count      int DEFAULT 0           -- aperture (impression aggregate)
  last_read_at    timestamptz             -- ultima lettura registrata
  raw_meta_lite   jsonb                   -- raw_meta SENZA i campi testuali pesanti
  UNIQUE (url_hash)
```

**Note importanti**:
- `title`, `description`, `content_html`, `content_text` non sono in Postgres. Vivono **solo in Manticore**.
- `raw_meta_lite` esclude i campi body per non duplicare. Tiene solo: media metadata, autore, taxonomy IDs, fonte payload originale per debug strutturale.
- L'`id` di Postgres è la chiave primaria del documento Manticore (1:1).

### Knowledge graph

Vedi [KNOWLEDGE-GRAPH.md](KNOWLEDGE-GRAPH.md) per il modello concettuale.

```
topics                                    -- entità canoniche curate
  id              bigserial PK
  type            text                    -- 'brand' | 'person' | 'subject'
  slug            text UNIQUE
  display_name    text
  aliases         text[]                  -- forme alternative per dizionario
  description     text
  external_refs   jsonb                   -- {wikidata: "Q123", ...}
  is_curated      bool DEFAULT false
  created_at      timestamptz

entities                                  -- entità raw da NER, possibilmente non risolte
  id              bigserial PK
  surface_form    text
  normalized      text                    -- lowercase, no accenti
  ner_type        text                    -- 'PER' | 'ORG' | 'LOC' | 'MISC' | 'REGEX_PER' | 'REGEX_BRAND'
  topic_id        bigint FK → topics      -- nullable
  occurrence_count int DEFAULT 0
  first_seen_at   timestamptz
  last_seen_at    timestamptz
  ignored         bool DEFAULT false
  UNIQUE (normalized, ner_type)

article_topics                            -- arco articolo→topic
  article_id      bigint FK
  topic_id        bigint FK
  score           float
  source          text                    -- 'dict' | 'ner' | 'taxonomy' | 'llm'
  position        text                    -- 'title' | 'body' | 'both'
  PK (article_id, topic_id)

article_entities                          -- arco articolo→entità raw
  article_id      bigint FK
  entity_id       bigint FK
  count           int DEFAULT 1
  in_title        bool DEFAULT false
  PK (article_id, entity_id)

topic_relations                           -- co-occorrenza tra topic
  topic_a_id      bigint FK               -- vincolo: topic_a < topic_b
  topic_b_id      bigint FK
  type            text                    -- 'co_occurs' (per ora solo questo)
  weight          float
  cooccurrence    int
  last_updated    timestamptz
  PK (topic_a_id, topic_b_id, type)
```

### Alert e notifiche

```
alerts
  id              bigserial PK
  user_id         bigint FK
  type            text                    -- 'string' | 'brand' | 'person'
  value           text                    -- stringa o topic.slug
  channels        text[]                  -- ['push', 'email']
  active          bool DEFAULT true
  created_at      timestamptz

alert_matches
  id              bigserial PK
  alert_id        bigint FK
  article_id      bigint FK
  matched_at      timestamptz
  notified        bool DEFAULT false
  UNIQUE (alert_id, article_id)

push_subscriptions
  id              bigserial PK
  user_id         bigint FK
  endpoint        text UNIQUE
  p256dh          text
  auth            text
  user_agent      text
  created_at      timestamptz

notifications                             -- centro notifiche in-app
  id              bigserial PK
  user_id         bigint FK
  alert_match_id  bigint FK               -- nullable
  title           text
  body            text
  url             text
  read_at         timestamptz
  created_at      timestamptz
```

### Activity log

Tabella ad alto volume, **partizionata per giorno** con range partitioning nativo Postgres. Manutenzione con job RQ schedulato (creazione partizioni future, drop partizioni oltre retention).

```
activity_log (PARTITIONED BY RANGE (ts))
  id              bigserial
  user_id         bigint                  -- nullable (utenti anonimi)
  session_id      uuid                    -- nullable
  fingerprint     text                    -- nullable
  event_type      text                    -- 'http_request' | 'impression' | 'click' | 'dwell' | 'scroll' | 'search'
  route           text
  method          text
  target_type     text                    -- 'article' | 'source' | 'category' | 'topic' | 'user'
  target_id       text
  metadata        jsonb
  ip              inet
  country         text
  asn             int
  ua              text
  status          int
  latency_ms      int
  ts              timestamptz NOT NULL
  PRIMARY KEY (id, ts)
```

Partizioni `activity_log_YYYY_MM_DD`. Worker RQ gestisce: pre-creazione partizioni dei prossimi 7 giorni, drop di quelle oltre retention (TBD), batch insert da Redis per smorzare il throughput delle scritture.

## Schema Manticore

Un solo RT index principale per gli articoli. La definizione esatta sarà nel sorgente, qui la struttura logica:

```
articles_rt (RT index)
  id               bigint              -- = articles.id in Postgres
  source_id        int                 -- per filtro per fonte
  source_domain    string              -- per facet
  title            text indexed        -- search e display
  description      text indexed        -- search e display
  content_html     string stored       -- non indicizzato, solo restituito
  content_text     text indexed        -- corpo testuale per full-text
  topic_slugs      multi (string)      -- per filtro/facet topic
  topic_ids        multi (int)         -- per JOIN logico con PG
  published_at     timestamp           -- ordinamento cronologico
  kind             string              -- 'rss' | 'wordpress_api'
```

Configurazione attesa:
- **Morphology v1.0**: `libstemmer_it` (Snowball Italian stemmer). Manticore non ha un lemmatizer dictionary-based per l'italiano — i lemmatizer ufficiali coprono solo EN/RU/UK/DE.
- **Wordforms**: file custom `italian_wordforms.txt` con mappature manuali per le irregolarità più frequenti che lo stemmer rovina (es. `andato > andare`, `vado > andare`, `eravamo > essere`). Espandibile nel tempo come `reserved-words.txt`.
- Stopwords IT (file italian_stopwords.txt)
- Min word length 2
- HTML pulito **prima** di Manticore: il `content_text` viene prodotto in fase di ingestion (vedi [INGESTION.md](INGESTION.md)). Manticore riceve testo già pronto, niente `html_strip` lato indice.

### Limite morfologico per l'italiano e upgrade path

Manticore non offre lemmatizer dizionario-based per l'italiano. Lo stemmer Snowball funziona ma ha limiti noti:
- "andato"/"andiamo"/"vado" → stem distinti (lemmatizer ideale → `andare`)
- "amico"/"amica"/"amiche" → over/under-stem
- "città" → talvolta perde l'accento

**Strategia per v1.0**: `libstemmer_it` + wordforms file per le irregolarità top-100 verbi italiani. Sufficiente per una qualità di ricerca decente al lancio.

**Upgrade path da v1.2** (quando arriva spaCy NER): sfruttiamo lo stesso modello `it_core_news_lg` per **pre-lemmatizzare** `content_text` in fase di ingestion. Manticore riceve testo già lemmatizzato e applica solo `libstemmer_it` come ulteriore normalizzazione (o `morphology=none`). Costo: ~30-50ms extra per articolo nel worker `extractor`, già in pipeline.

Vantaggio: qualità di ricerca da lemmatizer reale senza dipendere da features Manticore mancanti per l'italiano.

Backup: snapshot Manticore notturno + log delta. Manticore supporta `BACKUP` SQL command nativo.

## Indici Postgres principali (da rifinire)

- `users(username)`, `users(email)`, `users(google_sub)`
- `auth_sessions(user_id)`, `auth_sessions(last_seen_at) WHERE revoked_at IS NULL`
- `articles(source_id, published_at DESC)`, `articles(published_at DESC)`, `articles(processing_status) WHERE processing_status != 'indexed'`
- `user_sources(user_id, category_id)`
- `categories(user_id, parent_id, position)`
- `article_topics(topic_id, article_id)`
- `article_entities(entity_id)`
- `topic_relations(topic_a_id, weight DESC)`, `topic_relations(topic_b_id, weight DESC)`
- `alert_matches(alert_id, matched_at DESC)`, `alert_matches(article_id)`
- `activity_log` per partizione: `(user_id, ts DESC)`, `(target_type, target_id)`
- `entities(normalized, ner_type)`, `entities(occurrence_count DESC) WHERE topic_id IS NULL AND NOT ignored`

## Image storage (locale)

Le immagini degli articoli sono **scaricate e conservate localmente** in due varianti, mantenendo l'URL originale come fallback.

### Formato e dimensioni
- **Formato**: WebP qualità 80 (compromesso dimensione/qualità, ottimo supporto browser)
- **Mobile**: width 370px, height proporzionale al rapporto originale
- **Desktop**: max width 1200px (no upscale se l'originale è più piccolo), height proporzionale

### Path su filesystem
Sharding a 2 livelli per evitare directory enormi (~65k subdir). Hash di partenza: `sha256(image_url)`.

```
/var/lib/youfeed/images/
  ab/cd/abcdef0123...{m,d}.webp
  └─ shard1
     └─ shard2
        └─ {hash}_m.webp     # mobile, 370px
        └─ {hash}_d.webp     # desktop, max 1200px
```

`articles.image_local_path` contiene la base `ab/cd/abcdef0123...`. I path completi vengono ricomposti dall'app aggiungendo `_m.webp` o `_d.webp`.

### Servizio
Apache serve `/images/*` direttamente dal filesystem (no FastAPI sul percorso caldo):
```
Alias /images /var/lib/youfeed/images
<Directory /var/lib/youfeed/images>
  Require all granted
  AddType image/webp .webp
  Header set Cache-Control "public, max-age=31536000, immutable"
</Directory>
```

Cloudflare cachea aggressivamente con questi header → edge cache effettivo, byte serviti dal nostro origin solo al primo richiamo per regione.

### Stati `image_status`
- `pending` — articolo appena salvato, processing da fare
- `processed` — entrambe le varianti su disco, `image_local_path` valorizzato
- `failed` — fetch o resize falliti dopo retry; frontend usa `image_url` originale come fallback
- `skipped` — nessuna immagine disponibile, immagine troppo piccola (< 200px wide), o formato non supportato

### Retention immagini
La sweep di retention articoli (engagement-based, vedi sotto) deve anche **eliminare i file locali** delle immagini degli articoli droppati.

## Retention basata su engagement

Politica: **non un cutoff temporale piatto**, ma una sweep che preserva gli articoli letti e droppa solo quelli mai consultati.

```
DROP da Postgres + Manticore se:
  ingested_at < now() - interval '12 months'
  AND read_count = 0
  AND open_count = 0
  AND NOT EXISTS (alert_match per questo articolo)
```

Articoli con almeno una lettura/apertura restano indefinitamente — alimentano:
- la pagina pubblica `/{username}/...` (un articolo letto da qualcuno mantiene valore)
- le statistiche di engagement per la personalizzazione (recency-weighted)
- il knowledge graph (le co-occorrenze tra topic basate su articoli letti pesano di più)

`read_count`, `open_count`, `last_read_at` sono **aggregati**, popolati dal worker che consuma `activity_log`. Vantaggio: la sweep di retention non scansiona `activity_log` (che ha retention molto più breve), basta interrogare gli aggregati su `articles`.

### Retention `activity_log`
Manteniamo i log granulari per **180 giorni** (drop partizione daily oltre questa soglia). Per la personalizzazione recency-weighted di periodi più lunghi gli aggregati su `articles` e su (futuri) `user_topic_affinity` / `user_source_affinity` sono sufficienti.

## Operatività

**Backup**:
- Postgres: `pg_basebackup` notturno + WAL archiving su storage offsite
- Manticore: `BACKUP` notturno + replay log
- Disaster recovery: ripristino PG dal backup, ripristino Manticore dal backup. Riconciliazione finale.

**Migrazioni**:
- Postgres: Alembic
- Manticore: script versionati nel repo (no tool standard)

**Manutenzione partizioni**:
- Job RQ `manage_partitions` schedulato giornaliero: crea le prossime 7 partizioni di `activity_log`, droppa quelle oltre la retention (vedi "Da definire")

## Stack fissato
- PostgreSQL ✓
- Manticore come content store + search ✓
- Redis ✓
- MaxMind MMDB ✓
- Range partitioning manuale per `activity_log` ✓

## Stack fissato (decisioni recenti)
- Retention articles: engagement-based (drop solo articoli >12 mesi senza letture/aperture/alert match) ✓
- Retention activity_log: 180 giorni con drop partizione daily ✓
- Tokenizer Manticore v1.0: `libstemmer_it` + wordforms IT custom (lemmatizer dizionario-based non disponibile per IT in Manticore). Da v1.2: pre-lemmatizzazione spaCy in ingestion. ✓
- HTML stripping: lato ingestion, Manticore riceve `content_text` pulito ✓
- `internal_links` estratti durante normalizzazione e salvati come jsonb su `articles` ✓

## Da definire
- **Strategia di anonimizzazione** activity_log su cancellazione utente (GDPR right to erasure)
- **`raw_meta_lite`**: lista esatta dei campi che restano (da decidere quando arriva il primo PR sull'ingestion)
- **Schema versioning Manticore**: cambi di campo richiedono REPLACE INTO di tutto. Strategia per migrazioni grandi (rebuild background?)
- **Archive cold storage**: gli articoli droppati dalla retention finiscono nel nulla o in S3-compatibile per riaccesso futuro?
