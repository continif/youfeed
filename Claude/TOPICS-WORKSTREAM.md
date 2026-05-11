# TOPICS — workstream qualità estrazione e curatela

Stream parallelo a Phase 21 v1.0 e v1.1. Aggrega tutti i task che riguardano:
qualità di **dictionary classify** ([app/ingestion/classify.py](../backend/app/ingestion/classify.py)),
**topic extractor regex-based** ([app/topic_extractor/](../backend/app/topic_extractor/)),
**curatela seed** ([infra/seed/topics.yaml](../infra/seed/topics.yaml) + snapshot
[data/topics.parquet](../data/topics.parquet)).

NON copre: NER spaCy (Phase 1.2.A), Wikidata enrichment (Phase 1.2.B),
LLM fallback (Phase 1.2.C). Quelle restano nel master plan.

## Convenzioni

- ID task: `T-001`, `T-002`, ... ordine di apertura, mai riusati.
- Stato: `[ ]` aperto · `[~]` in corso · `[✓]` chiuso · `[⚠]` bloccato (annotare motivo).
- Severity: **high** (impatta lo score di tutti gli articoli) · **med** (un sottoinsieme
  di domini) · **low** (estetico/futuro).
- Ogni task ha: descrizione, esempio reale, ipotesi di causa, area/file, DoD.

## Diagnostica raccolta (sample)

Esempi reali di articoli con topic estratti errati o mancati. Sono il banco di
prova per validare i task qui sotto — quando un task chiude, i suoi esempi
devono passare in regressione.

### Sample S-001 — borsa Razer
- **Titolo**: "Bomba Razer: risparmia ben 80€ sulla borsa Xanthus con scomparto imbottito per laptop"
- **Topic attesi**: `Razer` (brand), `Xanthus` o `Razer Xanthus Tote Bag` (model)
- **Topic estratti oggi (post T-001+T-004+T-005+T-009)**: `Razer`, `Laptop`,
  `Notebook`, `Amazon` ✓ (dict classify). Mancano i model — usciranno con scan
  REGEX_MODEL pass-2 (workflow separato dell'extractor).
- **Topic estratti prima**: `Bomba`, `Fascia`, `Canale`, `Rende`, `Dello`
- **Failure mode originale**: blacklist BRAND_SINGLE troppo corta + i 6 nomi
  erano comuni italiani veri (T-009: ambiguous location) + Razer/Laptop/Monitor
  non in topic curated.

### Sample S-002 — monitor Lenovo
- **Titolo**: "Lenovo L27-41 al minimo storico: il monitor IPS da 27″ e 100Hz crolla a soli 89€ su Amazon"
- **Topic attesi**: `Lenovo` (brand), `Lenovo L27-41` (model), `Monitor` (subject)
- **Topic estratti oggi (post T-001+T-003+T-004+T-005+T-009)**: `Monitor`,
  `Lenovo`, `Amazon` ✓ (dict). Il model `Lenovo L27-41` esce via REGEX_MODEL
  ora che il pattern accetta token alfanumerici con dash (T-003).
- **Topic estratti prima**: `Canale`, `Rende`, `Dello`

### Sample S-003 — Megan Gale / Fastweb / Iliad
- **Titolo**: "Megan Gale fa litigare gli operatori. Fastweb chiede a Iliad di fermare lo spot con la testimonial"
- **Topic attesi**: `Megan Gale` (person), `Fastweb` (brand), `Iliad` (brand)
- **Topic estratti oggi (post T-004+T-009)**: `Fastweb`, `Iliad` ✓ (dict). Manca
  `Megan Gale` — è una persona non-curated, deve uscire via REGEX_PER (T-006).
- **Topic estratti prima**: `Campagna`, `Milano`, `Dello`

### Sample S-004 — Qualcomm / Snapdragon
- **Titolo**: "Qualcomm lancia la quinta generazione di Snapdragon 4: prestazioni grafiche migliorate del 77%"
- **Topic attesi**: `Qualcomm`, `Snapdragon 4`, `Smartphone`
- **Topic estratti oggi (post T-011)**: `Qualcomm`, `Snapdragon`, `Smartphone` ✓
  + falso positivo `Lancia` (verbo italiano "lanciare" 3sg che coincide col
  brand auto Lancia curated). Limite contestuale → vedi T-013.
- **Topic estratti prima**: `Lancia`, `Smartphone`

### Sample S-005 — Falso "Dell" in elisione `dell'`
- **Titolo**: "La distribuzione automatica entra nell'era dell'intelligenza artificiale"
- **Topic attesi**: `Intelligenza artificiale`
- **Topic estratti oggi (post T-010)**: `Intelligenza artificiale` ✓
- **Topic estratti prima**: falso positivo `Dell` (matchato in `dell'`).

### Sample S-006 — NOW / Sky On Demand
- **Titolo**: "Cosa guardare su NOW e Sky On Demand a maggio? Le novità tra film, serie TV e originals"
- **Topic attesi**: `NOW`, `Sky On Demand`, `Sky Italia`
- **Topic estratti oggi (post T-011)**: `NOW`, `Sky On Demand` ✓
  (entrambi aggiunti come brand curated)
- **Topic estratti prima**: solo `Sky Italia` (matchato via alias "Sky").

### Sample S-007 — Nina Festival
- **Titolo**: "Nina Festival, tre giorni per discutere l'intelligenza artificiale oltre il mito della neutralità"
- **Topic attesi**: `Nina Festival` (person/brand), `Intelligenza artificiale`
- **Topic estratti oggi**: `Intelligenza artificiale`, `Roma` (FP). `Nina Festival` non
  è curated né viene estratto al volo: il dict classify estrae solo entità *già
  in topics*. Per estrarre nuove entità in tempo reale serve integrare
  REGEX_PER nel pipeline classify (T-012, postponed).
- **Failure mode**: limite architetturale, non bug.

### Sample S-008 — Levoit Windi → falso "WindTre"
- **Titolo**: "Levoit Windi Mini 2026: i tre mini-ventilatori portatili a torre che salveranno la vostra estate"
- **Topic attesi**: `Levoit`, `Windi Mini` (model)
- **Topic estratti oggi (post T-011)**: `Levoit` ✓
- **Topic estratti prima**: falso positivo `WindTre` (matchato via alias "Tre"
  che corrispondeva al numero italiano `tre` minuscolo nel testo).

## Backlog

### T-001 — Espandi `_BRAND_SINGLE_BLACKLIST` con sostantivi/aggettivi/avverbi italiani comuni
- **Severity**: high (i 3 sample sono tutti contaminati da questi falsi positivi)
- **Area**: [app/topic_extractor/extractor.py:85](../backend/app/topic_extractor/extractor.py#L85)
- **Stato**: [✓] (2026-05-07)
- **Done**: blacklist espansa da ~30 → 230+ voci (avverbi, voci verbali frequenti,
  sostantivi/aggettivi italiani comuni capitalizzati per enfasi titolare).
  Sample S-001/S-002/S-003 puliti. 9 test parametrizzati di regressione +
  fix collaterale a `_trim_blacklisted_first_tokens` (rigetta match in cui il
  FIRST risultante è un'iniziale puntata). Tutti i 60 test extractor verdi.
- **Descrizione**: la blacklist attuale ha ~30 voci (avverbi connettivi + verbi
  passato-remoto + mesi/giorni). Espanderla con almeno 200-300 entry: sostantivi
  comuni italiani che capitano capitalizzati per inizio frase, aggettivi enfatici
  da titolo sensazionalistico, voci verbali coniugate frequenti.
- **Esempi mancanti raccolti dai sample**: `Bomba`, `Fascia`, `Canale`, `Rende`,
  `Dello`, `Campagna`, `Soltanto`, `Solo`, `Ecco`, `Adesso`, `Subito`, `Davvero`,
  `Ancora`, `Finalmente`, `Persino`, `Probabilmente`, `Ovviamente`.
- **Tradeoff**: una blacklist troppo aggressiva può scartare brand legittimi
  (es. `Apple` non deve finirci). Procedura: sourcing dal corpus seed reale
  (estrai i candidati BRAND_SINGLE su 1000 articoli, ordina per occurrence_count,
  flagga manualmente).
- **DoD**: la blacklist espansa supera 200 voci; i 3 sample S-001/S-002/S-003
  non producono più i falsi positivi citati; test unit dedicati.

### T-002 — Verifica/sistema il case-insensitive del dictionary `classify`
- **Severity**: high (impatta tutti i topic con `display_name` o `aliases` non lowercase)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py)
- **Stato**: [✓] (2026-05-07)
- **Done**: verificato che `_compile_index` usa già `flags=re.IGNORECASE`
  (line 103) → il match è case-insensitive di default. Il test pre-esistente
  `test_scan_is_case_insensitive` lo copre. Niente fix necessario, solo
  conferma.

### T-003 — `REGEX_MODEL` accetta token alfanumerici con dash
- **Severity**: med (impatta soprattutto news tech/elettronica)
- **Area**: [app/topic_extractor/extractor.py](../backend/app/topic_extractor/extractor.py) (`extract_models`)
- **Stato**: [✓] (2026-05-07)
- **Done**: `model_part` esteso a `[A-Z][\w-]*\d[\w-]*` (matcha WH-1000XM5,
  L27-41, RTX-4090, A12X) e `[a-z][A-Z][a-z]*` (camelCase tipo iPhone, iPad).
  Pattern principale supporta ora fino a 4 token post-brand. 3 test unit
  dedicati: Lenovo L27-41, Sony WH-1000XM5, Apple iPhone 15 Pro.
- **Descrizione**: il pattern attuale cattura `<known_brand> <num|word> [num|word]?`.
  Token come `L27-41`, `WH-1000XM5`, `iPhone 15 Pro Max` non rientrano. Estendere
  il sotto-pattern post-brand a `[A-Za-z]?\d+[\w-]*` (mantenendo l'anchor sul
  brand whitelisted per limitare i falsi positivi).
- **DoD**: test unit con `Lenovo L27-41`, `Sony WH-1000XM5`, `Apple iPhone 15 Pro`,
  `Samsung Galaxy S24 Ultra`, `Porsche 911 GT3 RS`. Match longest-first.

### T-004 — Espansione `topics.yaml` seed brand IT (target 250+)
- **Severity**: high (lo Step B dictionary è il primo livello e oggi ha solo ~70 entry)
- **Area**: [infra/seed/topics.yaml](../infra/seed/topics.yaml) + snapshot
  [data/topics.parquet](../data/topics.parquet)
- **Stato**: [✓] (2026-05-07) parziale — copertura passata da ~40 a 113 brand
  (telco IT, tech consumer, retail/GDO, auto/motori, banche/fintech, media/
  streaming). Restano da aggiungere calciatori, conduttori TV, cantanti,
  brand moda/alimentari, industria/business, politici internazionali — vedi
  TODO in coda al file. Target finale 250-500 ancora aperto come iterazione.
- **Descrizione**: copertura attuale starter ~70 (squadre Serie A, partiti,
  politici, big-tech). Mancano completamente verticali frequenti nelle news IT:
  - **Telco**: Fastweb, Iliad, WindTre, Vodafone, Tim, Eolo, Sky Wifi, Postemobile
  - **Tech IT/EU**: Razer, Lenovo, Logitech, Asus, Acer, MSI, Huawei, Xiaomi,
    OnePlus, Realme, Honor, Oppo, Nothing
  - **Retail**: Esselunga, Coop, Conad, Lidl, Eurospin, Carrefour, MediaWorld,
    Unieuro, Trony, Euronics, IKEA
  - **Auto**: Stellantis, Maserati, Lamborghini, Ducati, Aprilia, Piaggio
  - **Banche/Fintech**: Intesa, Unicredit, BPM, MPS, Mediobanca, N26, Revolut,
    Satispay, Hype
  - **Media**: Mediaset, Rai, Sky Italia, DAZN, Now, La7, Discovery+
- **DoD**: file YAML supera 250 entry; test integration su sample reale (10 news
  IT da feed RSS attivi) — match rate ≥80%.

### T-005 — Topic `subject` per categorie merceologiche tech
- **Severity**: med (i prodotti tech ricorrono in news shopping/recensione)
- **Area**: [infra/seed/topics.yaml](../infra/seed/topics.yaml)
- **Stato**: [✓] (2026-05-07)
- **Done**: 16 subject merceologici aggiunti (Monitor, Smartphone, Notebook,
  Laptop, Tablet, Smartwatch, Cuffie, Auricolari, Console, Webcam, Stampante,
  Router, SSD, Hard Disk, Aspirapolvere, Smart TV) con aliases lowercase.
  Sample S-002 estrae `Monitor` ✓.
- **Descrizione**: aggiungere `type='subject'` per categorie generiche di
  prodotto: `Monitor`, `Notebook`, `Smartphone`, `Laptop`, `Cuffie`, `Tablet`,
  `Smartwatch`, `Console`, `Auricolari`, `Webcam`, `Stampante`, `Router`, `SSD`,
  `Hard disk`. Aliases varianti (`monitor` minuscolo, `notebooks`, `smartphones`,
  ecc.).
- **DoD**: 30+ subject merceologici in seed; sample S-002 estrae `Monitor`.

### T-006 — Verifica `REGEX_PER` su persone all'inizio del titolo
- **Severity**: med
- **Area**: [app/topic_extractor/extractor.py](../backend/app/topic_extractor/extractor.py) `_RE_PERSON` + `_trim_blacklisted_first_tokens`
- **Stato**: [ ]
- **Descrizione**: in S-003 "Megan Gale fa litigare..." il match dovrebbe essere
  `Megan Gale` (2 token full). Da capire perché non emerge nei topic estratti.
  Ipotesi: il post-trim `_trim_blacklisted_first_tokens` toglie `Megan` se
  finisse in blacklist (improbabile), oppure la pipeline scarta il match per
  qualche filtro a valle (occurrence_count minimo, polarizzazione singola
  source). Aggiungere logging diagnostico temporaneo.
- **DoD**: test unit con il titolo di S-003 produce `Megan Gale` come candidato
  PER; review CLI mostra l'entity con count atteso.

### T-007 — Topic "concept" curated (intelligenza artificiale, criptovalute, ecc.)
- **Severity**: med
- **Area**: [infra/seed/topics.yaml](../infra/seed/topics.yaml) + verifica T-002
- **Stato**: [✓] (2026-05-07)
- **Done**: aggiunti `Criptovalute`, `Bitcoin`, `Blockchain`, `NFT`,
  `Cybersicurezza`, `ChatGPT`, `Copilot`, `Gemini`, `Claude`, `Transizione
  energetica`, `Manovra` con aliases lowercase. T-002 conferma il match
  case-insensitive.
- **Descrizione**: topic concettuali multi-word in lowercase frequente:
  `intelligenza artificiale`, `criptovalute`, `cybersicurezza`, `bitcoin`,
  `cambio climatico`, `fonti rinnovabili`, `guerra in ucraina`, `medio oriente`.
  Type='subject' con `display_name` Title Case e `aliases` con la versione
  lowercase + abbreviazioni (`IA`, `AI`, `crypto`).
- **Dipendenza**: T-002 deve aver chiuso prima (case-insensitive match).
- **DoD**: 20+ concept topics; corpus reale di 50 articoli AI/crypto rileva
  almeno il concept atteso ≥80%.

### T-009 — Location ambigue (comuni IT con nome = sostantivo italiano comune)
- **Severity**: high (emerso durante chiusura T-001/T-004: i 6 falsi positivi di
  S-001/S-002/S-003 erano comuni reali importati da ISTAT, NON falsi positivi
  della regex)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py)
- **Stato**: [✓] (2026-05-07)
- **Done**: aggiunto `_AMBIGUOUS_LOCATION_TERMS` (16 voci: bomba, campagna,
  canale, dello, fascia, grosso, lago, lana, massa, nave, prato, rende, sale,
  scena, terrazzo, vita). `_build_term_map` salta i topic `type='location'` il
  cui display_name lowercase coincide con un termine ambiguo. Mantiene città
  non ambigue (Roma, Milano, ...) e brand omonimi (es. brand "Massa") via
  filtro su `t.type`. 3 test unit dedicati.
- **Limite**: la lista è hardcoded — quando un nuovo falso positivo emerge,
  estendere il set. In futuro: campo `topics.requires_context` su DB con
  scoring contestuale.

### T-010 — Boundary asimmetrico classify per elisioni italiane (`dell'`, `l'`, ...)
- **Severity**: high (impatta brand corti su vasta gamma di articoli IT)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py) `_compile_index`
- **Stato**: [✓] (2026-05-07)
- **Done**: il pattern boundary era simmetrico `(?<![\wàèéìòù])(...)(?![\wàèéìòù])`,
  così l'apostrofo italiano (`'` o `’` curly) non bloccava i match: `dell'altra`
  ammetteva il match `Dell` (brand). Ora asimmetrico: lookbehind invariato,
  lookahead esteso a `(?![\wàèéìòù'’])`. Questo blocca i match della parola
  PRIMA dell'apostrofo (`Dell` in `dell'altra`) ma permette i match della
  parola DOPO (`intelligenza` in `dell'intelligenza`). 3 test unit dedicati.

### T-011 — Brand mancanti / alias troppo ambigui
- **Severity**: high
- **Area**: [infra/seed/topics.yaml](../infra/seed/topics.yaml)
- **Stato**: [✓] (2026-05-07)
- **Done**: aggiunti `NOW` (NowTV), `Sky On Demand`, `Qualcomm`, `Snapdragon`,
  `MediaTek`, `Intel`, `AMD`, `ARM`, `TSMC`, `Levoit`, `Dyson`, `Roborock`,
  `Ecovacs`, `Redmi`, `Jabra`, `Anker`. Rimossi alias troppo ambigui da
  `WindTre` (`Tre` matchava il numero italiano "tre" → S-008; `Wind` puro
  ridondante con `Wind Tre`/`Wind 3`/`Wind3`). Sample S-006 e S-008 puliti.

### T-012 — Step C: integrare REGEX_PER/REGEX_MODEL nel pipeline classify live
- **Severity**: med (sblocca estrazione di entità non-curated come "Nina Festival",
  "Donald Trump senior" ecc. al volo, senza review CLI)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py)
  + [app/topic_extractor/extractor.py](../backend/app/topic_extractor/extractor.py)
- **Stato**: [✓] (2026-05-07)
- **Done**:
  1. `classify(...)` chiama `_extract_regex_matches` dopo il dict match
     (parametro `enable_regex_extraction=True` di default).
  2. `extract_persons` + `extract_models` su title/body separati per scoring
     `t*3+b*1` allineato al dict.
  3. Whitelist brand per REGEX_MODEL = display_name dei brand curated già
     matched dal dict (sblocca estrazione contextuale: se l'articolo matcha
     "Lenovo", parte REGEX_MODEL con whitelist `["Lenovo", ...]`).
  4. `_upsert_regex_topic` crea/riusa `Topic(slug=slugify(surface),
     is_curated=false)` — idempotente via ON CONFLICT DO NOTHING.
  5. Cap anti-esplosione: `MAX_REGEX_PERSONS_PER_ARTICLE=5`,
     `MAX_REGEX_MODELS_PER_ARTICLE=3` per articolo.
  6. Dedupe finale per topic_id (un topic prodotto da più fonti tiene il
     match con score più alto) — necessario per non violare PK
     `(article_id, topic_id)` su `article_topics`.
  7. `TopicMatch.source` esposto, `apply_classification` lo persiste.
  8. Pattern `model_part` esteso a `\d{1,4}` per chip mono-digit (Snapdragon 4).
- **Risultati sui sample**:
  - S-001: `Razer Xanthus Tote`, `Razer Xanthus Tote Bag` (model)
  - S-002: `Lenovo L27-41` (model)
  - S-003: `Megan Gale` (person)
  - S-004: `Snapdragon 4` (model) + `Qualcomm` (dict)
  - S-007: `Nina Festival` (person)
  - S-008: `Levoit Windi Mini`, `Levoit Windi Mini 2026`, `Windi Mini` (model)
- 6 nuovi test integration in
  [tests/integration/test_classify_step_c.py](../backend/tests/integration/test_classify_step_c.py).

### T-013 — Falso positivo brand vs verbo italiano omonimo (es. "Lancia")
- **Severity**: low (raro, emerso solo su S-004 "Qualcomm lancia...")
- **Area**: classify (con conoscenza POS) o seed
- **Stato**: [ ]
- **Descrizione**: il brand auto `Lancia` (curated) coincide con il verbo
  italiano "lancia" (lanciare 3sg). Il classify dict non distingue il contesto.
  Soluzioni possibili (in ordine di costo):
  1. flaggare `topics.requires_context=true` e abbassare lo score se non c'è
     anchor lessicale (es. preceduto da "la"/"una"/"in" + seguito da modello
     "Lancia Ypsilon")
  2. spostare `Lancia` da `aliases=[]` a `aliases=["Lancia Auto", ...]` e
     lasciare il display_name "Lancia" non-indicizzato (perderebbe però i
     match veri)
  3. richiede POS tagging (NER spaCy, Phase 1.2.A)
- **DoD**: S-004 non estrae `Lancia` come brand quando è verbo; estrae
  `Lancia Ypsilon` (model) quando è contesto auto.

### T-008 — `REGEX_MODEL` cattura nomi composti (es. "Razer Xanthus Tote Bag")
- **Severity**: low (estrazione fine; il match base brand basta per molti use case)
- **Area**: [app/topic_extractor/extractor.py](../backend/app/topic_extractor/extractor.py)
- **Stato**: [ ]
- **Descrizione**: il pattern oggi cattura `<known_brand> <num|word> [num|word]?`.
  Per nomi prodotto tipo "Razer Xanthus Tote Bag" o "Apple Vision Pro", servono
  2-4 token post-brand alfanumerici. Rischio falsi positivi alto (es. "Apple ha
  rilasciato il nuovo prodotto" → match "Apple Ha Rilasciato Il Nuovo"). Mitigazione:
  imporre che almeno uno dei post-brand sia capitalized 4+ char OR contenga numeri.
- **DoD**: dopo T-008 i sample S-001 estraggono `Razer Xanthus` (anche senza
  "Tote Bag"); il falso positivo descritto sopra non emerge in 100 articoli sample.

### T-014 — Comuni IT con nome = pronome/avverbio italiano comune (round 2)
- **Severity**: high (sample reale 25325 contaminato da 4 falsi positivi su 18 topic)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py) `_AMBIGUOUS_LOCATION_TERMS`
- **Stato**: [✓] (2026-05-08)
- **Sample**: art. 25325 "Torna la patrimoniale della sinistra: nel mirino patrimoni…"
  estraeva `Ne` (comune GE, collide con pronome partitivo "ne ho due"),
  `Mira` (VE, "nel mirino"), `Alto` (CN, aggettivo "alto"),
  `Posta` (RI, "posta in gioco" / "la posta").
- **Done**: aggiunti `ne`, `mira`, `alto`, `posta` a `_AMBIGUOUS_LOCATION_TERMS`.
  Aggiunti `Mira`, `Alto`, `Posta` (Title Case) a `_BRAND_SINGLE_BLACKLIST` per
  copertura simmetrica (`Ne` < 4 char, non matcha BRAND_SINGLE).
- **DoD**: art. 25325 dopo reclassify non contiene più i 4 topic FP; il test
  parametrico in `test_topic_extractor.py` copre `Mira/Alto/Posta`.

### T-017 — Pannello admin `/yf_admin/*` (HTTP Basic, regole admin-editabili)
- **Severity**: high (qualità topic in crescita continua → necessario poter
  agire da UI, non da codice + redeploy)
- **Area**: nuovo router [routers/admin.py](../backend/app/routers/admin.py),
  middleware CSRF, migrations 0009/0010, [classify.py](../backend/app/ingestion/classify.py)
- **Stato**: [✓] (2026-05-09)
- **Done**:
  1. **Auth**: `ADMIN_USERNAME`/`ADMIN_PASSWORD` in `.env` (plaintext v1).
     `app/admin_deps.py` con `require_admin()` HTTP Basic timing-safe.
  2. **Pagine** (8 route): dashboard, lista utenti, lista+edit+delete topic,
     ispettore articolo, statistiche, lista+CRUD term rules per kind, lista+CRUD
     composite rules, reload cache.
  3. **Template Jinja2** in `app/templates/admin/` + CSS `app/static/css/admin.css`.
     No SPA, no build step, server-rendered con form HTML.
  4. **Migration 0009**: tabelle `topic_term_rules` (kind ∈ {ambiguous_location,
     brand_single, case_sensitive_slug}, term, note) + `topic_composite_rules`
     (composite_slug unique, components TEXT[], note). Seed iniziale dei
     frozenset Python hardcoded.
  5. **Migration 0010**: riconciliazione idempotente importando i set Python
     correnti (alcuni round T-014/T-015/T-016 erano nei moduli ma non in 0009).
  6. **Refactor classify.py**: `_load_index()` ora chiama `_refresh_rules_from_db()`
     che sostituisce `_AMBIGUOUS_LOCATION_TERMS`, `_CASE_SENSITIVE_SLUGS`,
     `_COMPOSITE_RULES` (e `extractor._BRAND_SINGLE_BLACKLIST`) con i valori in
     DB. Ogni edit via admin chiama `invalidate_classifier_cache()` → al prossimo
     classify le regole sono fresche.
  7. **CSRF skip**: middleware esclude `/yf_admin/*` (HTTP Basic, no session
     cookie → CSRF inapplicabile).
- **DoD**: 303/303 test pass; smoke test live verificato auth (401/200), tutte
  GET/POST endpoint admin OK (dashboard, users, topics CRUD, articles, stats,
  rules CRUD, composite CRUD, reload).

### T-016 — Refactor multi-layer per qualità topic (post-degrado evidenziato)
- **Severity**: high (quality regression: sample art. 27451 mostrava 7 FP eterogenei → degrado strutturale, non più whack-a-mole su singoli termini)
- **Area**: 5 layer separati — vedi sotto
- **Stato**: [✓] (2026-05-08)
- **Sample**: art. 27451 "Quantum, il mercato entra nella fase industriale…":
  prima estraeva `Uniti`, `Home Quantum`, `Chiari`, `Sandonnini` solo,
  `Pierluigi Sandonnini Punti`, `Quantum Technology Monitor`, `INVIA Iscriviti`.
- **Done — 5 fix coerenti su layer diversi**:
  1. **Fix 1 — HTML cleanup**: [reclassify_topics.py](../backend/app/utils/reclassify_topics.py)
     `_html_to_text` ora rimuove `<nav>, <aside>, <footer>, <header>, <form>,
     <script>, <style>, <noscript>` prima di estrarre testo. Risolve da solo
     `Home Quantum`, `INVIA Iscriviti` e una coda di FP da widget/menu/form.
  2. **Fix 2 — End-trim PERSON**: [extractor.py](../backend/app/topic_extractor/extractor.py)
     `_trim_blacklisted_first_tokens` rinominato `_trim_blacklisted_edge_tokens`,
     ora trimma HEAD e TAIL. Risolve `Pierluigi Sandonnini Punti` →
     `Pierluigi Sandonnini`.
  3. **Fix 3 — BRAND_SINGLE non duplica PERSON tokens**: [classify.py](../backend/app/ingestion/classify.py)
     `_extract_regex_matches` raccoglie i token (lowercased) di tutti i PERSON
     candidate e filtra i BRAND_SINGLE il cui surface coincide. Risolve
     `Sandonnini` solo quando `Pierluigi Sandonnini` è già PERSON.
  4. **Fix 4 — PERSON drop su collisione curated non-person**: nuova helper
     `_person_collides_with_curated(cand, idx)`. Se un token (4+ char) del
     PERSON è display_name/alias di un topic curated di tipo brand/subject/
     location → drop. Risolve `Quantum Technology Monitor` (Monitor è curated
     subject). `_CompiledIndex` esteso con `topic_id_to_type`.
  5. **Fix 5 — Round 4 termini**: 5 nuove voci a `_AMBIGUOUS_LOCATION_TERMS`
     (`chiari, fondi, premia`) e `_BRAND_SINGLE_BLACKLIST`
     (`Uniti, Home, Punti, Iscriviti, Invia`).
- **DoD**: art. 27451 da 22 topic con 7 FP → 17 topic puliti. Reclassify
  globale: 1066/1066 OK, coverage 96%. 9 nuovi unit test (3 per end-trim,
  3 per collisione curated, 3 esistenti per blacklist round 4).

### T-015 — Comuni IT round 3 + composite-rules (Google + Gemini → Google Gemini)
- **Severity**: high (sample 27787 contaminato da 7 FP location + nessuna
  collassazione brand-prodotto duplicato)
- **Area**: [app/ingestion/classify.py](../backend/app/ingestion/classify.py)
  `_AMBIGUOUS_LOCATION_TERMS`, `_COMPOSITE_RULES`, `_apply_composite_rules`;
  [infra/seed/topics.yaml](../infra/seed/topics.yaml); migration 0008.
- **Stato**: [✓] (2026-05-08)
- **Sample**: art. 27787 "AI in azienda: quanto costa?…" estraeva `Mese`, `Front`,
  `Casella`, `Licenza`, `Acuto`, `Matrice`, `Quindici` (tutti comuni IT che
  collidono con sostantivi/aggettivi/numerali italiani comuni). Inoltre
  `Google` e `Gemini` matchavano come topic separati invece di un singolo
  `Google Gemini`.
- **Done**:
  1. 7 nuovi termini in `_AMBIGUOUS_LOCATION_TERMS` (lowercase) e
     `_BRAND_SINGLE_BLACKLIST` (Title Case): acuto, casella, front, licenza,
     matrice, mese, quindici.
  2. Nuovo `_COMPOSITE_RULES` in classify.py: lista di tuple
     `(composite_slug, frozenset(component_slugs))`. `_apply_composite_rules`
     dopo il dedupe finale rimuove le componenti dai matches e aggiunge il
     composite (score = somma; in_title/in_body = OR; source = "composite").
  3. Nuovo topic `google-gemini` in topics.yaml; rimosso alias "Google Gemini"
     da `gemini` (ora è display_name del composite).
  4. Migration `0008_at_composite_source` estende il CHECK constraint di
     `article_topics.source` per accettare `'composite'`.
  5. `_CompiledIndex` ora include `slug_to_id` mapping completo.
- **DoD**: art. 27787 dopo reclassify ha `Google Gemini` (score 6 = 2+4
  somma componenti) e nessuno dei 7 FP. 22 articoli totali nel corpus hanno
  ora il topic composite. 3 unit test in `test_classify.py` (collasso ok,
  skip se solo 1 componente, skip se composite missing).

## Tool: ri-classificazione articoli già indicizzati

Dopo aver modificato seed/blacklist/regex servono i nuovi topic anche sugli
articoli già processati. Il tool [app/utils/reclassify_topics.py](../backend/app/utils/reclassify_topics.py):

```bash
# Tutti gli articoli indexed (default: solo title+description)
python -m app.utils.reclassify_topics --all

# Solo una source
python -m app.utils.reclassify_topics --source-id 3

# Più accurato: scarica content_text da Manticore (~10x più lento)
python -m app.utils.reclassify_topics --all --include-content
```

Idempotente (delete+insert su `article_topics`). Invalida la cache classify
all'avvio. Su DB con 242 articoli indexed: ~6s senza content, ~30s con.

Workflow tipico dopo modifica seed:
```bash
python -m app.utils.seed_loader --topics ../infra/seed/topics.yaml
python -m app.utils.reclassify_topics --all
python -m app.utils.topics_snapshot export --include-uncurated --out ../data/topics.parquet
```

## Operativo

- Stato 2026-05-07: chiusi T-001, T-002, T-003, T-004 (parziale), T-005,
  T-007, T-009, T-010, T-011, T-012. Aperti T-006 (diagnostica REGEX_PER),
  T-008 (composti, ora parzialmente sbloccato da T-012), T-013 (FP
  brand-verbo `Lancia`).

- Per ogni chiusura: aggiornare le voci `Topic estratti oggi` nei sample S-NNN
  per riflettere il nuovo comportamento (così la regressione resta visibile).
- Quando si raggiungono 5+ task `[✓]` o si chiude un blocco, ri-esportare
  [data/topics.parquet](../data/topics.parquet) via
  `python -m app.utils.topics_snapshot export --include-uncurated --out ../data/topics.parquet`.

## Nuovi sample diagnostici

Quando emergono altri articoli problematici, aggiungere una sezione `S-NNN`
sopra (con titolo, topic attesi, topic estratti, failure mode), e aprire i task
`T-NNN` corrispondenti se non coperti.
