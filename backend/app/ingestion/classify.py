"""Classificazione articolo -> lista di topic_id.

v1.0: matching dictionary-based contro `topics.aliases` + display_name.
Niente NER spaCy (rinviato a v1.2). Niente LLM fallback (v1.2).

Strategia:
- carichiamo in memoria una mappa `pattern -> topic_id` partendo da Topic.aliases
  + display_name, usando word-boundary regex case-insensitive
- ogni topic accumula uno score = (#match in title)*3 + (#match in body)*1
- ritorniamo i topic con score >= MIN_SCORE, ordinati desc

La mappa è cached per processo: i topics curati cambiano raramente. Una
chiamata `invalidate_classifier_cache()` permette ai test/admin di forzare
il reload.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, TopicCompositeRule, TopicTermRule
from app.topic_extractor import extractor as ex_module
from app.topic_extractor.extractor import (
    Candidate,
    extract_brand_single,
    extract_models,
    extract_persons,
)
from app.topic_extractor.extractor import normalize as ex_normalize
from app.utils.slugify import slugify

log = structlog.get_logger()

MIN_SCORE = 1

# Cap anti-esplosione per articolo della Step C (regex extractor live).
# Sufficiente per news IT tipiche (titolo 60-90 char + descrizione 200-400):
# raramente compaiono più di 3-4 persone/2-3 modelli in un singolo articolo.
# Per BRAND_SINGLE il cap è più stretto perché il pattern è più permissivo
# (qualsiasi parola Title Case 4+ char in mid-sentence non in blacklist).
MAX_REGEX_PERSONS_PER_ARTICLE = 5
MAX_REGEX_MODELS_PER_ARTICLE = 3
MAX_REGEX_BRANDS_PER_ARTICLE = 2
# Step D NER (spaCy) — cap conservativi, le entità sono concentrate nel titolo
MAX_NER_PERSONS_PER_ARTICLE = 5
MAX_NER_ORGS_PER_ARTICLE = 3
MAX_NER_LOCATIONS_PER_ARTICLE = 3

# Comuni italiani con nome che coincide con sostantivi/aggettivi italiani comuni:
# Bomba (CH), Campagna (SA), Canale (CN), Dello (BS), ecc. Sono `topics(type=location,
# is_curated=true)` legittimi (presi da ISTAT), ma il loro `display_name` lowercase
# come termine puro è troppo ambiguo per il dictionary classify (matchano news di
# e-commerce, cronaca generica, recensioni). Skip dal term map: per news realmente
# legate a quei comuni, l'extractor REGEX o un match contestuale ("comune di
# Bomba", "a Bomba (CH)") andranno gestiti separatamente (workstream T-009).
#
# La lista è chiusa: aggiungerla quando emerge un nuovo falso positivo. NON
# include città/capoluoghi rilevanti (Roma, Milano, ...) che hanno legittima
# polisemia coperta da topic separati per type.
# Default seed: viene sostituito a runtime da `_load_index()` con i valori in DB
# (tabella `topic_term_rules`). Restano qui solo come fallback in caso di DB
# mancante / migration non applicata. Per editare le regole usa l'admin
# `/yf_admin/rules`.
_AMBIGUOUS_LOCATION_TERMS: set[str] = set(
    {
        "bomba", "campagna", "canale", "dello", "fascia", "grosso",
        "lago", "lana", "massa", "nave", "norma", "ora", "prato",
        "rende", "sale", "scala", "scena", "terrazzo", "ultimo", "vita",
        # Sostantivi giornalistici/finanziari italiani capitati come comuni:
        # Fonte (TV), Fonti (FE), Sostegno (BI). Sempre falsi positivi.
        "fonte", "fonti", "sostegno",
        # La Cassa (TO) — collide col sostantivo "cassa" preceduto da articolo.
        "la cassa",
        # Round 2 (T-014, sample art. 25325):
        # Ne (GE) = pronome partitivo, Mira (VE) = "nel mirino" / verbo,
        # Alto (CN) = aggettivo, Posta (RI) = "posta in gioco" / "la posta".
        "ne", "mira", "alto", "posta",
        # Round 3 (T-015, sample art. 27787):
        # Acuto (FR) = aggettivo "acuto", Casella (GE) = "casella di posta",
        # Front (TO) = sostantivo inglese, Licenza (RM) = "licenza software",
        # Matrice (CB) = sostantivo "matrice", Mese (SO) = "mese" sostantivo,
        # Quindici (AV) = numerale "quindici".
        "acuto", "casella", "front", "licenza", "matrice", "mese", "quindici",
        # Round 4 (T-016, sample art. 27451):
        # Chiari (BS) = aggettivo plurale, Fondi (LT) = "fondi" investimenti,
        # Premia (TO) = verbo 3sg di "premiare".
        "chiari", "fondi", "premia",
        # Round 5: Paese (TV) = "il Paese" sostantivo, Siano (SA) = congiuntivo
        # "siano" 3pl di "essere".
        "paese", "siano",
    }
)

# Topic con `display_name` che coincide con un verbo/sostantivo italiano
# omonimo. Per questi serve match CASE-SENSITIVE (testo con capitalizzazione
# esatta) invece del default case-insensitive: "Lancia" Title Case = brand auto;
# "lancia" lowercase = verbo "lanciare" 3sg → da NON matchare.
# La lista è chiusa, basata sui sample reali (T-013).
# Default seed: sostituito da DB in `_load_index()` (vedi note sopra).
_CASE_SENSITIVE_SLUGS: set[str] = set(
    {
        # Brand auto / motori vs verbi italiani omonimi
        "lancia",     # brand auto vs verbo "lanciare" 3sg
        "lanciano",   # comune CH vs verbo "lanciare" 3pl
        "vespa",      # brand vs sostantivo "vespa" (insetto)
        "panda",      # brand auto Fiat vs animale
        "bologna",    # brand calcio vs città (location separata)
        "rai",        # brand TV — matcha "rai" lowercase nel parlato
        "tim",        # brand telco vs nome inglese "Tim"
        "lega",       # partito vs verbo "legare" 3sg
        # Comuni/sostantivi italiani omonimi
        "alba",       # comune CN vs sostantivo "alba" (sorgere del sole)
        "noto",       # comune SR vs aggettivo "noto" (conosciuto)
        "capaci",     # comune PA (strage) vs aggettivo "capaci" plurale
        # Partiti con alias all-caps brevi (FI, PD, M5S, ...): in case-insensitive
        # matchano substring tipo "Wi-Fi" → "FI" → falso positivo Forza Italia.
        # Rendiamo case-sensitive l'intero topic (incluso display_name).
        "forza-italia",
        "pd",
        "m5s",
        "fratelli-d-italia",       # alias "FdI"
        "alleanza-verdi-sinistra", # alias "AVS"
        "italia-viva",             # alias "IV"
        "azione",                  # display "Azione" vs verbo
        # Tecnologie con sigla tutta maiuscola (OLED, LED, ...) — devono matchare
        # solo all-caps. La forma minuscola "led" è il participio passato di
        # "leggere" o nome cognome breve.
        "oled", "led", "microled", "mini-led", "lcd", "4k", "8k",
        # Sigle istituzionali con alias short (UN, UE, EU, ...) — il match
        # case-insensitive farebbe collidere "un" articolo italiano con alias
        # ONU="UN", e "ue" desinenza italiana con alias Europa="UE".
        "onu", "europa", "bce", "nato", "ocse",
    }
)


@dataclass(frozen=True)
class TopicMatch:
    topic_id: int
    score: float
    in_title: bool
    in_body: bool
    source: str = "dict"  # 'dict' | 'regex'

    @property
    def position(self) -> str:
        if self.in_title and self.in_body:
            return "both"
        if self.in_title:
            return "title"
        return "body"


@dataclass
class _CompiledIndex:
    """Cache delle regex compilate. Due indici separati: case-insensitive
    (default per la maggioranza dei topic) e case-sensitive (per i topic
    omonimi con verbi/sostantivi italiani — vedi `_CASE_SENSITIVE_SLUGS`).

    `slug_to_id` è una mappa completa di tutti i topic curated, usata da
    `_apply_composite_rules` per collassare componenti in un topic sintetico.
    """

    pattern_ci: re.Pattern[str]
    term_to_topics_ci: dict[str, list[int]]
    pattern_cs: re.Pattern[str] | None
    term_to_topics_cs: dict[str, list[int]]
    slug_to_id: dict[str, int]
    # Mappa topic_id → type (brand/person/subject/location/model). Usata da
    # `_person_collides_with_curated` per scartare PERSON candidates
    # contaminati da token curated non-person.
    topic_id_to_type: dict[int, str]
    # Mappa topic_id → tokens(display_name) lowercase. Usata da
    # `_apply_subsumption` per assorbire match brand/short se contenuti come
    # sotto-sequenza contigua nei token di un match più specifico (es.
    # "Sony" assorbito da "Sony Xperia 1 VIII", "Xperia" idem).
    topic_id_to_tokens: dict[int, tuple[str, ...]]


_CACHE: _CompiledIndex | None = None


# Composite rules: se TUTTI gli slug in `components` matchano in un articolo,
# vengono rimossi dal risultato e sostituiti dal topic con slug `composite`.
# Lo `composite` deve esistere nel DB come topic curated (da topics.yaml).
# Score combinato = somma degli score componenti (più segnali → più rilevanza).
# Default seed: sostituito da DB in `_load_index()`.
_COMPOSITE_RULES: list[tuple[str, frozenset[str]]] = [
    ("google-gemini", frozenset({"google", "gemini"})),
]


def _normalize_term(s: str) -> str:
    """Lowercase + strip + collapse whitespace. Niente accent-fold (l'italiano
    li conserva: "perché" != "perche")."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _build_term_maps(
    topics: Iterable[Topic],
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Costruisce due mappe term -> [topic_id, ...]:
    - `term_map_ci`: termini lowercase per match case-insensitive (default)
    - `term_map_cs`: termini con capitalizzazione originale per match case-sensitive
      (solo per topic con slug in `_CASE_SENSITIVE_SLUGS`)
    """
    out_ci: dict[str, list[int]] = {}
    out_cs: dict[str, list[int]] = {}
    for t in topics:
        candidates: list[str] = []
        if t.display_name:
            candidates.append(t.display_name)
        for a in t.aliases or []:
            if a:
                candidates.append(a)
        is_location = (t.type == "location")
        is_case_sensitive = (t.slug in _CASE_SENSITIVE_SLUGS)
        for raw in candidates:
            if is_case_sensitive:
                # Mantieni capitalizzazione originale: solo "Lancia" matcha,
                # non "lancia". Niente lowercase, niente normalize.
                term = raw.strip()
                if not term or len(term) < 2:
                    continue
                out_cs.setdefault(term, []).append(int(t.id))
            else:
                term = _normalize_term(raw)
                if not term or len(term) < 2:
                    continue
                # Skip comuni con nome ambiguo (vedi _AMBIGUOUS_LOCATION_TERMS):
                # display_name lowercase troppo collidente con sostantivi italiani.
                if is_location and term in _AMBIGUOUS_LOCATION_TERMS:
                    continue
                out_ci.setdefault(term, []).append(int(t.id))
    return out_ci, out_cs


# Back-compat: il modulo storicamente esponeva `_build_term_map`. Lo manteniamo
# come thin wrapper così i test esistenti su una sola mappa continuano a girare.
def _build_term_map(topics: Iterable[Topic]) -> dict[str, list[int]]:
    out_ci, out_cs = _build_term_maps(topics)
    # Merge: i termini case-sensitive sono inseriti col loro term-as-is.
    merged = dict(out_ci)
    for k, v in out_cs.items():
        merged.setdefault(k, []).extend(v)
    return merged


_NEVER_MATCH = re.compile(r"(?!x)x")
_TYPOGRAPHIC_QUOTE = "’"  # RIGHT SINGLE QUOTATION MARK
_BOUNDARY_LOOKAHEAD = r"\wàèéìòù'" + _TYPOGRAPHIC_QUOTE


# Articoli con questi termini nel titolo sono affiliate/commerciali
# (recensioni offerte, listing prodotti) e inquinano il grafo topic con
# brand/modelli senza rilevanza giornalistica → skip totale dell'estrazione.
_TITLE_SKIP_PATTERN = re.compile(
    r"\b(offerta|offerte)\b",
    re.IGNORECASE,
)


def _compile_one(term_map: dict[str, list[int]], *, ignore_case: bool) -> re.Pattern[str]:
    if not term_map:
        return _NEVER_MATCH
    sorted_terms = sorted(term_map.keys(), key=len, reverse=True)
    escaped = [re.escape(t) for t in sorted_terms]
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(
        r"(?<![\wàèéìòù])(" + "|".join(escaped) + rf")(?![{_BOUNDARY_LOOKAHEAD}])",
        flags=flags,
    )


def _compile_index(
    term_map: dict[str, list[int]] | None = None,
    term_map_cs: dict[str, list[int]] | None = None,
    slug_to_id: dict[str, int] | None = None,
    topic_id_to_type: dict[int, str] | None = None,
    topic_id_to_tokens: dict[int, tuple[str, ...]] | None = None,
) -> _CompiledIndex:
    """Compila due regex separate: case-insensitive (default) + case-sensitive
    (per topic con omonimia verbo italiano: vedi `_CASE_SENSITIVE_SLUGS`).

    Boundary asimmetrico per gestire le elisioni italiane (dell', l', un',
    sull'):
      - lookbehind: blocca solo \\w + accenti italiani — NON l'apostrofo
        (parole DOPO un'elisione devono potersi matchare: dell'intelligenza)
      - lookahead: blocca anche apostrofo `'` + curly `’` (parole PRIMA di
        un'elisione NON devono matchare: dell'altra non matcha brand `Dell`)

    Argomenti: `term_map` è il dict ci (case-insensitive). `term_map_cs` è il
    case-sensitive (None se nessun topic case-sensitive). `slug_to_id` mappa
    slug → topic_id per le composite rules. Per back-compat il primo
    parametro è ancora chiamato `term_map`.
    """
    ci_map = term_map or {}
    cs_map = term_map_cs or {}
    pattern_ci = _compile_one(ci_map, ignore_case=True)
    pattern_cs = _compile_one(cs_map, ignore_case=False) if cs_map else None
    return _CompiledIndex(
        pattern_ci=pattern_ci,
        term_to_topics_ci=ci_map,
        pattern_cs=pattern_cs,
        term_to_topics_cs=cs_map,
        slug_to_id=slug_to_id or {},
        topic_id_to_type=topic_id_to_type or {},
        topic_id_to_tokens=topic_id_to_tokens or {},
    )


async def _load_index(session: AsyncSession) -> _CompiledIndex:
    global _CACHE, _COMPOSITE_RULES
    if _CACHE is not None:
        return _CACHE
    # Carica regole admin-editabili dal DB e sostituisci i set/list module-level.
    await _refresh_rules_from_db(session)
    # Escludi topic con type='invalid' (marcati come non-topic in admin):
    # non devono essere matching candidates anche se erano is_curated.
    rows = (
        await session.execute(
            select(Topic)
            .where(Topic.is_curated == True)  # noqa: E712
            .where(Topic.type != "invalid")
        )
    ).scalars().all()
    term_map_ci, term_map_cs = _build_term_maps(rows)
    slug_to_id = {row.slug: int(row.id) for row in rows if row.slug}
    topic_id_to_type = {int(row.id): row.type for row in rows if row.type}
    topic_id_to_tokens = {
        int(row.id): tuple((row.display_name or "").lower().split())
        for row in rows
        if row.display_name
    }
    _CACHE = _compile_index(
        term_map_ci, term_map_cs, slug_to_id, topic_id_to_type, topic_id_to_tokens
    )
    log.info(
        "yf.classify.index_built",
        topics=len(rows),
        terms_ci=len(term_map_ci),
        terms_cs=len(term_map_cs),
        ambiguous_terms=len(_AMBIGUOUS_LOCATION_TERMS),
        case_sensitive_slugs=len(_CASE_SENSITIVE_SLUGS),
        composite_rules=len(_COMPOSITE_RULES),
    )
    return _CACHE


async def _refresh_rules_from_db(session: AsyncSession) -> None:
    """Sostituisce i set/list `_AMBIGUOUS_LOCATION_TERMS`,
    `_CASE_SENSITIVE_SLUGS`, `_COMPOSITE_RULES` (e
    `extractor._BRAND_SINGLE_BLACKLIST`) con i valori in DB.

    Se le tabelle non esistono ancora (migration 0009 non applicata) fallback
    silenzioso ai default hardcoded.
    """
    global _COMPOSITE_RULES
    try:
        rows = (
            await session.execute(select(TopicTermRule.kind, TopicTermRule.term))
        ).all()
    except Exception as e:  # tabella mancante (test legacy, db fresh)
        log.debug("yf.classify.rules_skip", error=str(e))
        return

    # Group by kind
    ambiguous = {r[1].lower() for r in rows if r[0] == "ambiguous_location"}
    brand_single = {r[1] for r in rows if r[0] == "brand_single"}
    case_sensitive = {r[1] for r in rows if r[0] == "case_sensitive_slug"}

    if ambiguous:
        _AMBIGUOUS_LOCATION_TERMS.clear()
        _AMBIGUOUS_LOCATION_TERMS.update(ambiguous)
    if case_sensitive:
        _CASE_SENSITIVE_SLUGS.clear()
        _CASE_SENSITIVE_SLUGS.update(case_sensitive)
    if brand_single:
        # `extractor._BRAND_SINGLE_BLACKLIST` è frozenset → sostituisco il
        # binding nel modulo `extractor` con un nuovo frozenset (i call site
        # leggono via `ex_module._BRAND_SINGLE_BLACKLIST` o via `in` su
        # set-as-is, entrambi indipendenti dall'identità dell'oggetto).
        ex_module._BRAND_SINGLE_BLACKLIST = frozenset(brand_single)

    composite_rows = (
        await session.execute(
            select(
                TopicCompositeRule.composite_slug,
                TopicCompositeRule.components,
            )
        )
    ).all()
    if composite_rows:
        _COMPOSITE_RULES = [
            (slug, frozenset(components)) for slug, components in composite_rows
        ]


def invalidate_classifier_cache() -> None:
    """Forza il reload al prossimo `classify(...)`. Da chiamare dopo che
    l'admin ha modificato `topics`. Invalida anche la cache IDF dei topic
    usata da `articles_service.related_articles`: dopo una moderazione
    massiva i pesi inverse-doc-freq possono essere obsoleti."""
    global _CACHE
    _CACHE = None
    # Import locale per evitare ciclo articles_service -> ingestion -> ...
    from app.services import articles_service
    articles_service.invalidate_topic_idf_cache()


def _scan(text: str, idx: _CompiledIndex) -> dict[int, int]:
    """Ritorna topic_id -> count di match nel testo. Scan separato per i due
    indici: case-insensitive normalizza il termine in lowercase, case-sensitive
    no (matcha solo "Lancia" maiuscolo, non "lancia").

    Append di uno spazio finale al testo: garantisce che i lookahead (`\b`,
    boundary) abbiano sempre un carattere "non-word" da consumare, anche per
    nomi a fine titolo (es. "Annunciato Snapdragon 4" — Snapdragon 4 è
    l'ultimo token).
    """
    if not text:
        return {}
    # Normalizza apostrofo curly (U+2019) → straight ('), così termini come
    # "Giro d'Italia" matchano sia in testi con apostrofo tipografico ’ sia
    # con quello ASCII. Il lookahead boundary include comunque entrambe le
    # forme (vedi _BOUNDARY_LOOKAHEAD).
    text = text.replace("’", "'") + " "
    counts: dict[int, int] = {}
    # Case-insensitive (default per la maggioranza dei topic)
    for m in idx.pattern_ci.finditer(text):
        term = _normalize_term(m.group(1))
        for tid in idx.term_to_topics_ci.get(term, []):
            counts[tid] = counts.get(tid, 0) + 1
    # Case-sensitive (Lancia, Vespa, Lanciano, ...)
    if idx.pattern_cs is not None:
        for m in idx.pattern_cs.finditer(text):
            term = m.group(1)  # NO normalize: case preservato
            for tid in idx.term_to_topics_cs.get(term, []):
                counts[tid] = counts.get(tid, 0) + 1
    return counts


async def classify(
    session: AsyncSession,
    *,
    title: str,
    body_text: str,
    origin_taxonomy: list[str] | None = None,
    enable_regex_extraction: bool = True,
    enable_ner_extraction: bool = True,
) -> list[TopicMatch]:
    """Ritorna la lista di TopicMatch per (title, body).

    Step B (`source='dict'`): match dictionary contro topic curated.
    Step C (`source='regex'`): se `enable_regex_extraction=True`, estrae
    persone via REGEX_PER e modelli via REGEX_MODEL (con whitelist brand
    derivata dai dict match) e crea/riusa topic `is_curated=false`.
    Step D (`source='ner'`): se `enable_ner_extraction=True`, estrae PER/
    ORG/LOC via spaCy `it_core_news_lg` **solo sul titolo** (coerente con
    policy title-only T-018) e crea/riusa topic `is_curated=false`. Le
    deduplicazioni per slug fanno sì che entità già coperte da dict/regex
    non producano duplicati.
    """
    idx = await _load_index(session)
    title_text = title or ""
    body_text = body_text or ""

    # Skip totale per articoli affiliate/commerciali: titolo con
    # "offerta"/"offerte" → niente estrazione (inquinano il grafo).
    if _TITLE_SKIP_PATTERN.search(title_text):
        log.info("yf.classify.title_skip", title=title_text[:80])
        return []

    title_counts = _scan(title_text, idx)
    body_counts = _scan(body_text, idx)

    # Boost da origin_taxonomy: ogni termine è scansionato come fosse body.
    if origin_taxonomy:
        tax_blob = " ".join(origin_taxonomy)
        tax_counts = _scan(tax_blob, idx)
        for tid, n in tax_counts.items():
            body_counts[tid] = body_counts.get(tid, 0) + n  # boost incremental

    all_ids = set(title_counts) | set(body_counts)
    out: list[TopicMatch] = []
    for tid in all_ids:
        t_count = title_counts.get(tid, 0)
        b_count = body_counts.get(tid, 0)
        score = t_count * 3.0 + b_count * 1.0
        if score < MIN_SCORE:
            continue
        out.append(
            TopicMatch(
                topic_id=tid,
                score=score,
                in_title=t_count > 0,
                in_body=b_count > 0,
                source="dict",
            )
        )

    # Step C — regex extractor live (T-012). I topic prodotti sono is_curated=false.
    if enable_regex_extraction:
        # Brand curated già matched dal dict → known_brands per REGEX_MODEL.
        # Se nessun brand match, REGEX_MODEL non gira (richiede whitelist).
        matched_topic_ids = list(all_ids) if all_ids else []
        known_brands = await _known_brand_names(session, matched_topic_ids)
        regex_matches = await _extract_regex_matches(
            session,
            title=title_text,
            body=body_text,
            known_brands=known_brands,
            idx=idx,
        )
        out.extend(regex_matches)

    # Step D — NER spaCy live (Phase 1.2.A). Solo titolo (policy T-018).
    if enable_ner_extraction and title_text:
        ner_matches = await _extract_ner_matches(session, title=title_text, idx=idx)
        out.extend(ner_matches)

    # Dedupe finale per topic_id: lo stesso topic può essere prodotto da più
    # fonti (es. brand 'Apple' curated matchato dal dict + estratto come PER
    # da regex; oppure REGEX_PER e REGEX_MODEL che producono lo stesso slug
    # via slugify). Tieni il match con score più alto. Senza questo dedupe, il
    # batch insert su `article_topics` viola la PK (article_id, topic_id).
    by_id: dict[int, TopicMatch] = {}
    for m in out:
        if m.topic_id not in by_id or m.score > by_id[m.topic_id].score:
            by_id[m.topic_id] = m
    out = list(by_id.values())

    # Composite rules: collassa componenti multipli in un singolo topic
    # sintetico (es. google + gemini → google-gemini).
    out = _apply_composite_rules(out, idx)
    out = _apply_subsumption(out, idx)

    out.sort(key=lambda m: m.score, reverse=True)
    return out


def _apply_composite_rules(
    matches: list[TopicMatch], idx: _CompiledIndex
) -> list[TopicMatch]:
    """Applica `_COMPOSITE_RULES`: se TUTTE le componenti di una regola sono
    presenti nei matches, le rimuove e aggiunge il topic composito.
    Score combinato = somma; in_title/in_body = OR delle componenti.
    """
    if not matches or not idx.slug_to_id:
        return matches
    matched_by_id = {m.topic_id: m for m in matches}
    for composite_slug, components in _COMPOSITE_RULES:
        component_ids = [idx.slug_to_id.get(s) for s in components]
        if not all(component_ids):
            continue  # regola riferisce slug non presenti in DB
        if not all(cid in matched_by_id for cid in component_ids):
            continue  # non tutte le componenti hanno matchato
        composite_id = idx.slug_to_id.get(composite_slug)
        if composite_id is None:
            continue
        component_matches = [matched_by_id[cid] for cid in component_ids]  # type: ignore[index]
        score = sum(m.score for m in component_matches)
        in_title = any(m.in_title for m in component_matches)
        in_body = any(m.in_body for m in component_matches)
        # Rimuovi componenti, aggiungi composito (sovrascrive se esiste già)
        for cid in component_ids:
            matched_by_id.pop(cid, None)  # type: ignore[arg-type]
        matched_by_id[composite_id] = TopicMatch(
            topic_id=composite_id,
            score=score,
            in_title=in_title,
            in_body=in_body,
            source="composite",
        )
    return list(matched_by_id.values())


def _person_collides_with_curated(
    cand: Candidate, idx: _CompiledIndex
) -> bool:
    """True se almeno un token (4+ char) del PERSON candidate corrisponde a
    un termine di un topic curated NON-person (brand/subject/location/model).

    Esempio: "Quantum Technology Monitor" → "Monitor" è un curated subject
    → la sequenza non è un PERSON, è un nome composto di altro tipo. Drop.

    Token < 4 char ignorati (rumore: "di", "la", "il" ...).
    """
    for raw_token in cand.surface_form.split():
        token = raw_token.lower().rstrip(".,;:")
        if len(token) < 4:
            continue
        topic_ids = idx.term_to_topics_ci.get(token, [])
        for tid in topic_ids:
            t_type = idx.topic_id_to_type.get(tid)
            if t_type and t_type != "person":
                return True
    return False


def _apply_subsumption(
    matches: list[TopicMatch], idx: _CompiledIndex
) -> list[TopicMatch]:
    """Rimuove i match il cui display_name (tokenizzato) è sotto-sequenza
    contigua dei token di un altro match presente nello stesso articolo.

    Esempi:
      - "Sony" (brand) matchato insieme a "Sony Xperia 1 VIII" (model) →
        rimuovi "Sony": il model più specifico assorbe il brand generico.
      - "Xperia" matchato insieme a "Sony Xperia 1 VIII" → rimuovi "Xperia".

    Niente effetto se uno dei due display_name è vuoto o ha un solo token in
    comune ma non contiguo (es. "Apple iPhone" NON assorbe "iPhone Pro").
    """
    if len(matches) < 2:
        return matches
    tokens_by_id: dict[int, tuple[str, ...]] = {
        m.topic_id: idx.topic_id_to_tokens.get(m.topic_id, ()) for m in matches
    }
    to_remove: set[int] = set()
    for aid, a_tokens in tokens_by_id.items():
        if not a_tokens:
            continue
        for bid, b_tokens in tokens_by_id.items():
            if aid == bid or aid in to_remove:
                continue
            if len(b_tokens) <= len(a_tokens):
                continue
            # `a_tokens` è sotto-sequenza contigua di `b_tokens`?
            la = len(a_tokens)
            for i in range(len(b_tokens) - la + 1):
                if b_tokens[i : i + la] == a_tokens:
                    to_remove.add(aid)
                    break
    if not to_remove:
        return matches
    return [m for m in matches if m.topic_id not in to_remove]


async def _known_brand_names(
    session: AsyncSession, matched_topic_ids: list[int]
) -> list[str]:
    """Display_name dei brand curated tra i topic già matchati dal dict.
    Usato come whitelist per REGEX_MODEL (es. se l'articolo matcha 'Apple',
    abilitiamo l'estrazione di 'Apple iPhone 15 Pro')."""
    if not matched_topic_ids:
        return []
    rows = (
        await session.execute(
            select(Topic.display_name)
            .where(Topic.id.in_(matched_topic_ids))
            .where(Topic.type == "brand")
            .where(Topic.is_curated == True)  # noqa: E712
        )
    ).all()
    return [r[0] for r in rows if r[0]]


async def _extract_regex_matches(
    session: AsyncSession,
    *,
    title: str,
    body: str,
    known_brands: list[str],
    idx: _CompiledIndex | None = None,
) -> list[TopicMatch]:
    """Step C: estrae person/model dal testo via regex, upserta come Topic
    is_curated=false, ritorna TopicMatch."""
    # 1. Estrazione separata su title/body per applicare scoring 3*t + 1*b.
    title_persons = extract_persons(title) if title else []
    body_persons = extract_persons(body) if body else []
    title_brands = extract_brand_single(title) if title else []
    body_brands = extract_brand_single(body) if body else []
    if known_brands:
        title_models = extract_models(title, known_brands=known_brands) if title else []
        body_models = extract_models(body, known_brands=known_brands) if body else []
    else:
        title_models = []
        body_models = []

    # Fix 4 (T-016): scarta candidati PERSON che contengono almeno un token
    # corrispondente a un topic curated NON-person (brand/subject/location).
    # Esempio: "Quantum Technology Monitor" → "Monitor" è curated subject →
    # non è un PERSON, è un nome composto di tipo diverso. Drop.
    if idx is not None:
        title_persons = [c for c in title_persons if not _person_collides_with_curated(c, idx)]
        body_persons = [c for c in body_persons if not _person_collides_with_curated(c, idx)]

    # Fix 3 (T-016): rimuovi BRAND_SINGLE il cui surface è un token già
    # presente in un match PERSON. Esempio: PERSON="Pierluigi Sandonnini" +
    # BRAND_SINGLE="Sandonnini" → tieni solo il PERSON.
    person_tokens = {
        tok.lower().rstrip(".,;:")
        for c in (title_persons + body_persons)
        for tok in c.surface_form.split()
    }
    if person_tokens:
        title_brands = [
            c for c in title_brands if c.surface_form.lower() not in person_tokens
        ]
        body_brands = [
            c for c in body_brands if c.surface_form.lower() not in person_tokens
        ]

    # 2. Aggrega per (normalized, ner_type) → counts in title/body
    persons = _aggregate_candidates(title_persons, body_persons)
    brands = _aggregate_candidates(title_brands, body_brands)
    models = _aggregate_candidates(title_models, body_models)

    # 3. Cap anti-esplosione: top-N per articolo, ordinati per score
    persons_capped = _take_top(persons, MAX_REGEX_PERSONS_PER_ARTICLE)
    brands_capped = _take_top(brands, MAX_REGEX_BRANDS_PER_ARTICLE)
    models_capped = _take_top(models, MAX_REGEX_MODELS_PER_ARTICLE)

    # 4. Upsert Topic per ciascuno + costruisci TopicMatch.
    # `_upsert_regex_topic` ritorna None se il topic esistente è type='invalid'
    # (marcato come non-topic in admin) → skip totale, no association.
    out: list[TopicMatch] = []
    for agg in persons_capped:
        tid = await _upsert_regex_topic(session, agg["surface"], type_="person", idx=idx)
        if tid is None:
            continue
        out.append(_match_from_agg(agg, topic_id=tid))
    for agg in brands_capped:
        tid = await _upsert_regex_topic(session, agg["surface"], type_="brand", idx=idx)
        if tid is None:
            continue
        out.append(_match_from_agg(agg, topic_id=tid))
    for agg in models_capped:
        tid = await _upsert_regex_topic(session, agg["surface"], type_="model", idx=idx)
        if tid is None:
            continue
        out.append(_match_from_agg(agg, topic_id=tid))
    return out


def _aggregate_candidates(
    title_cands: list[Candidate], body_cands: list[Candidate]
) -> list[dict[str, object]]:
    """Per ogni surface_form normalizzata: surface (originale), title_count,
    body_count. Una surface compare 1 volta (anche se in entrambi)."""
    agg: dict[str, dict[str, object]] = {}
    for c in title_cands:
        norm = ex_normalize(c.surface_form)
        if norm not in agg:
            agg[norm] = {"surface": c.surface_form, "t": 0, "b": 0}
        agg[norm]["t"] = int(agg[norm]["t"]) + 1  # type: ignore[arg-type]
    for c in body_cands:
        norm = ex_normalize(c.surface_form)
        if norm not in agg:
            agg[norm] = {"surface": c.surface_form, "t": 0, "b": 0}
        agg[norm]["b"] = int(agg[norm]["b"]) + 1  # type: ignore[arg-type]
    return list(agg.values())


def _take_top(aggs: list[dict[str, object]], cap: int) -> list[dict[str, object]]:
    """Ordina per score = 3*t + 1*b desc, tiene top-cap, score >= MIN_SCORE."""
    scored = [
        {**a, "score": int(a["t"]) * 3.0 + int(a["b"]) * 1.0}  # type: ignore[arg-type]
        for a in aggs
    ]
    scored = [a for a in scored if float(a["score"]) >= MIN_SCORE]  # type: ignore[arg-type]
    scored.sort(key=lambda a: float(a["score"]), reverse=True)  # type: ignore[arg-type]
    return scored[:cap]


def _match_from_agg(agg: dict[str, object], *, topic_id: int) -> TopicMatch:
    t = int(agg["t"])  # type: ignore[arg-type]
    b = int(agg["b"])  # type: ignore[arg-type]
    return TopicMatch(
        topic_id=topic_id,
        score=t * 3.0 + b * 1.0,
        in_title=t > 0,
        in_body=b > 0,
        source="regex",
    )


async def _extract_ner_matches(
    session: AsyncSession,
    *,
    title: str,
    idx: _CompiledIndex | None = None,
) -> list[TopicMatch]:
    """Step D: estrae entità via spaCy `it_core_news_lg`, upserta come Topic
    is_curated=false (stesso pattern di Step C). Solo sul titolo per coerenza
    con la policy T-018 (title-only extraction).

    Score: ogni entità appare 1 volta nel titolo → score = 3.0 (peso titolo).
    Cap per article tipato (5 PER, 3 ORG, 3 LOC) per anti-esplosione.
    """
    from app.ingestion import ner

    entities = ner.extract_entities(title)
    if not entities:
        return []

    # Cap per tipo, preservando ordine di apparizione
    by_type: dict[str, list[ner.NerEntity]] = {"person": [], "brand": [], "location": []}
    for e in entities:
        bucket = by_type.get(e.topic_type)
        if bucket is None:
            continue
        bucket.append(e)
    by_type["person"] = by_type["person"][:MAX_NER_PERSONS_PER_ARTICLE]
    by_type["brand"] = by_type["brand"][:MAX_NER_ORGS_PER_ARTICLE]
    by_type["location"] = by_type["location"][:MAX_NER_LOCATIONS_PER_ARTICLE]

    out: list[TopicMatch] = []
    for topic_type, ents in by_type.items():
        for e in ents:
            tid = await _upsert_regex_topic(session, e.text, type_=topic_type, idx=idx)
            if tid is None:
                continue
            out.append(
                TopicMatch(
                    topic_id=tid,
                    score=3.0,  # title-only → peso titolo (allineato dict step)
                    in_title=True,
                    in_body=False,
                    source="ner",
                )
            )
    return out


async def _upsert_regex_topic(
    session: AsyncSession,
    surface: str,
    *,
    type_: str,
    idx: _CompiledIndex | None = None,
) -> int | None:
    """Restituisce topic_id; crea il topic is_curated=false se non esiste.
    Lo slug è deterministico via `slugify(surface)`. Idempotente.

    Ritorna None se esiste già un topic con quello slug ma con type='invalid':
    è stato marcato come non-topic in admin, non va più riassociato ad articoli.

    Se `idx` è passato, prima di creare un nuovo auto-topic controlla se il
    surface è già un **alias** (o display_name) di un topic curated, e in
    quel caso riusa l'id del curated invece di duplicare. Necessario perché
    il check su slug non basta: "Apple" come alias di curated "Apple Inc."
    ha slug `apple-inc`, quindi senza questo guard si creerebbe un secondo
    topic `apple` is_curated=false.
    """
    # Guard alias: lookup nel term map dei curated prima di insert.
    if idx is not None:
        norm = _normalize_term(surface)
        ids = idx.term_to_topics_ci.get(norm) or idx.term_to_topics_cs.get(surface.strip())
        if ids:
            # Più curated possono condividere lo stesso alias (raro ma legale):
            # tieni il primo, è quello inserito per primo nel build dell'index.
            return int(ids[0])

    slug = slugify(surface)
    # Se esiste già un topic con questo slug (curated o no), lo riusiamo.
    # Es: "Apple" surface_form da REGEX_PER finirebbe sullo stesso slug del
    # brand Apple curated → preferiamo riusarlo invece di creare un duplicato.
    stmt = pg_insert(Topic).values(
        type=type_,
        slug=slug,
        display_name=surface,
        aliases=[],
        description=None,
        external_refs=None,
        is_curated=False,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["slug"])
    await session.execute(stmt)
    # Fetch (id, type): l'INSERT non ritorna id su conflict_do_nothing, e
    # ci serve type per riconoscere i topic blacklisted.
    row = (
        await session.execute(
            select(Topic.id, Topic.type).where(Topic.slug == slug)
        )
    ).one_or_none()
    if row is None:
        # Edge case: race nello stesso processo (non dovrebbe succedere).
        raise RuntimeError(f"Topic {slug!r} non trovato dopo upsert")
    tid, t_type = row
    if t_type == "invalid":
        return None
    return int(tid)
