# Knowledge Graph

YOUFEED estrae da titolo e contenuto degli articoli le entità rilevanti (brand, persone, argomenti) e le organizza in un grafo. Il grafo alimenta:
- la pagina pubblica `/{username}/topic/{name}` (articoli su una stessa entità da fonti diverse);
- la home pubblica raggruppata per topic;
- il motore di raccomandazione (utenti che leggono articoli su entità X tendono ad apprezzare entità Y);
- la navigazione "topic correlati" (Inter ↔ Lautaro Martinez ↔ Serie A);
- l'autocomplete della search.

## Modello concettuale

Tre tipi di nodo, tre tipi di arco.

### Nodi

```
articles                      # già esistente, vedi INGESTION.md
topics                        # entità canoniche, curate (brand, person, subject)
entities                      # entità grezze estratte da NER, possibilmente non risolte
```

`topics` è il livello "pulito" usato dall'app utente. `entities` è il livello "raw" che alimenta i topic via resolution.

### Archi

```
article_topics      article ──mentions──> topic
article_entities    article ──contains──> entity
topic_relations     topic   ──related_to──> topic
```

## Schema dettagliato

### `topics` — entità canoniche
```
topics
  id              bigserial PK
  type            text          -- 'brand' | 'person' | 'subject'
  slug            text UNIQUE   -- usato negli URL pubblici
  display_name    text
  aliases         text[]        -- forme alternative per match dizionario
  description     text
  external_refs   jsonb         -- {wikidata: "Q123", ...}
  is_curated      bool          -- false se generato automaticamente, true se rivisto
  created_at      timestamptz
```

### `entities` — entità raw da NER
```
entities
  id              bigserial PK
  surface_form    text          -- "Lautaro Martínez" come scritto
  normalized      text          -- "lautaro martinez" (lower, no accenti)
  ner_type        text          -- 'PER' | 'ORG' | 'LOC' | 'MISC' | 'REGEX_PER' | 'REGEX_BRAND'
  topic_id        bigint FK     -- nullable: NULL = non ancora risolta
  occurrence_count int          -- contatore aggregato
  first_seen_at   timestamptz
  last_seen_at    timestamptz
  UNIQUE (normalized, ner_type)
```

Quando un'entità raggiunge una soglia di occorrenze e non è ancora mappata, finisce nella **dashboard admin** per essere promossa a `topics` (manuale o assistito da LLM).

### `article_topics` — arco articolo→topic *(già esistente)*
```
article_topics
  article_id      bigint FK
  topic_id        bigint FK
  score           float
  source          text          -- 'dict' | 'ner' | 'taxonomy' | 'llm'
  position        text          -- 'title' | 'body' | 'both'
  PK (article_id, topic_id)
```

### `article_entities` — arco articolo→entità raw
```
article_entities
  article_id      bigint FK
  entity_id       bigint FK
  count           int           -- occorrenze nell'articolo
  in_title        bool
  PK (article_id, entity_id)
```

Permette di tenere traccia di entità non ancora risolte e analizzare ricorrenze.

### `topic_relations` — co-occorrenza tra topic
```
topic_relations
  topic_a_id      bigint FK     -- topic_a < topic_b per evitare duplicati
  topic_b_id      bigint FK
  type            text          -- 'co_occurs'
  weight          float         -- es. PMI o normalizzato 0..1
  cooccurrence    int           -- # articoli con entrambi
  last_updated    timestamptz
  PK (topic_a_id, topic_b_id, type)
```

Aggiornato in batch (job notturno o sliding window): per ogni articolo nuovo, per ogni coppia di topic mentionati, incrementa `cooccurrence` e ricalcola `weight`.

## Estrazione (pipeline)

Dettaglio dello step "estrazione entità" descritto in [INGESTION.md](INGESTION.md).

```
articolo (title + content_text)
        ↓
┌──────────────────────────────────────────────┐
│ Step A — Origin taxonomy             [v1.0]  │
│   categorie/tag dichiarati dalla fonte       │
│   matching su topics.aliases                 │
│   → article_topics (source='taxonomy')       │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step B — Dizionario                  [v1.0]  │
│   per ogni topic in topics:                  │
│     for alias in topic.aliases:              │
│       match con confine di parola            │
│       title=peso 2, body=peso 1              │
│   → article_topics (source='dict')           │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step C — Regexp heuristics           [v1.0]  │
│   pattern per persone (capitalized + de/di/  │
│   della/von/...) e brand (CAPS, CamelCase)   │
│   filtro su stopwords (mesi, giorni, prono.) │
│   → upsert in entities                       │
│   → article_entities                         │
│   → article_topics (source='regex') solo     │
│      se la surface coincide con un alias     │
│      di topic noto                           │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step D — NER (spaCy)                 [v1.2]  │
│   estrazione PER/ORG/LOC/MISC                │
│   sostituisce/raffina output regexp          │
│   normalizzazione → upsert in entities       │
│   se entity.topic_id NOT NULL:               │
│     → article_topics (source='ner')          │
│   sempre:                                    │
│     → article_entities                       │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step E — LLM fallback (opzionale)    [v1.2]  │
│   se article_topics ancora vuoto             │
│   prompt Haiku con title + first 1000 chars  │
│   estrae brand/persone/argomenti             │
│   match con topics.aliases o entities        │
│   → article_topics (source='llm')            │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step F — Topic relations (batch)     [v2.0]  │
│   trigger: ogni N articoli oppure cron       │
│   per ogni coppia (a,b) in article_topics    │
│   incrementa cooccurrence                    │
│   ricalcola weight (es. PMI)                 │
└──────────────────────────────────────────────┘
```

### Step C — Regexp heuristics (v1.0): pattern italiani

Patterns minimi (compilati una volta a startup worker):

**Persone** — primo + (particella opzionale) + cognome:
```
\b
[A-ZÀ-Ý][a-zà-ÿ]+                                  # Mario
(?:\s+(?:de|di|del|della|dei|dello|degli|delle|
       da|dal|dalle|dallo|dalla|von|van|du|le|la)
   \s+
  |\s+)
[A-ZÀ-Ý][a-zà-ÿ]+                                  # Draghi / De Maria
(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)?                          # opzionale terzo
\b
```
Cattura: `Mario Draghi`, `Roberto De Maria`, `Luigi Di Maio`, `Maria Elena Boschi`.

**Brand uppercase** (acronimi 2-7 lettere):
```
\b[A-Z]{2,7}\b
```
Cattura: `FIAT`, `RAI`, `BMW`, `NASA`. Filtro stoplist: `IO`, `TU`, sigle istituzionali generiche.

**Brand CamelCase**:
```
\b[a-z]?[A-Z][a-z]+(?:[A-Z][a-z]+)+\b
```
Cattura: `iPhone`, `PayPal`, `eBay`, `YouFeed`.

**Trademark suffixes**:
```
\b\w+(?:®|™)\b
```

**Filtri post-match (riducono false positive)**:
- Stopwords: mesi (`Gennaio`-`Dicembre`), giorni (`Lunedì`-`Domenica`), pronomi maiuscoli inizio frase
- Toponimi comuni (`Roma`, `Milano`, `Italia`): non scartati ma marcati `low_confidence=true`
- Surface forms a inizio frase: `confidence -= 0.2` (la maiuscola è strutturale, non semantica)
- Lunghezza minima 3 caratteri per i pattern uppercase

**Output**:
- Sempre: upsert in `entities` (con `ner_type='REGEX_PER'` o `'REGEX_BRAND'`) + insert in `article_entities`
- Solo se la surface coincide con un alias di un topic noto: anche `article_topics` con `source='regex'`
- Le entità che non matchano un topic restano grezze nella tabella `entities` e crescono in `occurrence_count` finché un admin le promuove (o finché in v1.2 il NER conferma + Wikidata enrichment le rifinisce automaticamente)

### Resolution entity → topic

Quando un'entità raw raggiunge un certo numero di occorrenze (es. 20) e ha NER type `PER` o `ORG`, finisce nella coda di review:

1. Admin la vede in dashboard con: surface forms, contesti d'uso, articoli che la mentionano
2. Può: (a) promuoverla a nuovo `topic`, (b) collegarla a topic esistente come alias, (c) ignorarla (entity diventa `ignored=true`)
3. Opzionale: pre-suggestion automatica via Claude Haiku con lookup Wikidata per disambiguare

### Wikidata enrichment (automatico, async)

Ogni nuovo `topic` curato (manualmente o auto-promosso) viene arricchito da un job RQ `enrich_wikidata(topic_id)` che gira in background — non blocca la creazione.

**Cosa preleviamo da Wikidata**:
- `description` in IT → `topics.description` (se mancante, lasciamo vuoto — niente fallback su altre lingue, l'app è IT-only)
- `image` (P18) → `topics.external_refs.image_url`
- `logo` (P154) per i brand → `topics.external_refs.logo_url`
- `instance_of` (P31) e `subclass_of` (P279) → conferma tipo (`brand` / `person` / `subject`) + `topics.external_refs.types`
- Label IT (`rdfs:label@it`) e label nella lingua nativa dell'entità (`P1559` *native label*) → merge in `topics.aliases`. La native label cattura nomi propri di persone/brand stranieri ("Volodymyr Zelenskyy", "Microsoft Corporation") che compaiono comunque nel testo italiano.
- `also_known_as` (P1449, P742) → merge in `topics.aliases`
- `dateOfBirth`/`dateOfDeath` per `person` → `topics.external_refs.dob`, `dod`
- Wikidata ID (Q...) → `topics.external_refs.wikidata`

**Pipeline**:
1. Search Wikidata API: `wbsearchentities?search={display_name}&type=item&language=it`
2. Top match con threshold di confidenza (basato su label match esatto + `instance_of` coerente con `topic.type`)
3. Se confidenza < soglia → `is_curated=false`, lascia il topic non arricchito (admin può confermare manualmente)
4. SPARQL singola query per tutti i campi sopra
5. UPDATE `topics` con merge non distruttivo degli alias (no override delle parole già presenti)

**Costo**:
- Wikidata API: pubblica, gratuita, rate limit ~5 req/sec con User-Agent
- Volume: solo alla creazione/curation di un topic, non per articolo. Stima: decine/centinaia di chiamate al giorno, trascurabile.
- Cache: nessuna (chiamato una sola volta per topic, poi `external_refs` è la cache)

**Tecnologia**: `httpx` + parsing JSON, no SDK dedicato. Endpoint:
- Search: `https://www.wikidata.org/w/api.php`
- SPARQL: `https://query.wikidata.org/sparql`

## Query tipiche

**Articoli su un topic, cronologico inverso** (pagina pubblica `/{username}/topic/{name}`):
```sql
SELECT a.* FROM articles a
JOIN article_topics at ON at.article_id = a.id
JOIN topics t ON t.id = at.topic_id
JOIN user_sources us ON us.source_id = a.source_id
JOIN categories c ON c.id = us.category_id
WHERE t.slug = :slug
  AND us.user_id = :user_id
  AND c.is_public = true
ORDER BY a.published_at DESC
LIMIT 50;
```

**Topic correlati a un topic**:
```sql
SELECT t.*, tr.weight, tr.cooccurrence
FROM topic_relations tr
JOIN topics t ON t.id = CASE
  WHEN tr.topic_a_id = :id THEN tr.topic_b_id
  ELSE tr.topic_a_id END
WHERE tr.topic_a_id = :id OR tr.topic_b_id = :id
ORDER BY tr.weight DESC
LIMIT 20;
```

**Stesso argomento da fonti diverse** (home pubblica raggruppata):
```sql
SELECT t.slug, t.display_name, COUNT(DISTINCT a.source_id) AS fonti,
       array_agg(a.id ORDER BY a.published_at DESC) AS articles
FROM articles a
JOIN article_topics at ON at.article_id = a.id
JOIN topics t ON t.id = at.topic_id
WHERE a.published_at > now() - interval '24 hours'
GROUP BY t.slug, t.display_name
HAVING COUNT(DISTINCT a.source_id) >= 2
ORDER BY COUNT(DISTINCT a.source_id) DESC, MAX(a.published_at) DESC;
```

## Storage del grafo — opzioni

Il grafo è inerentemente relazionale (nodi + archi); la scelta è su **dove** persistere e come interrogarlo.

| Opzione | Descrizione | Quando |
|---|---|---|
| **A) Tabelle Postgres** | Schema sopra, query in SQL standard | Default consigliato — semplice, ZERO sistemi extra |
| **B) Apache AGE** | Estensione Postgres che aggiunge openCypher | Se servono query graph complesse (path, traversal a N hop) |
| **C) Neo4j / Memgraph** | DB grafo dedicato, più performante su traversal profondi | Solo se A+B non bastano |

**Raccomandazione**: A. Le query tipiche di YOUFEED (1-2 hop max) sono perfettamente serviite da JOIN SQL. Se in futuro emergesse bisogno di traversal profondi (es. "trova articoli connessi a Inter via almeno 3 entità intermedie"), si valuta AGE come estensione non distruttiva.

## Recommendation engine — come usa il KG

Non è in scope per l'MVP, ma il design del KG va già pensato per supportarlo:

1. **Profile utente** = vettore di topic letti, pesato per recency e dwell time (dati da `activity_log`)
2. **Espansione tramite KG**: a partire dai top-N topic dell'utente, esplora `topic_relations.weight` per scoprire topic correlati
3. **Ranking articoli**: scoring combinato di (a) match topic profilo, (b) freshness, (c) source affinity (utente legge spesso source X), (d) co-occorrenza con topic letti recentemente
4. **Cold start** per nuovo utente: usa solo i topic delle categorie create + popolarità globale

Tabelle aggiuntive che serviranno *(da progettare quando avvieremo il reco engine)*:
```
user_topic_affinity   user_id, topic_id, score, decayed_at
user_source_affinity  user_id, source_id, score, decayed_at
```

## Decisioni fissate
- Wikidata enrichment automatico per ogni topic curato, via job RQ `enrich_wikidata` ✓

## Da definire
- Soglia di occorrenze per promuovere un'`entities` a candidato review
- Algoritmo `weight` di `topic_relations`: PMI, NPMI, semplice count normalizzato?
- Frequenza ricalcolo `topic_relations` (notturno? sliding window 7 giorni?)
- Soglia di confidenza per accettare un match Wikidata automatico (sopra: arricchisce; sotto: resta non arricchito in attesa di review)
- UI di admin per resolution entity (priorità bassa, MVP può andare con SQL diretto)
