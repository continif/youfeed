# Personalizzazione del feed `/me/feed`

Obiettivo: riordinare la timeline dell'utente loggato in funzione di
**cosa legge davvero**, non solo della data di pubblicazione. Articoli
in linea con i suoi interessi salgono in cima; articoli noiosi/non
allineati scendono. Senza diventare una "echo chamber": diversità
mantenuta da un floor di chronological + penalità anti-cluster.

## Scope e non-scope

**In scope (v1)**
- Re-ranking server-side della timeline `/me/feed` per utenti loggati
  con storia di interazione sufficiente.
- Affinity per **topic** (segnale primario) e **source** (secondario).
- Fingerprint per pre-merge dell'attività pre-login.
- Toggle utente "ordina cronologico" come fallback opt-out.

**Out of scope (v1)**
- Collaborative filtering / matrix factorization: no — niente ML batch
  pesante, niente embedding precomputati. Tutto si fa con SQL e Postgres.
- Personalizzazione per anonimi: la timeline pubblica `/{username}` e
  l'RSS export restano chronologici per definizione.
- Push notification ranking: non tocca questo layer, ha il suo router.

## Segnali disponibili

### Dati strutturali (già in DB)
- `article_topics(article_id, topic_id, score, source, position)` —
  arco articolo → topic con peso e provenienza (dict/ner/regex/llm).
- `article_bookmarks(user_id, article_id)` — segnale forte (esplicito).
- `user_sources(user_id, source_id, category_id)` — sottoscrizioni.
- `users.created_at` — età account (peso al cold-start).

### Telemetria (già in DB ma sotto-utilizzata)
[`activity_log`](../backend/app/models/activity.py) partitioned daily:
- `user_id`, `fingerprint`, `session_id`
- `event_type`: oggi quasi solo `http_request`, ma il modello supporta
  `impression`, `click`, `open`, `dwell`, `scroll`, `search`, `share`
- `target_type` + `target_id` (es. `'article'`, `'12345'`) con indice
  `ix_activity_log_target`
- `route` e `metadata` (JSONB) per dettagli

L'endpoint [`POST /yf_track`](../backend/app/routers/track.py) accetta
già impression/click/dwell. Il middleware `ActivityLogMiddleware`
accoda tutto su Redis e un worker drena in batch su Postgres.

**Quello che manca**: il frontend al momento NON emette eventi di
tracking. Il composable [useTrackingConsent](../frontend/src/composables/useTrackingConsent.ts)
ha la plumbing per FingerprintJS e gating sul consenso, ma le pagine
non chiamano `trackEvent(...)`. Vedi "Phase 1" sotto.

### Eventi che intendiamo emettere

Gradiente di intensità: dalla semplice esposizione (impression) al
segnale fortissimo "non mi è bastata l'anteprima, voglio l'articolo
originale completo" (original_open).

| Evento          | Trigger                                                      | Peso |
|-----------------|--------------------------------------------------------------|------|
| `impression`    | card articolo entra in viewport ≥ 500ms                      | +0.1 |
| `preview_open`  | click su card → `/me/article/N` (anteprima nell'app)         | +1.0 |
| `dwell_5s`      | 5s sulla detail page                                         | +0.3 |
| `dwell_15s`     | 15s sulla detail page (sostituisce dwell_5s, non somma)      | +0.8 |
| `dwell_60s`     | 60s sulla detail (sostituisce dwell_15s)                     | +1.5 |
| `original_open` | click su "Apri l'articolo originale" → link esterno          | +2.5 |
| `related_click` | click su una "notizia correlata" dalla detail page           | +1.0 + topic-overlap bonus |
| `bookmark`      | salva tra i preferiti                                        | +3.0 |
| `share`         | invio link a terzi                                           | +2.0 |
| `unsource`      | toglie la fonte dal feed                                     | −2.0 source |

**Razionale del gradiente preview → original**:

L'anteprima `/me/article/N` mostra titolo + immagine + descrizione + le
prime ~500 char. È un costo basso (1 click dal feed). Aprirla = "mi
incuriosisce". Cliccare "Apri originale" invece costa di più (nuova
tab, esce dal sito, deve fidarsi del dominio): chi lo fa sta dicendo
"questo argomento mi interessa abbastanza da volerlo leggere TUTTO".
Quindi `original_open` pesa 2.5× di `preview_open`. Insieme al dwell,
sono i due segnali più affidabili.

**Bonus topic-overlap su `related_click`**:

Quando l'utente è su `/me/article/A` e clicca su "B" tra le correlate,
sta dicendo "voglio altri articoli COME questo". I topic che A e B
condividono sono il motivo per cui sono state proposte come correlate
(vedi `articles_service.related_articles` con coverage TF-IDF).
Quei topic ricevono un peso extra di **+1.5** ciascuno nell'affinity
del target, oltre al peso base `preview_open` di B.

Es. A = "OpenAI lancia GPT-5", topic = {AI, OpenAI, ChatGPT, USA}.
B = "Microsoft compra Anthropic" (correlata), topic = {AI, Anthropic,
ChatGPT, USA, Microsoft}. Shared = {AI, ChatGPT, USA}. Su un click
related:
- B contribuisce +1.0 ai 5 suoi topic (peso base preview_open)
- Più +1.5 a {AI, ChatGPT, USA} (bonus overlap)
- Risultato: {AI: 2.5, ChatGPT: 2.5, USA: 2.5, Anthropic: 1.0, Microsoft: 1.0}

Da emettere come `event_type='click'` con
`metadata = {"source": "related", "from_article": A_id, "shared_topics": [t1, t2, t3]}`.
La rollup query estrae lo shared_topics dal metadata e applica il bonus.

**Negativi impliciti** (da analizzare in Phase 5, non in v1):
- Articolo impression ≥ 3 volte, mai aperto → leggera penalità sul
  topic dominante.
- preview_open chiuso entro <3s, no scroll → bounce; nessun peso (no
  contributo, non penalità).

## Architettura

### Segnali espliciti — bypass parziale del decay

Ci sono due signal che l'utente ci ha dato **esplicitamente**, non
inferiti da comportamento: i bookmark (articoli salvati) e gli alert
(topic per cui vuole notifiche). Hanno regole diverse dai signal
comportamentali:

**Bookmark = "voglio rileggerlo"**

Un bookmark vive nel DB (`article_bookmarks`) ed è una dichiarazione
forte: "questo mi interessa abbastanza da rivolerlo ritrovare". Va
trattato in due punti dello scoring:

1. **Evento `bookmark` (+3.0)** — come oggi, contribuisce come evento e
   decade con half-life. Misura "ti è piaciuto ALLORA".
2. **Contributo permanente** — separatamente, ogni bookmark attivo
   aggiunge **+2.0 a ciascun topic dell'articolo salvato**, con
   half-life 90g (molto lenta), aggiornato direttamente da
   `article_bookmarks` JOIN `article_topics`. Misura "ti interessa
   ANCORA". Se l'utente toglie il bookmark, il contributo sparisce.

**Alert = "ping me whenever this topic appears"**

Le `alert_topics(alert_id, topic_id)` sono il segnale più esplicito
possibile: l'utente ha PUNTUALMENTE dichiarato "mi interessa il topic X".
Sarebbe assurdo non darle un peso massimo nel ranker.

- Ogni topic in `alert_topics` (via `alerts.user_id`) ottiene un
  **boost fisso di +5.0** sull'affinity di quell'utente per quel topic.
- **NESSUN decay**: finché l'alert esiste, l'affinity resta alta.
- Se l'utente cancella l'alert, il boost sparisce alla prossima rollup.

Esempio concreto: utente con alert su `{OpenAI, AI}` e nessun click
in 2 settimane. Senza questi signal, l'affinity decadrebbe a ~zero
(half-life 30g, ma 14g di silenzio bastano a smorzare). Col boost
fisso da alert, `user_topic_affinity` ha `OpenAI=5.0, AI=5.0` come
floor → questi topic continuano a salire in cima al feed.

**Tabella riassuntiva delle sorgenti di score**:

| Sorgente            | Decay                    | Magnitudo tipica |
|---------------------|--------------------------|------------------|
| Eventi lettura      | Half-life per topic.type | 0.1..3.0/evento  |
| Bookmark (evento)   | Half-life come sopra     | +3.0             |
| Bookmark (esistenza)| Half-life 90g sui topic  | +2.0/bookmark    |
| Alert su topic      | Nessuno (finché esiste)  | **+5.0 fisso**   |
| Sources sottoscritte (Phase 4 v2) | TBD        | TBD              |

### Decay e "scadenza" delle preferenze

> *"Quello che mi piace leggere oggi tra un mese potrebbe non
> interessarmi più."* — esatto, e per gestirlo abbiamo tre layer:

**Layer 1 — Half-life sul peso evento** (sempre attivo)

Ogni evento contribuisce all'affinity moltiplicato per:

```
weight_decay = exp(-days_since_event / HALF_LIFE)
```

Dopo `HALF_LIFE` giorni vale 1/e ≈ 37%. Dopo 2× → 14%, dopo 3× → 5%.

L'half-life **non è uniforme**: dipende dal `topic.type`. Interessi
"strutturali" (un brand, un team sportivo, un argomento ricorrente)
durano nel tempo. Interessi "transient" (un evento specifico, una
breaking news) decadono velocemente:

| topic.type      | HALF_LIFE | Razionale                                         |
|-----------------|-----------|---------------------------------------------------|
| `subject`       | 30g       | "calcio", "tech", "politica" — interessi stabili  |
| `brand`         | 30g       | Apple, FIAT, Esselunga — preferenze durature      |
| `company`       | 30g       | OpenAI, Stellantis — relazione professionale      |
| `person`        | 30g       | Personaggio pubblico che segui                    |
| `location`      | 30g       | Città/regione (Roma, Milano)                      |
| `model`         | 15g       | iPhone 17, Tesla Model Y — interesse acquisto     |
| `software`      | 15g       | App/SaaS — finestra decisionale media             |
| `hardware`      | 15g       | Idem                                              |
| `work`          | 15g       | Libri, film: ne parlerai per qualche settimana    |
| `event`         | 5g        | "Sciopero ATM 14 maggio", "Sanremo 2026" — passa  |

**Layer 2 — Hard cutoff sull'attività considerata** (finestra mobile)

La rollup query considera SOLO gli eventi degli ultimi **90 giorni**.
Oltre, l'evento sparisce dal calcolo. Anche se l'evento ha già pochissimo
peso (90g con half-life 30g ≈ 12%), non rientra nemmeno nello scan SQL
→ query più veloce.

90g è abbastanza per coprire stagionalità medie (un evento ricorrente
mensile o bimestrale resta visibile) ma elimina la coda di rumore.

**Layer 3 — Pruning della tabella affinity**

Cron giornaliero che cancella:

```sql
DELETE FROM user_topic_affinity
WHERE last_seen < now() - INTERVAL '180 days'
   OR score < 0.05;
```

Tiene la tabella snella. Se un topic risale a oltre 6 mesi fa, è
definitivamente "uscito dal radar"; se lo score è <5% del top dell'utente,
non muoverà mai il ranker → inutile tenerlo.

**Interazione tra i layer**:

```
day 0:    user clicca un articolo su "Sanremo 2026" (type=event)
day 10:   weight residuo = exp(-10/5) = 13% → quasi nullo
day 30:   rollup non lo vede nemmeno più (sotto noise threshold)
day 180:  prune cancella la riga residua
```

Vs. interesse stabile:

```
day 0:    user clicca articolo su Inter (type=brand, HALF_LIFE 30g)
day 30:   weight residuo = 37%
day 60:   weight residuo = 14%   (ma se nel frattempo clicca altri
          articoli Inter, il peso si rinnova)
```

Effetto netto: il sistema "ricorda" le passioni a lungo termine
finché vengono nutrite, e dimentica rapidamente le curiosità di passaggio.

### Layer offline — affinity rollup

Tabella materializzata, aggiornata via cron 2× al giorno:

```sql
CREATE TABLE user_topic_affinity (
    user_id   BIGINT NOT NULL,
    topic_id  BIGINT NOT NULL,
    score     REAL   NOT NULL,    -- 0..1 normalizzato
    last_seen TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, topic_id)
);
CREATE INDEX ix_uta_user_score ON user_topic_affinity(user_id, score DESC);

CREATE TABLE user_source_affinity (
    user_id   BIGINT NOT NULL,
    source_id BIGINT NOT NULL,
    score     REAL   NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, source_id)
);
```

Computazione (pseudo-SQL, semplificato):

```sql
-- Step 1: peso per evento (pesi da tabella nella sezione "Eventi")
WITH event_weights AS (
    SELECT
        al.user_id,
        (al.target_id)::bigint AS article_id,
        al.ts,
        CASE al.event_type
            WHEN 'impression'    THEN 0.1
            WHEN 'preview_open'  THEN 1.0
            WHEN 'dwell_5s'      THEN 0.3
            WHEN 'dwell_15s'     THEN 0.8
            WHEN 'dwell_60s'     THEN 1.5
            WHEN 'original_open' THEN 2.5
            WHEN 'related_click' THEN 1.0
            WHEN 'bookmark'      THEN 3.0
            WHEN 'share'         THEN 2.0
            ELSE 0
        END AS base_weight,
        al.metadata->'shared_topics' AS shared_topics  -- per related_click
    FROM activity_log al
    WHERE al.ts >= now() - INTERVAL '90 days'           -- Layer 2: hard cutoff
      AND al.target_type = 'article'
      AND al.user_id IS NOT NULL
),
-- Step 2: half-life per-topic-type
weighted AS (
    SELECT
        ew.user_id,
        at.topic_id,
        t.type AS topic_type,
        ew.base_weight
        * EXP(-EXTRACT(EPOCH FROM now() - ew.ts) / (half_life_seconds(t.type)))
        -- bonus per overlap se related_click e topic è nello shared_topics
        * CASE
            WHEN ew.shared_topics ? at.topic_id::text THEN 2.5
            ELSE 1.0
          END AS w
    FROM event_weights ew
    JOIN article_topics at ON at.article_id = ew.article_id
    JOIN topics t ON t.id = at.topic_id
)
-- Step 3a: contributi da bookmark esistenti (separati dagli eventi
-- per applicare half-life 90g invece di quello per topic.type)
explicit_bookmark AS (
    SELECT
        b.user_id,
        at.topic_id,
        SUM(
            2.0 * EXP(-EXTRACT(EPOCH FROM now() - b.created_at) / (90 * 86400))
        ) AS w,
        MAX(b.created_at) AS last_seen
    FROM article_bookmarks b
    JOIN article_topics at ON at.article_id = b.article_id
    GROUP BY b.user_id, at.topic_id
),
-- Step 3b: boost fisso da alert (no decay finché l'alert esiste)
explicit_alert AS (
    SELECT
        a.user_id,
        at.topic_id,
        5.0 AS w,
        now() AS last_seen
    FROM alerts a
    JOIN alert_topics at ON at.alert_id = a.id
),
-- Step 3c: contributi da eventi (CTE "weighted" sopra)
event_contrib AS (
    SELECT user_id, topic_id, SUM(w) AS w, MAX(ts) AS last_seen
    FROM weighted
    GROUP BY user_id, topic_id
),
-- Step 4: UNION dei tre canali, somma per (user, topic)
combined AS (
    SELECT * FROM event_contrib
    UNION ALL
    SELECT * FROM explicit_bookmark
    UNION ALL
    SELECT * FROM explicit_alert
)
INSERT INTO user_topic_affinity (user_id, topic_id, score, last_seen)
SELECT
    c.user_id,
    c.topic_id,
    SUM(c.w) / LOG(1 + topic_corpus.cnt) AS raw_score,
    MAX(c.last_seen) AS last_seen
FROM combined c
JOIN (
    SELECT topic_id, COUNT(*) AS cnt
    FROM article_topics
    GROUP BY topic_id
) topic_corpus ON topic_corpus.topic_id = c.topic_id
GROUP BY c.user_id, c.topic_id, topic_corpus.cnt
ON CONFLICT (user_id, topic_id) DO UPDATE
SET score = EXCLUDED.score, last_seen = EXCLUDED.last_seen;

-- Step 4: normalizzazione per-utente (max → 1.0) in una seconda query
UPDATE user_topic_affinity uta
SET score = uta.score / NULLIF(max_uta.max_score, 0)
FROM (
    SELECT user_id, MAX(score) AS max_score
    FROM user_topic_affinity
    GROUP BY user_id
) max_uta
WHERE uta.user_id = max_uta.user_id;
```

Dove `half_life_seconds(topic_type)` è una helper function PL/pgSQL
che ritorna 30/15/5 giorni in secondi a seconda del tipo (vedi tabella
sopra in "Decay").

**Frequenza**: cron 04:00 + 16:00 UTC (allineato a `yf-reclassify-topics`).
Costo stimato: scan su 90g di `activity_log` partitioned (3 partizioni
mensili) + join con `article_topics` indicizzato → secondi-decine di
secondi su corpus medio (~10k articoli, ~100 utenti attivi).

### Layer online — re-rank /me/feed

Quando l'utente carica `/me/feed`:

1. Query attuale: top-N articoli del suo feed, ordinati `published_at DESC`.
   → Vedi [`articles_service.py:_query_timeline`](../backend/app/services/articles_service.py).
2. **Allarga la window**: invece di `LIMIT 24`, prendi `LIMIT 100`
   articoli candidati nelle ultime 72h (o quanto basta per averne 100).
3. Per ogni candidato calcola `score`:

```
score = w_fresh  * freshness(article.published_at)
      + w_topic  * sum(affinity[topic] for topic in article.topics)
      + w_source * affinity[article.source_id]
      + w_bm     * (1 if any other user with similar profile bookmarked it)
      − w_div    * diversity_penalty(article, already_picked)
```

Pesi iniziali (da tunare):
```
w_fresh  = 1.0    # decadenza: 1.0 per <2h, 0.6 per 24h, 0.3 per 72h
w_topic  = 2.5
w_source = 0.8
w_bm     = 0.5    # signal debole in v1 (no CF)
w_div    = 0.4    # forte penalità su 3+ stesso topic in 5 righe
```

4. Ordina per `score DESC`, ritaglia ai primi 24 → SPA.
5. **Floor cronologico**: se score di tutti è simile (cold-start, no
   interazioni), torna al chronological puro. Soglia: stddev(score) <
   threshold → bypass.

Implementazione: nuovo modulo `app/services/ranking_service.py`. La
funzione `timeline_for_user` di [articles_service.py](../backend/app/services/articles_service.py)
diventa thin wrapper che decide se chiamare il chrono attuale o passare
attraverso il ranker.

### Cursor pagination

Il keyset attuale `(published_at, id)` non funziona per score-ordered.
Due opzioni:

A) **Score+id keyset opaque** — encoded come prima. Il client passa
   cursor opaco al server, il server applica filtro `WHERE
   score < cur_score OR (score = cur_score AND id < cur_id)`. Problema:
   lo score è ricomputato ad ogni request → l'ordinamento può cambiare
   tra page 1 e page 2.

B) **Cache della query nel cookie/session** — la prima request compone
   la lista ordinata di 100 article_id, salva in Redis con TTL 30 min
   sotto `yf:rank:{user_id}:{ts}`. Le pagine successive paginano dentro
   la lista fissa. Tradeoff: richiede Redis ma garantisce stabilità.

Opzione **B** è più pulita per UX. Costo: 1 set Redis + N get.

## Cold start

Utente con < 10 click in 30 giorni: pochissimo segnale per ranking.
Strategia:

1. **Boost da onboarding**: i topic che ha esplicitamente seguito al
   signup (se il tour onboarding li chiede) → seed dell'affinity con
   score base 0.5.
2. **Boost dalle sources scelte**: ogni source sottoscritta contribuisce
   ai topic dei suoi articoli recenti.
3. **Fallback chrono**: se nemmeno questo basta (utente appena
   registrato), bypass del ranker e mostra timeline chronologica.

La trasition è graduale: man mano che `user_topic_affinity.score`
cresce, il `w_topic` effettivo aumenta vs `w_fresh`.

## Il ruolo del fingerprint

Casi d'uso del fingerprint nel ranker:

### 1. Merge dell'attività pre-registrazione

Quando un utente si registra, lo stesso browser ha lasciato eventi
`activity_log` con `user_id IS NULL` + `fingerprint = abc123`. Al
signup:

```sql
UPDATE activity_log
SET user_id = $new_user_id
WHERE user_id IS NULL
  AND fingerprint = $current_fp
  AND ts >= now() - INTERVAL '30 days';
```

Così il nuovo utente "eredita" la sua cronologia di letture anonime,
evitando il cold-start zero.

### 2. Multi-device awareness

Se lo stesso `user_id` appare con due fingerprint diversi (PC + mobile),
non facciamo niente di speciale — l'affinity per topic/source è la
stessa indipendentemente dal device. **Non** facciamo personalizzazione
*per device* perché complicherebbe senza chiaro beneficio.

### 3. Anti-fraud signal

Se due utenti distinti condividono lo stesso fingerprint (account
shared con familiari) i loro profili divergeranno comunque. Se invece
un fingerprint compare con 50 user_id diversi in poche ore, è bot
farming → al ranker non importa, ma è segnale per [security](SECURITY.md).

### 4. Consent gating

Senza consenso (`useTrackingConsent` → "denied"), il fingerprint non
viene generato e il frontend non emette eventi `/yf_track`. Per quegli
utenti:
- L'affinity table resta vuota → fallback chrono.
- Niente merge pre-login.
- Va comunicato in privacy settings: "il feed personalizzato richiede
  il consenso al tracciamento".

## Privacy / consent

- L'opt-out su `/me/privacy` deve disabilitare anche il re-rank server
  side, non solo il tracking client. Aggiunta colonna `users.tracking_consent`
  o flag in `users.metadata`.
- Retention `activity_log`: già gestita da [retention_service](../backend/app/services/retention_service.py)
  (partitioned drop). I dati di telemetria per utente cancellato
  sparirebbero col CASCADE su `user_id`.
- Export GDPR: il prossimo data-takeout deve includere
  `user_topic_affinity` + `user_source_affinity`.

## Condivisione articoli (sharing)

Funzionalità nuova che alimenta direttamente il segnale `share` del
ranker (peso +2.0). Bottone di condivisione **sull'overlay della foto
articolo, in basso a sinistra**, simmetrico al bookmark (top-right).

### Comportamento

Click sul bottone → menu/popover con 5 piattaforme + "Copia link":

| Target    | URL intent                                                              |
|-----------|-------------------------------------------------------------------------|
| LinkedIn  | `https://www.linkedin.com/sharing/share-offsite/?url={URL}`             |
| WhatsApp  | `https://wa.me/?text={ENCODED_TITLE_PLUS_URL}`                          |
| Threads   | `https://threads.net/intent/post?text={ENCODED_TITLE_PLUS_URL}`         |
| X         | `https://twitter.com/intent/tweet?text={TITLE}&url={URL}`               |
| Substack  | "Copia link" (no share intent pubblico) → `navigator.clipboard.writeText` + toast |

**URL condiviso**: `article.url_canonical` (link originale della fonte).
Razionale: l'utente vuole condividere la notizia, non il pannello YouFeed.
Si può eventualmente aggiungere `?ref=youfeed` per attribution analytics
ma è opzionale. Da rivedere se in futuro vorremo spingere visite alla
pagina pubblica `/{username}`.

### UX

- Icona overlay in basso-sinistra dell'immagine, simmetrica al bookmark
  (`absolute left-2 bottom-2`, ~32×32px, bg semitrasparente nero, hover
  blu).
- Click → popover ancorato sotto/sopra il bottone (Headless UI o markup
  manuale Vue, niente librerie aggiuntive).
- Sotto i 5 brand: link "Copia link" (clipboard) + se disponibile
  `navigator.share` → bottone "Sistema (condividi…)" che apre il dialog
  nativo mobile.
- Tutti i click sui target emettono `share` con
  `metadata = {"to": "linkedin"|"whatsapp"|"x"|"threads"|"substack"|"copy"|"native"}`.

### Componente

Nuovo `ShareButton.vue` riutilizzabile in:
- `ArticleCard.vue` (timeline)
- `ArticleDetail.vue` (sulla foto grande)

Props: `articleId`, `title`, `url`, `position` (per orientare il popover
in alto/basso a seconda del layout).

## Phase d'implementazione

Cinque fasi, organizzate per parallellizzabilità. Il task fa
"sharing" è dentro Phase 1 perché alimenta uno dei segnali del ranker.

### Phase 1 — Frontend tracking + sharing (settimana 1-2, parallelizzabile)

**1.A · Helper tracking centralizzato**
- [ ] `lib/tracking.ts` con `trackEvent(type, target?, metadata?)`
- [ ] Internamente: `fetch('/yf_track', { method:'POST', keepalive:true })`,
      header `X-YF-Fingerprint` se consent==granted
- [ ] Throttle/dedupe per impression (1 hit per (article_id, session))

**1.B · Eventi dal feed timeline**
- [ ] `ArticleCard.vue`: IntersectionObserver → emit `impression`
      (debounce 500ms, una volta per articolo per pagina)
- [ ] `ArticleCard.vue` click su card → emit `preview_open` PRIMA del
      router-push

**1.C · Eventi dalla detail page**
- [ ] `ArticleDetail.vue`: timer +
      `document.visibilityState='visible'` → emit `dwell_5s` a 5s,
      `dwell_15s` a 15s, `dwell_60s` a 60s (cumulativi sulla stessa
      visita, niente double-fire)
- [ ] Click sul bottone "Apri l'articolo originale": emit
      `original_open` con `keepalive:true` PRIMA del `window.open`
- [ ] Click su una card delle "notizie correlate": emit `related_click`
      con `metadata = {"from_article":A, "shared_topics":[ids]}` —
      gli shared_topics si calcolano client-side dall'intersezione di
      `A.topics` con `B.topics` (entrambe già nel payload)

**1.D · Eventi da azioni esplicite**
- [ ] Bookmark button → emit `bookmark` quando aggiunge (NON quando rimuove)
- [ ] Share button (vedi 1.E) → emit `share` con destination

**1.E · Sharing — componente ShareButton.vue (nuovo)**
- [ ] Markup base: icona overlay `absolute left-2 bottom-2 w-8 h-8`
      simmetrica al bookmark, bg nero/55 + hover blue-600
- [ ] Popover Vue con 5 + 2 azioni (LinkedIn, WhatsApp, Threads, X,
      Substack/copia, copia diretta, native share se disponibile)
- [ ] Helper `buildShareUrl(target, title, url)` con encoding corretto
- [ ] Substack target: `await navigator.clipboard.writeText(url)` +
      toast "Link copiato"
- [ ] Native Web Share: bottone visibile solo se `navigator.share`
      esiste (mobile)
- [ ] Integrazione in `ArticleCard.vue` (over la foto)
- [ ] Integrazione in `ArticleDetail.vue` (over la foto grande)
- [ ] Telemetria: ogni target emette `share` con `metadata.to`
- [ ] Test manuale su mobile (verifica intent URL aprano l'app nativa)

**1.F · Consent gating (privacy)**
- [x] Tutti gli emit di tracking gated su `useTrackingConsent.consent === 'granted'`
      (early-return dentro `trackEvent()` in `lib/tracking.ts`)
- [x] Bottoni share funzionano ANCHE senza consent (sono azione esplicita
      dell'utente: l'intent URL apre comunque); il tracking event `share`
      viene loggato solo con consent (gated dallo stesso `trackEvent()`)
- [ ] Toggle "Feed personalizzato" in `PrivacySettings.vue` → spostato a
      Phase 2.A insieme alla migration `users.personalize` (la rollup
      che dovrebbe disabilitare non esiste ancora)

**1.G · Verifica raccolta dati**
- [ ] Dopo deploy, controlla in `activity_log` che gli eventi nuovi
      arrivino con `target_type='article'` + `target_id` valido
- [ ] Lascia girare **almeno 2 settimane** prima di Phase 2: serve un
      dataset di partenza

### Phase 2 — Affinity rollup (settimana 3, dipende da dati Phase 1)

**2.A · Schema + opt-out**
- [ ] Migration 0021: tabelle `user_topic_affinity` + `user_source_affinity`
      (vedi pseudocodice sopra)
- [ ] Migration aggiunge anche colonna `users.personalize BOOLEAN DEFAULT TRUE`
- [ ] Endpoint `PATCH /yf_me/preferences` per `users.personalize`
- [ ] In `PrivacySettings.vue`: toggle "Feed personalizzato"
      (spostata qui da 1.F)

**2.B · Helper per half-life**
- [ ] PL/pgSQL function `half_life_seconds(topic_type TEXT)` che
      ritorna 30/15/5 giorni in secondi (default 30g se type sconosciuto)

**2.C · Rollup CLI**
- [ ] `app/utils/compute_affinities.py` — analoga a
      [`refresh_topics.py`](../backend/app/utils/refresh_topics.py): carica .env,
      apre session, esegue le query SQL del doc, commit. Idempotente.
- [ ] Supporta `--user-id N` per ricalcolare un singolo utente (utile
      per signup hook in Phase 4)
- [ ] Supporta `--dry-run` con stats (n. utenti aggiornati, n. topic,
      tempo)

**2.D · Schedule**
- [ ] `infra/systemd/yf-compute-affinities.service` + `.timer`
      (04:00 + 16:00 UTC, dopo `yf-reclassify-topics`)
- [ ] Aggiornare `infra/systemd/README.md`

**2.E · Prune**
- [ ] Aggiungere al [retention_service](../backend/app/services/retention_service.py):
      `DELETE FROM user_topic_affinity WHERE last_seen < now() - 180g OR score < 0.05`
- [ ] Stesso pattern per `user_source_affinity`

**2.F · Backfill iniziale**
- [ ] Lancio manuale via screen: `python -m app.utils.compute_affinities --all`
- [ ] Verificare che le top-affinity dell'utente di test (`drtarr`) abbiano senso

### Phase 3 — Re-rank online (settimana 4)

**3.A · Ranking service**
- [ ] `app/services/ranking_service.py`:
  - `score_candidate(article, affinity_topic, affinity_source, already_picked)`
  - `rerank(candidates: list, user_affinities) -> list[ranked]`
  - Pesi `w_fresh/w_topic/w_source/w_div` come costanti modulo (tunabili)

**3.B · Integration nel timeline**
- [ ] In `articles_service.timeline_for_user`:
  - if user.personalize == False → vecchio path chronologico
  - if affinity rows < 20 → cold-start, vecchio path
  - else: query top-100 candidates, passa a `rerank()`, ritaglia a `limit`
- [ ] Logging strutturato: `yf.ranking.applied user_id=… arm=ranked|chrono`

**3.C · Stable pagination**
- [ ] Redis key `yf:rank:{user_id}:{request_ts}` con TTL 30min, JSON
      della lista ordinata di article_id
- [ ] Cursor opaco = `(request_ts, offset)` base64
- [ ] Pagine successive: deserializza cursor, pesca dalla lista cached,
      avanza offset

**3.D · Toggle utente**
- [ ] In `PrivacySettings.vue`: toggle "Feed personalizzato" già da Phase 1.F
- [ ] PATCH `/yf_me/preferences` aggiorna `users.personalize`

### Phase 4 — Fingerprint merge (settimana 4, parallelo a Phase 3)

**4.A · Hook signup**
- [ ] In `auth_service.create_user` (o equivalente post-signup):
      legge `X-YF-Fingerprint` dalla request,
      `UPDATE activity_log SET user_id=new_id WHERE user_id IS NULL
       AND fingerprint=$fp AND ts >= now() - 30d`
- [ ] Trigger immediato `compute_affinities --user-id new_id` in background
      (RQ enqueue, non blocca la response)

**4.B · Test**
- [ ] Test end-to-end: utente anonimo legge 5 articoli → si registra →
      affinity table popolata immediatamente

### Phase 5 — A/B test e tuning (settimana 5+)

**5.A · Assegnazione arm**
- [ ] Migration: aggiunge `users.ranking_arm CHAR(8) DEFAULT NULL`
- [ ] All'attivazione di un utente: random 50/50 → `'chrono'` o `'ranked'`
- [ ] `timeline_for_user` rispetta `ranking_arm`

**5.B · Metriche**
- [ ] Pannello admin `/yf_admin/ranking/metrics`:
  - CTR per arm (click / impression)
  - Bookmark rate per arm
  - Dwell medio sessione per arm
  - Retention D+1, D+7 per arm
- [ ] Update settimanale, non realtime (heavy query)

**5.C · Decisione**
- [ ] Se `ranked` vince in 3/4 metriche → promuove a default per tutti
- [ ] Se perde → analisi qualitativa, ritorna a chrono o ritunà pesi
- [ ] Salva pesi finali + risultato A/B in `STATUS.md`

## Open questions

1. **Storia minima per attivare il ranker**: 10 click? 30? Da decidere
   guardando la distribuzione reale dopo Phase 1.
2. **Cosa fare se l'utente accetta tracking solo DOPO N giorni**:
   abbiamo già attività anonima legata al suo fingerprint? Sì se il fp
   viene generato anche senza login (verificare in
   [useTrackingConsent](../frontend/src/composables/useTrackingConsent.ts)
   — oggi `getFingerprint` ritorna null se consent != granted, quindi
   l'utente che dà consenso solo dopo non ha storia → no merge).
3. **Per quanto tempo manteniamo `user_topic_affinity`**: chiusa dalla
   sezione "Decay e scadenza". Half-life per topic.type (30g brand/
   subject, 15g model/software, 5g event) + cutoff 90g sull'attività
   considerata + prune dopo 180g. Da rivalutare dopo Phase 2 con dati
   reali sulla distribuzione delle ricomparse di topic.
4. **Diversity quanta**: 3 articoli stesso topic in fila va bene? 5
   stessa source? Da osservare.
5. **Pre-LLM o post-LLM**: con il LLM fallback (T-018) scartato per
   budget, restiamo su SQL puro. Se in futuro torniamo all'LLM,
   l'affinity può alimentare il prompt ("l'utente ha mostrato interesse
   per: AI, fintech, Roma calcio") ma resta layer indipendente.
6. **Negative explicit**: serve un bottone "non mi interessa" sulle
   card? Aumenterebbe la qualità del segnale negativo (oggi inferito
   solo da impression-no-click). Da rivalutare in Phase 5.

## Riferimenti

- [BACKEND.md](BACKEND.md) — schema attività e stack
- [DATABASE.md](DATABASE.md) — partitioning `activity_log` e retention
- [SECURITY.md](SECURITY.md) — fingerprint usato anche per detection abuse
- [INGESTION.md](INGESTION.md) — `article_topics` come fonte primaria del segnale
- [STATUS.md](STATUS.md) → Phase 2.0.A — Recommendation engine (questo doc è la specifica)
