"""Wikidata enrichment per i topic curati (Phase 1.2.B iteration-1).

Per ogni topic curato si interroga Wikidata Search API per trovare il
Q-ID corrispondente, poi `wbgetentities` per estrarre description (it/en),
aliases (merge col dataset locale), Wikipedia URL e immagine commons.

I dati arricchiti vivono in:
- `topics.description` (text, lang `it` preferita)
- `topics.aliases` (ARRAY[text], merge case-insensitive con quelli esistenti)
- `topics.external_refs` (JSONB) con shape:
    {
      "wikidata_qid": "Q1130",
      "wikipedia_url_it": "https://it.wikipedia.org/wiki/...",
      "wikipedia_url_en": "https://en.wikipedia.org/wiki/...",
      "image": "https://commons.wikimedia.org/wiki/Special:FilePath/...",
      "enriched_at": "2026-05-11T...",
      "match_confidence": 0.92,
      "match_method": "label_it_exact"
    }

Soglia confidenza: 0.7 (sotto cui non scriviamo nulla). I match si fanno con:
- 1.00: exact label `it` (case-insensitive)
- 0.80: exact label `en` o alias `it` exact
- 0.70: alias `en` exact
- < 0.70: ignorato

Politica: idempotente; non sovrascrive una description esistente *non vuota*
a meno che `force=True`; le aliases sono sempre mergeate non distruttivamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic


log = structlog.get_logger()


WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "YouFeed/1.1 (https://www.youfeed.it; mastro.francesco@gmail.com)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
DEFAULT_THRESHOLD = 0.7


# P31 "instance of" Q-IDs accettabili per ogni topic.type. La lista è una
# whitelist conservativa: se il match non rientra in queste classi, lo scartiamo
# (evita "Amazon" → fiume Amazon quando il topic è type='brand'). Per type
# senza vincolo (subject, model, ...) ritorniamo None = no filter.
TYPE_TO_P31_WHITELIST: dict[str, frozenset[str]] = {
    "brand": frozenset({
        "Q4830453",   # business
        "Q43229",     # organization
        "Q167270",    # brand
        "Q891723",    # public company
        "Q6881511",   # enterprise
        "Q1985",      # food brand
        "Q161726",    # multinational corporation
        "Q15265344",  # broadcaster
        "Q1656682",   # statunitense / company subclass
        "Q4830453",   # business (duplicate intentional)
        "Q786820",    # automobile manufacturer
        "Q18388277",  # technology company
        "Q11032",     # newspaper
        "Q1058914",   # software company
        "Q41710",     # ethnic group (rare)
        "Q210167",    # video game developer
        "Q1107656",   # video game publisher
        "Q5621421",   # band
        "Q476028",    # association football club
        "Q1336961",   # sports team
        "Q31920",     # sports club
        "Q1664720",   # institute
        "Q4287745",   # medical organization
        "Q163740",    # nonprofit organization
        "Q11691",     # stock exchange
        "Q1058914",   # software company (duplicate)
        "Q784885",    # multi-sport club
    }),
    "person": frozenset({
        "Q5",  # human
    }),
    "location": frozenset({
        "Q515",       # city
        "Q6256",      # country
        "Q484170",    # commune (FR)
        "Q5119",      # capital
        "Q5398426",   # comune of Italy
        "Q486972",    # human settlement
        "Q23397",     # lake
        "Q12280",     # bridge
        "Q3957",      # town
        "Q1549591",   # big city
        "Q1637706",   # city of more than 1M
        "Q19953632",  # former municipality
        "Q15284",     # municipality
        "Q35657",     # state of the US
        "Q10864048",  # first-level admin region
        "Q56061",     # admin territorial entity
    }),
    "company": frozenset({
        "Q4830453",   # business
        "Q6881511",   # enterprise
        "Q891723",    # public company
        "Q161726",    # multinational corporation
        "Q18388277",  # technology company
        "Q1058914",   # software company
        "Q786820",    # automobile manufacturer
        "Q11032",     # newspaper
        "Q15265344",  # broadcaster
        "Q1656682",   # company subclass
        "Q210167",    # video game developer
        "Q1107656",   # video game publisher
        "Q2401749",   # società di telecomunicazioni
        "Q43229",     # organization (subclass also accepted)
    }),
    "organization": frozenset({
        "Q43229",     # organization
        "Q163740",    # nonprofit organization
        "Q1664720",   # institute
        "Q4287745",   # medical organization
        "Q1985",      # food brand (rare org type)
        "Q11691",     # stock exchange
        "Q31920",     # sports club
        "Q476028",    # association football club
        "Q1336961",   # sports team
        "Q484652",    # international organization
        "Q327333",    # government agency
        "Q2659904",   # government organization
        "Q7188",      # government
    }),
    "software": frozenset({
        "Q7397",      # software
        "Q9143",      # programming language
        "Q9135",      # operating system
        "Q341",       # free software
        "Q1330336",   # mobile app
        "Q21198",     # computer science
        "Q1130645",   # web application
        "Q166142",    # application software
        "Q251",       # video game
        "Q11410",     # video game (alt)
        "Q176165",    # web framework
        "Q193351",    # web browser
        "Q1077673",   # software framework
        "Q40056",     # search engine
        "Q131212",    # large language model
    }),
    "hardware": frozenset({
        "Q3966",      # computer hardware
        "Q56155214",  # device
        "Q22645",     # graphics processing unit
        "Q5290",      # central processing unit
        "Q5082128",   # smartphone
        "Q3962566",   # smartphone (alt)
        "Q986008",    # tablet computer
        "Q170978",    # laptop
        "Q68",        # computer
        "Q11993",     # mobile phone
        "Q43084",     # video game console
    }),
    "event": frozenset({
        "Q1656682",   # event
        "Q1190554",   # occurrence
        "Q132241",    # festival
        "Q464980",    # election
        "Q1187337",   # international event
        "Q1656682",   # event (dup)
        "Q15275719",  # recurring event
        "Q4504495",   # award ceremony
        "Q40231",     # conference
        "Q175331",    # demonstration
        "Q198",       # war
        "Q3001412",   # political event
    }),
    "work": frozenset({
        "Q386724",    # work (most generic)
        "Q571",       # book
        "Q11424",     # film
        "Q5398426",   # television series
        "Q15416",     # television program
        "Q482994",    # album
        "Q2031291",   # newspaper article
        "Q838948",    # work of art
        "Q1004",      # comics
        "Q47461344",  # written work
        "Q571",       # book (dup)
        "Q7725634",   # literary work
    }),
    # subject e model non hanno filtro: accettiamo qualsiasi P31
}


# Inferenza inversa: dato un set di P31 Q-id, suggerisci il `type` migliore.
# L'ordine conta: tipi più specifici prima dei più generici (es. "software"
# prima di "subject", "company" prima di "organization"/"brand").
_TYPE_INFERENCE_ORDER: tuple[str, ...] = (
    "person",
    "location",
    "software",
    "hardware",
    "event",
    "work",
    "company",
    "organization",
    "brand",
)


def infer_type_from_p31(p31_qids: set[str]) -> str | None:
    """Ritorna il type più specifico la cui whitelist matcha almeno un P31,
    seguendo l'ordine `_TYPE_INFERENCE_ORDER`. None se nessun match.

    Pensato per il tool `refresh_topics` che riassegna il `type` di un topic
    in base ai claim Wikidata aggiornati.
    """
    if not p31_qids:
        return None
    for t in _TYPE_INFERENCE_ORDER:
        wl = TYPE_TO_P31_WHITELIST.get(t)
        if wl and (p31_qids & wl):
            return t
    return None


def _extract_p31_qids(entity: dict[str, Any]) -> set[str]:
    """Estrae i Q-ID di P31 (instance of) dall'entity."""
    out: set[str] = set()
    claims = (entity.get("claims") or {}).get("P31") or []
    for claim in claims:
        mainsnak = claim.get("mainsnak") or {}
        datavalue = (mainsnak.get("datavalue") or {}).get("value") or {}
        if isinstance(datavalue, dict) and "id" in datavalue:
            out.add(str(datavalue["id"]))
    return out


def _type_compatible(entity: dict[str, Any], topic_type: str) -> bool:
    """True se l'entità è compatibile col topic.type. Senza whitelist = pass."""
    whitelist = TYPE_TO_P31_WHITELIST.get(topic_type)
    if whitelist is None:
        return True
    p31 = _extract_p31_qids(entity)
    return bool(p31 & whitelist)


@dataclass(slots=True)
class WikidataMatch:
    qid: str
    confidence: float
    method: str
    raw_search_hit: dict[str, Any]


@dataclass(slots=True)
class EnrichmentResult:
    topic_id: int
    status: str  # 'enriched' | 'no_match' | 'low_confidence' | 'skipped' | 'error'
    qid: str | None = None
    confidence: float | None = None
    method: str | None = None


# ---------------------------------------------------------------------------
# Wikidata API wrappers
# ---------------------------------------------------------------------------


async def _search_entities(
    client: httpx.AsyncClient, term: str, *, language: str = "it", limit: int = 5
) -> list[dict[str, Any]]:
    params = {
        "action": "wbsearchentities",
        "search": term,
        "language": language,
        "format": "json",
        "type": "item",
        "limit": str(limit),
        "uselang": language,
    }
    try:
        resp = await client.get(WIKIDATA_API, params=params)
        if resp.status_code >= 400:
            log.warning("yf.wikidata.search_status", status=resp.status_code, term=term)
            return []
        return list((resp.json() or {}).get("search") or [])
    except httpx.HTTPError as e:
        log.warning("yf.wikidata.search_failed", term=term, error=str(e))
        return []


async def _get_entities(
    client: httpx.AsyncClient, qids: list[str]
) -> dict[str, dict[str, Any]]:
    if not qids:
        return {}
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "format": "json",
        "languages": "it|en",
        "props": "labels|descriptions|aliases|claims|sitelinks/urls",
    }
    try:
        resp = await client.get(WIKIDATA_API, params=params)
        if resp.status_code >= 400:
            log.warning("yf.wikidata.entities_status", status=resp.status_code)
            return {}
        return (resp.json() or {}).get("entities") or {}
    except httpx.HTTPError as e:
        log.warning("yf.wikidata.entities_failed", error=str(e))
        return {}


# ---------------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------------


import re as _re
_WORD_BOUNDARY = _re.compile(r"[\w]+", _re.UNICODE)


def _tokenize(s: str) -> set[str]:
    return set(_WORD_BOUNDARY.findall(s.lower()))


def _score_hit(term_norm: str, hit: dict[str, Any]) -> tuple[float, str] | None:
    """Calcola (confidence, method) per un hit di wbsearchentities.

    Considera match.type + match.language (label_it_exact > label_en_exact >
    alias_*_exact) e accetta "contains as token" come fallback (es. label
    "Amazon.com" contro term "amazon" → label_it_token).
    """
    match = hit.get("match") or {}
    matched_type = match.get("type") or ""
    matched_lang = match.get("language") or ""
    matched_text = (match.get("text") or "").strip().lower()
    label = (hit.get("label") or "").strip().lower()
    aliases_inline = [a.lower() for a in (hit.get("aliases") or [])]

    # 1. exact match: API ha trovato un label/alias che combacia esattamente
    if matched_text == term_norm:
        if matched_type == "label" and matched_lang == "it":
            return (1.00, "label_it_exact")
        if matched_type == "label" and matched_lang == "en":
            return (0.85, "label_en_exact")
        if matched_type == "alias" and matched_lang == "it":
            return (0.80, "alias_it_exact")
        if matched_type == "alias" and matched_lang == "en":
            return (0.70, "alias_en_exact")
        if matched_type == "alias":
            return (0.70, "alias_exact")

    # 2. label/alias contiene il termine come token intero (es. "Amazon.com"
    #    vs "amazon"). Confidence sotto exact ma sopra threshold di default.
    term_tokens = _tokenize(term_norm)
    if term_tokens:
        if term_tokens <= _tokenize(label):
            return (0.80, "label_token")
        for a in aliases_inline:
            if term_tokens <= _tokenize(a):
                return (0.75, "alias_token")

    return None


def _claim_qids(claims: dict[str, Any], prop: str) -> list[str]:
    """Estrai i Q-id puntati da `prop` (es. P31, P17, P127). I claim Wikidata
    multi-valore sono comuni (più istanze, più proprietari, ecc.): mantengo
    tutti i valori, preservando l'ordine."""
    out: list[str] = []
    for c in claims.get(prop) or []:
        snak = c.get("mainsnak") or {}
        dv = (snak.get("datavalue") or {}).get("value") or {}
        qid = dv.get("id") if isinstance(dv, dict) else None
        if isinstance(qid, str) and qid.startswith("Q") and qid not in out:
            out.append(qid)
    return out


def _claim_url(claims: dict[str, Any], prop: str) -> str | None:
    """Estrai una URL string (P856 = sito ufficiale). Prende il primo valore."""
    for c in claims.get(prop) or []:
        snak = c.get("mainsnak") or {}
        dv = (snak.get("datavalue") or {}).get("value")
        if isinstance(dv, str) and dv:
            return dv
    return None


async def _resolve_qid_labels(
    client: httpx.AsyncClient, qids: list[str]
) -> dict[str, str]:
    """Risolve una lista di Q-id a label umani (it preferred, fallback en)
    via una singola chiamata `wbgetentities props=labels`. Niente label se
    Wikidata non ce l'ha nelle due lingue."""
    if not qids:
        return {}
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "format": "json",
        "languages": "it|en",
        "props": "labels",
    }
    try:
        resp = await client.get(WIKIDATA_API, params=params)
        if resp.status_code >= 400:
            return {}
        ents = (resp.json() or {}).get("entities") or {}
    except httpx.HTTPError as e:
        log.debug("yf.wikidata.labels_failed", error=str(e))
        return {}
    out: dict[str, str] = {}
    for qid, ent in ents.items():
        labels = ent.get("labels") or {}
        for lang in ("it", "en"):
            v = (labels.get(lang) or {}).get("value")
            if v:
                out[qid] = str(v)
                break
    return out


def _build_external_refs(entity: dict[str, Any], match: WikidataMatch) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "wikidata_qid": match.qid,
        "match_confidence": match.confidence,
        "match_method": match.method,
        "enriched_at": datetime.now(UTC).isoformat(),
    }
    # Wikipedia sitelinks
    sitelinks = entity.get("sitelinks") or {}
    it_wp = (sitelinks.get("itwiki") or {}).get("url")
    en_wp = (sitelinks.get("enwiki") or {}).get("url")
    if it_wp:
        refs["wikipedia_url_it"] = it_wp
    if en_wp:
        refs["wikipedia_url_en"] = en_wp

    claims = entity.get("claims") or {}
    # P18 (image)
    p18 = (claims.get("P18") or [{}])[0] if claims.get("P18") else None
    if p18:
        mainsnak = p18.get("mainsnak") or {}
        datavalue = (mainsnak.get("datavalue") or {}).get("value")
        if isinstance(datavalue, str) and datavalue:
            refs["image"] = (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                + datavalue.replace(" ", "_")
                + "?width=512"
            )

    # Claim Q-id estratti GREZZI. Le label umane vengono risolte in
    # enrich_topic() con _resolve_qid_labels() e mergeate qui dopo.
    p31 = _claim_qids(claims, "P31")
    p17 = _claim_qids(claims, "P17")
    p127 = _claim_qids(claims, "P127")
    if p31:
        refs["instance_of"] = [{"qid": q, "label": None} for q in p31]
    if p17:
        refs["country"] = [{"qid": q, "label": None} for q in p17]
    if p127:
        refs["owned_by"] = [{"qid": q, "label": None} for q in p127]

    # P856 (official website)
    official = _claim_url(claims, "P856")
    if official:
        refs["official_url"] = official

    return refs


def _extract_description(entity: dict[str, Any]) -> str | None:
    descs = entity.get("descriptions") or {}
    for lang in ("it", "en"):
        v = (descs.get(lang) or {}).get("value")
        if v:
            return str(v)
    return None


def _extract_aliases(entity: dict[str, Any]) -> list[str]:
    aliases_block = entity.get("aliases") or {}
    out: list[str] = []
    seen_norm: set[str] = set()
    for lang in ("it", "en"):
        for it in aliases_block.get(lang) or []:
            v = (it.get("value") or "").strip()
            if not v:
                continue
            k = v.lower()
            if k in seen_norm:
                continue
            seen_norm.add(k)
            out.append(v)
    return out


def _merge_aliases(existing: list[str] | None, new: list[str]) -> list[str]:
    """Merge case-insensitive preservando l'ordine esistente prima."""
    seen: dict[str, str] = {}
    for a in (existing or []) + new:
        k = a.strip().lower()
        if not k or k in seen:
            continue
        seen[k] = a
    return list(seen.values())


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def enrich_topic(
    db: AsyncSession,
    *,
    topic_id: int,
    force: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    client: httpx.AsyncClient | None = None,
) -> EnrichmentResult:
    """Arricchisce un topic. Idempotente. Non sovrascrive description esistente
    a meno che `force=True`. Le aliases sono sempre mergeate non distruttive."""
    topic = await db.get(Topic, topic_id)
    if topic is None:
        return EnrichmentResult(topic_id=topic_id, status="error")

    if not force and topic.external_refs and topic.external_refs.get("wikidata_qid"):
        log.debug("yf.wikidata.skip_existing_qid", topic_id=topic_id)
        return EnrichmentResult(
            topic_id=topic_id,
            status="skipped",
            qid=topic.external_refs.get("wikidata_qid"),
        )

    term_norm = (topic.display_name or "").strip().lower()
    if not term_norm:
        return EnrichmentResult(topic_id=topic_id, status="no_match")

    own_client = client is None
    client = client or httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    try:
        # 1. Search top 5
        hits = await _search_entities(client, topic.display_name, language="it", limit=5)
        if not hits:
            return EnrichmentResult(topic_id=topic_id, status="no_match")

        # 2. Score per label/alias match; raccogli i candidati > threshold
        candidates: list[WikidataMatch] = []
        for h in hits:
            sc = _score_hit(term_norm, h)
            if sc is None:
                continue
            conf, method = sc
            if conf < threshold:
                continue
            candidates.append(
                WikidataMatch(
                    qid=str(h.get("id")),
                    confidence=conf,
                    method=method,
                    raw_search_hit=h,
                )
            )
        if not candidates:
            return EnrichmentResult(topic_id=topic_id, status="low_confidence")

        # 3. Fetch full entities per i top-3 candidati e filtra per P31 (type-aware)
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        top_n = candidates[:3]
        entities = await _get_entities(client, [c.qid for c in top_n])

        best: WikidataMatch | None = None
        entity: dict[str, Any] | None = None
        for cand in top_n:
            ent = entities.get(cand.qid)
            if ent is None:
                continue
            if not _type_compatible(ent, topic.type):
                log.debug(
                    "yf.wikidata.type_mismatch",
                    topic_id=topic_id,
                    topic_type=topic.type,
                    qid=cand.qid,
                    p31=list(_extract_p31_qids(ent)),
                )
                continue
            best = cand
            entity = ent
            break

        if best is None or entity is None:
            # Tutti i top candidati hanno P31 incompatibile: nessun match utilizzabile
            return EnrichmentResult(
                topic_id=topic_id,
                status="low_confidence",
                qid=top_n[0].qid if top_n else None,
                confidence=top_n[0].confidence if top_n else None,
            )

        # 4. Apply
        description = _extract_description(entity)
        new_aliases = _extract_aliases(entity)
        refs = _build_external_refs(entity, best)

        # 4b. Risolvi le label dei Q-id linkati (P31/P17/P127) in batch unico
        linked_qids: list[str] = []
        for key in ("instance_of", "country", "owned_by"):
            for item in refs.get(key) or []:
                qid = item.get("qid")
                if qid and qid not in linked_qids:
                    linked_qids.append(qid)
        if linked_qids:
            labels = await _resolve_qid_labels(client, linked_qids)
            for key in ("instance_of", "country", "owned_by"):
                for item in refs.get(key) or []:
                    lbl = labels.get(item.get("qid"))
                    if lbl:
                        item["label"] = lbl

        if description and (force or not topic.description):
            topic.description = description
        topic.aliases = _merge_aliases(topic.aliases, new_aliases) or topic.aliases
        # Preserva chiavi external_refs preesistenti (es. seed source) e sovrascrive
        # solo le chiavi wikidata-derived
        merged_refs = dict(topic.external_refs or {})
        merged_refs.update(refs)
        topic.external_refs = merged_refs

        await db.flush()
        log.info(
            "yf.wikidata.enriched",
            topic_id=topic_id,
            qid=best.qid,
            confidence=best.confidence,
            method=best.method,
            has_image="image" in refs,
        )
        return EnrichmentResult(
            topic_id=topic_id,
            status="enriched",
            qid=best.qid,
            confidence=best.confidence,
            method=best.method,
        )
    finally:
        if own_client:
            await client.aclose()
