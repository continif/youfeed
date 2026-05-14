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

## Phase d'implementazione

### Phase 0 — preparazione (no UI change)
- [ ] Verificare che `target_type='article'` + `target_id=<id>` siano
      effettivamente popolati dai pochi eventi che oggi finiscono in
      `activity_log` (probabilmente NO → vedi Phase 1).
- [ ] Migration per `user_topic_affinity` + `user_source_affinity`.

### Phase 1 — emissione eventi (silent collection)
- [ ] In `ArticleCard.vue`: IntersectionObserver → emit `impression`
      una volta per articolo per sessione, debounce 500ms.
- [ ] In `ArticleCard.vue` (click sul card che apre `/me/article/N`):
      emit `preview_open`.
- [ ] In `ArticleDetail.vue`: timer + visibility → emit `dwell_5s`,
      poi `dwell_15s`, poi `dwell_60s` (cumulativi, NON overlappabili).
- [ ] In `ArticleDetail.vue`, click sul bottone "Apri l'articolo
      originale": emit `original_open` PRIMA del `window.open`.
- [ ] Click su una card nelle "notizie correlate" della detail page:
      emit `related_click` con `metadata = {"from_article":<A>,
      "shared_topics":[<id>,<id>,...]}`. Lo shared_topics si calcola
      lato client (ha sia A.topics che B.topics).
- [ ] Bottone 💾 bookmark e "condividi" → emit `bookmark`/`share`.
- [ ] Tutti gli emit gated su `useTrackingConsent.consent === 'granted'`.
- [ ] Helper centrale `lib/tracking.ts` con `trackEvent(type, target, metadata?)`
      che fa `fetch('/yf_track', { keepalive: true })` + gestisce
      l'header `X-YF-Fingerprint`.
- [ ] Almeno 2 settimane in produzione prima di Phase 2 → bisogna avere
      dati su cui calcolare l'affinity.

### Phase 2 — calcolo offline affinity
- [ ] Utility CLI `app.utils.compute_affinities` che fa il rollup SQL.
- [ ] Systemd timer `yf-compute-affinities` 04:00 + 16:00 UTC.
- [ ] Backfill iniziale: lancio manuale.

### Phase 3 — re-rank online
- [ ] `app/services/ranking_service.py`: linear scoring + diversity penalty.
- [ ] `articles_service.timeline_for_user` chiama il ranker se l'utente
      ha affinity sufficiente (>= 20 righe in `user_topic_affinity`).
- [ ] Redis cache della lista ordinata per pagination stabile.
- [ ] Toggle utente "ordina cronologico" in settings.

### Phase 4 — fingerprint merge
- [ ] Hook al signup: UPDATE `activity_log` con `user_id` dai
      fingerprint correnti.
- [ ] Re-trigger immediato del rollup affinity per il nuovo user.

### Phase 5 — A/B test e tuning pesi
- [ ] Flag in `users.metadata.ranking_arm` per assegnare utenti a
      `'chrono' | 'ranked'` random 50/50.
- [ ] Misura proxy di engagement: click-through rate, bookmark rate,
      dwell medio per session, ritorni a 24h.
- [ ] Promozione del ranker a default se vince in tutte e 4 le metriche.

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
