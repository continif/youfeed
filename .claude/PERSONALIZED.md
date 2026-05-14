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

| Evento       | Trigger                                            | Peso (idea) |
|--------------|----------------------------------------------------|-------------|
| `impression` | card articolo entra in viewport ≥ 500ms            | +0.1        |
| `click`      | click sul titolo/immagine (apre detail)            | +1.0        |
| `dwell`      | tempo sulla detail page, in scaglioni `>5s/15s/60s`| +0.3..+1.5  |
| `bookmark`   | salva tra i preferiti                              | +3.0        |
| `share`      | invio link a terzi                                 | +2.0        |
| `unsource`   | toglie la fonte dal feed                           | −2.0 source |

Da considerare negativi impliciti:
- Articolo impression ≥ 3 volte, mai cliccato → leggera penalità sul
  topic (e ancora più leggera sulla source).
- Articolo aperto + chiuso entro <3s → segnale "non era quello", no peso.

## Architettura

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

Computazione (pseudo-SQL):

```sql
-- Per ogni (user, topic) negli ultimi 30 giorni:
INSERT INTO user_topic_affinity (user_id, topic_id, score, last_seen)
SELECT
    al.user_id,
    at.topic_id,
    SUM(
        weight_for_event(al.event_type, al.metadata)
        * EXP(-EXTRACT(EPOCH FROM now() - al.ts) / (15 * 86400))  -- 15g half-life
    ) / NULLIF(SUM(weight_for_event(al.event_type, al.metadata)), 0) AS raw_score,
    MAX(al.ts) AS last_seen
FROM activity_log al
JOIN article_topics at ON at.article_id = (al.target_id)::bigint
WHERE al.ts >= now() - INTERVAL '30 days'
  AND al.target_type = 'article'
  AND al.event_type IN ('click', 'open', 'dwell', 'bookmark', 'share')
GROUP BY al.user_id, at.topic_id;
```

Poi normalizzo per utente (max-score → 1.0) e applico TF-IDF-ish:
divido per `log(1 + occurrences_topic_corpus)` così i topic super-comuni
(es. "Italia", "politica") non saturano l'affinity.

**Frequenza**: cron 04:00 + 16:00 UTC (allineato a `yf-reclassify-topics`).
Costo stimato: query single su tabella partitioned, scan limitato a 2
partizioni × 30 giorni → secondi, non minuti.

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
- [ ] In `ArticleCard.vue` / `ArticleDetail.vue`: click sul titolo →
      emit `click` + `open`.
- [ ] In `ArticleDetail.vue`: timer + scroll → emit `dwell` a 5s/15s/60s.
- [ ] Tutti gli emit gated su `useTrackingConsent.consent === 'granted'`.
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
3. **Per quanto tempo manteniamo `user_topic_affinity`**: i topic
   transient (notizia di un giorno, es. "Sciopero ATM") non dovrebbero
   contare per sempre. La half-life di 15g sull'event peso dovrebbe
   bastare, ma valutiamo dopo Phase 2.
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
