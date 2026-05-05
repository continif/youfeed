# Ingestion

Il sistema di ingestion è diviso in **due sottosistemi** distinti, con responsabilità e cadenze diverse:

1. **Elaborazione URL** — analizza una URL fornita dall'utente, decide se è ingeribile e in che modo. Eseguito on-demand (sincrono o quasi-sincrono).
2. **Ingestion vera e propria** — recupero ricorrente dei contenuti dalle fonti già qualificate. Eseguito da worker schedulati.

Le due parti condividono solo la tabella `sources` come punto di scambio.

---

## Parte 1 — Elaborazione URL

Punto di ingresso: `POST /yf_sources/discover` con un URL fornito dall'utente.

### Output
La fase produce un record `sources` con uno dei tre stati:

| `sources.kind` | Significato |
|---|---|
| `rss` | URL è un feed RSS/Atom/JSON Feed direttamente, oppure il sito espone uno o più feed |
| `wordpress_api` | Il sito è WordPress con API REST pubblica (`/wp-json/wp/v2/posts`) |
| `invalid` | Nessuno dei due, URL scartato (record creato per evitare retry continui) |

Quando un sito offre **entrambi** WP API e RSS, scegliamo **WP API** (contenuto completo, taxonomy strutturata, autore esteso, immagini in più dimensioni).

### Pipeline di rilevamento

```
URL input
   ↓
Step 1: probe diretto
   GET URL con Accept: application/rss+xml, application/atom+xml, application/feed+json
   ├─ Content-Type feed valido? → kind=rss, url_feed=URL → END
   └─ HTML? → continua
   ↓
Step 2: rilevamento WordPress
   Cerca header HTTP:  Link: <…>; rel="https://api.w.org/"
   Cerca in HTML:      <link rel="https://api.w.org/" href="…">
   Fallback:           probe GET <site>/wp-json/wp/v2/posts?per_page=1
   ├─ Risposta JSON valida con post? → kind=wordpress_api, wp_api_root=… → END
   └─ continua
   ↓
Step 3: ricerca RSS in HTML
   <link rel="alternate" type="application/rss+xml">
   <link rel="alternate" type="application/atom+xml">
   <link rel="alternate" type="application/feed+json">
   Fallback path comuni: /feed, /feed/, /rss, /rss.xml, /atom.xml, /index.xml, /feed.json
   ├─ Almeno un feed valido? → kind=rss, url_feed=… → END
   └─ continua
   ↓
Step 4: nessun risultato
   kind=invalid, motivo registrato in sources.discovery_meta
```

Se ci sono **più candidati feed**, ritorniamo l'elenco al backend con anteprima (titolo + ultimi 3 articoli) e l'utente sceglie. La selezione finalizza il record.

In aggiunta alla preview dei feed, la response include un blocco **Open Graph del sito** (og_title, og_description, og_image, site_name, favicon) — il frontend lo mostra in una card nella `<SourceWizard>` per dare riconoscibilità visiva immediata prima della conferma.

### Validazione finale
Il candidato deve produrre almeno 1 articolo parsabile. Senza questa garanzia, la fonte resta in stato `pending` e non entra nella schedulazione.

### Persistenza
```
sources
  ...
  kind                text       -- 'rss' | 'wordpress_api' | 'invalid'
  url_site            text
  url_feed            text       -- per kind=rss
  wp_api_root         text       -- per kind=wordpress_api, es. https://example.com/wp-json/wp/v2
  discovery_meta      jsonb      -- diagnostica: candidati trovati, headers, errori
  qualified_at        timestamptz
```

---

## Parte 2 — Ingestion vera e propria

Due pipeline parallele che convergono nella stessa fase di salvataggio + estrazione.

```
                         [scheduler tick]
                                ↓
                    ┌─────────────┴─────────────┐
                    │                           │
        kind=wordpress_api               kind=rss
                    │                           │
                    ▼                           ▼
        ┌───────────────────────┐    ┌─────────────────────┐
        │ WordPress API pipeline │    │   RSS pipeline      │
        └───────────────────────┘    └─────────────────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                       NORMALIZZAZIONE
                                  ▼
                        DEDUP + SAVE article
                                  ▼
                ┌────────────────┴────────────────┐
                ▼                                  ▼
       ESTRAZIONE ENTITÀ                    INDEX MANTICORE
       (NER + dizionario)
                ▼
        AGGIORNAMENTO KG
        (vedi KNOWLEDGE-GRAPH.md)
                ▼
            MATCH ALERT
```

### Scheduler
- Tick ogni minuto, seleziona `sources` qualificate dove `last_fetched_at + poll_interval <= now()`
- Accoda job sulla coda corrispondente al `kind`: `fetch_rss` o `fetch_wp`
- **Politeness per host** via lock Redis (max N richieste concorrenti per dominio)
- **Adattivo**: se un feed non cambia per N cicli, raddoppia `poll_interval` (cap 6h); se produce articoli, dimezza (min 5 min)

### Pipeline RSS

1. **Fetch**: `httpx` async con `If-None-Match`/`If-Modified-Since` da `sources.etag`/`last_modified`. Su 304 aggiorna solo `last_fetched_at`.
2. **Parse**: `feedparser` (RSS/Atom) o parser JSON Feed custom.
3. **Estrazione voce**: `link`, `title`, `summary`, `content:encoded`, `published`, `author`, `media:thumbnail`/`enclosure`, `guid`, `category`/`tag`.
4. **Enrichment** *(condizionale)*: se la voce non ha immagine o ha solo titolo, fetch della pagina articolo e estrai con priorità: Open Graph → Twitter Card → JSON-LD `NewsArticle` → `trafilatura`. Rispetta `robots.txt`.
5. → emissione `ArticleCandidate`

### Pipeline WordPress API

1. **Fetch paginato**: `GET {wp_api_root}/posts?per_page=50&page=N&_embed=1&after=<last_published>` finché non si raggiunge una pagina già nota.
2. **Estrazione voce** (campi nativi WP, niente HTML scraping):
   - `id` (WP), `slug`, `link` → URL articolo
   - `title.rendered` → titolo
   - `content.rendered` → contenuto completo
   - `excerpt.rendered` → summary
   - `date_gmt` → published_at (UTC)
   - `modified_gmt` → updated_at
   - `_embedded.author[0].name` → autore
   - `_embedded["wp:featuredmedia"][0].source_url` + `media_details.sizes` → immagine
   - `_embedded["wp:term"][0/1]` → categories e tags WP nativi (utili come hint per la classificazione)
   - `categories[]`, `tags[]` → ID lookup
3. **Enrichment**: tipicamente non necessario, l'API WP fornisce già contenuto completo e immagine.
4. → emissione `ArticleCandidate`

### Punto di convergenza — `ArticleCandidate`

Schema comune (Pydantic) prodotto da entrambe le pipeline:
```
ArticleCandidate
  source_id            int
  external_id          str           # guid RSS oppure wp post id
  url_canonical        str
  url_hash             str           # sha256 di url_canonical
  title                str
  description          str           # excerpt/summary
  content_html         str           # contenuto pulito
  content_text         str           # plain text per NER e Manticore
  image_url            str | None
  author               str | None
  published_at         datetime
  updated_at           datetime | None
  origin_taxonomy      list[str]     # categorie/tag della fonte (hint per KG)
  internal_links       list[dict]    # [{url, anchor, internal: bool}, ...] estratti dal body
  raw_meta             dict          # tutto il payload originale per debug/futuro
```

### Normalizzazione (comune)
- **URL canonicalization**: rimozione `utm_*`, `gclid`, `fbclid`, `mc_*`, `_ga`, `ref`, normalizzazione protocollo/host
- **Date**: tutto in UTC con `dateutil`
- **HTML cleaning**: `bleach` whitelist conservativa per `content_html` (preservato per visualizzazione)
- **Plain text**: `selectolax` produce `content_text` privo di HTML — usato da NER e da Manticore. Manticore non fa più stripping lato indice; riceve testo già pulito.
- **Internal links extraction**: durante la pulizia HTML estraiamo tutti i `<a href>` dal corpo dell'articolo e li salviamo come jsonb su `articles.internal_links`:
  ```
  [
    {"url": "https://...", "anchor": "testo del link", "internal": true|false},
    ...
  ]
  ```
  `internal=true` se l'host del link == host della fonte (link interno al sito sorgente). Usi futuri: knowledge graph (articolo→articolo via citazione), individuazione cross-publishing, segnale di autorevolezza per il ranking.
- **Hash**: `sha256(url_canonical.lower())`

### Persistenza articolo

```
articles
  id                   bigserial
  source_id            bigint FK
  external_id          text          -- chiave nel sistema sorgente
  kind                 text          -- snapshot di sources.kind al momento dell'ingestion
  url_canonical        text
  url_hash             text UNIQUE
  title                text
  description          text
  content_html         text
  content_text         text          -- usato per NER e Manticore
  image_url            text
  author               text
  published_at         timestamptz
  updated_at           timestamptz
  origin_taxonomy      text[]
  ingested_at          timestamptz   -- interno, non da modificare
  processing_status    text          -- 'new' | 'extracted' | 'indexed' | 'failed'
  processing_error     text
  raw_meta             jsonb
  UNIQUE (url_hash)
```

`processing_status` è il campo di stato interno che ci dice a che punto è la pipeline post-save:
- `new` → appena salvato, da processare
- `extracted` → entità estratte, KG aggiornato
- `indexed` → indicizzato in Manticore
- `failed` → errore (con `processing_error`)

ON CONFLICT su `url_hash`: aggiorna `updated_at`, `raw_meta`, `processing_status='new'` per riprocessare se il contenuto è cambiato.

### Estrazione entità (post-save)

Dettagli completi in [KNOWLEDGE-GRAPH.md](KNOWLEDGE-GRAPH.md). Sintesi (con release):

1. **Origin taxonomy** *(v1.0)* — categorie/tag dichiarati dalla fonte (RSS `<category>` o WP `wp:term`) usati come segnale per `topics.aliases`
2. **Dizionario** *(v1.0)* — match esatto con `topics.aliases` su `title` (peso 2) e `content_text` (peso 1)
3. **Regexp heuristics** *(v1.0)* — pattern italiani per persone (Maiuscolo + de/di/della + Maiuscolo) e brand (UPPERCASE 2-7 lettere, CamelCase, trademark ®/™); popola `entities` + `article_entities` per il long-tail non coperto dal dizionario
4. **NER** *(v1.2)* — `spaCy` `it_core_news_lg`, sostituisce/raffina i risultati regexp
5. **LLM fallback** *(v1.2, opzionale)* — Claude Haiku per articoli ancora senza match

L'output popola `article_topics` (M:N articolo↔topic) e alimenta il knowledge graph.

### Image processing (post-save, prima dell'estrazione)

Step parallelo all'estrazione, accodato sulla coda `image_processor`:

1. **Skip** se `image_url` è NULL o non valido → `image_status='skipped'`
2. **Fetch** dell'immagine: `httpx` con timeout 10s, max body 10 MB. Su errore → retry 2 volte, poi `image_status='failed'`
3. **Open** con Pillow. Se non parsabile o `width < 200` → `image_status='skipped'`
4. **Read dimensioni** originali → `articles.image_width`, `image_height` (servono al frontend per layout masonry senza CLS)
5. **Resize**:
   - Mobile: `Lanczos` resize a width=370, height proporzionale
   - Desktop: `Lanczos` resize a max width=1200 (no upscale), height proporzionale
6. **Convert** entrambe a WebP qualità 80
7. **Save** su filesystem con sharding `sha256(image_url)[:2]/[2:4]/{hash}_{m,d}.webp` (vedi [DATABASE.md](DATABASE.md))
8. **UPDATE** `articles.image_local_path` (base senza suffix) e `image_status='processed'`, `image_processed_at=now()`

In caso di `failed` il frontend usa `image_url` originale come fallback (browser fa fetch diretto al sito sorgente).

### Indicizzazione Manticore
- Dopo `processing_status='extracted'`, accoda job `index_manticore`
- Index RT con: `id, source_id, source_domain, title, description, content_text, topic_slugs, published_at, kind`
- Per ricerche utente loggato: filtro `source_id IN (user's user_sources)`

### Match alert
Inalterato rispetto alla versione precedente: dopo `extracted`, valuta gli alert attivi (cache Redis), inserisce in `alert_matches`, accoda push/email.

---

## Architettura worker (RQ)

```
processi (systemd unit per ciascuno):
  url_processor         # 1-2 istanze su coda 'discover' (Parte 1, on-demand)
  scheduler             # 1 istanza
  fetcher_rss           # N istanze su coda 'fetch_rss'
  fetcher_wp            # N istanze su coda 'fetch_wp'
  normalizer            # N istanze su coda 'normalize' (output ArticleCandidate → DB)
  extractor             # K istanze su coda 'extract' (NER, KG update, CPU-bound)
  image_processor       # M istanze su coda 'image_processor' (HTTP+Pillow, IO/CPU)
  indexer               # 1-2 istanze su coda 'index_manticore'
  alerts_matcher        # 1-2 istanze su coda 'alerts_match'
```

In MVP `normalizer + extractor + indexer + alerts_matcher` possono essere un'unica coda `process_article` con un solo worker — separeremo dopo aver misurato.

---

## Tecnologie
- **HTTP**: `httpx` async
- **WP API client**: `httpx` + parser JSON nativo (no client dedicato necessario)
- **Feed parsing**: `feedparser`, parser custom JSON Feed
- **HTML/JSON-LD**: `selectolax`, `extruct` per metadata strutturati
- **Sanitization**: `bleach`
- **Estrazione articolo (fallback enrichment)**: `trafilatura`
- **Image processing**: `Pillow` con encoder WebP (incluso in libwebp/Pillow) + `httpx` per fetch
- **NER**: `spaCy` (`it_core_news_lg` — solo italiano, contenuto YOUFEED IT-only)
- **URL canonicalization**: `w3lib.url` + regole custom
- **LLM**: Anthropic SDK (Haiku) per fallback classificazione
- **Robots**: `urllib.robotparser` con cache Redis

---

## Osservabilità

Per fonte:
- `last_fetched_at`, `last_success_at`, `consecutive_failures`
- Articoli/giorno, % dedup, tempo medio fetch

Globali (Prometheus):
- `ingestion_articles_total{kind, status}`
- `ingestion_fetch_duration_seconds{kind}`
- `extraction_entities_total{type}`
- `kg_relations_total`

Dashboard amministrativa:
- Sources broken / invalid
- Topic candidates da review (entità NER non risolte ricorrenti)
- Volumi ingestion per kind

---

## Volumi attesi
- Scenario early (100 utenti, 20 fonti medie, 10 articoli/fonte/giorno): **20K articoli/giorno** ≈ 7M/anno
- Scenario medio (1000 utenti, 30 fonti, 20 articoli/fonte/giorno): **600K articoli/giorno** ≈ 220M/anno
- WP API tendenzialmente produce articoli con contenuto pieno → record più grandi (~5-50 KB di HTML)
- RSS produce record più piccoli (~1-5 KB)

---

## Storage

Decisione: **PostgreSQL + Manticore come content store**. Il dettaglio dello split è in [DATABASE.md](DATABASE.md). In sintesi per l'ingestion:

- `articles` in Postgres tiene **solo metadata e puntatori** (id, source_id, kind, url_canonical, url_hash, image_url, author, published_at, processing_status, origin_taxonomy, raw_meta_lite)
- `articles_rt` in Manticore tiene **titolo, descrizione, content_html, content_text, topic_slugs/ids** — stesso `id` del record Postgres
- L'ingestion deve scrivere sempre in entrambi: PG insert prima (genera id), poi job RQ `replace_manticore(id, payload)` idempotente
- Job notturno di riconciliazione per individuare disallineamenti
- `activity_log` resta in Postgres con range partitioning daily

Implicazioni operative per l'ingestion:
- Lo step di normalizzazione produce due output: una riga `articles` per PG e un documento per Manticore
- L'aggiornamento topic post-extraction richiede un REPLACE completo del documento Manticore (no partial update sugli RT index)
- In caso di fallimento Manticore, l'articolo resta `processing_status='new'` e viene riprovato

---

## Decisioni fissate
- Sito sia WP API che RSS → sempre WP API (nessun override utente) ✓
- HTML stripping in ingestion, Manticore riceve `content_text` pulito ✓
- `internal_links` estratti in normalizzazione e salvati come jsonb su `articles` ✓
- Retention engagement-based (vedi [DATABASE.md](DATABASE.md)) ✓

## Da definire
- Cosa fare per WP API protetti (auth richiesta) o limitati (`per_page` cap basso)?
- Limite `content_html` (per copyright/storage): troncare a N caratteri?
- Frequenza reindicizzazione completa Manticore
- Allowlist/denylist domini per ingestion
- Quando attivare AVIF in aggiunta/sostituzione di WebP (~25% saving extra, supporto browser ormai >95%)
