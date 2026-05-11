"""NER spaCy per estrazione entità (Phase 1.2.A).

Carica `it_core_news_lg` lazy + global, espone `extract_entities(text)` per
ottenere PER/ORG/LOC/MISC con i normali filtri italiani (no inizio frase,
no token isolati). I match vivono accanto agli estrattori regex di
`app/topic_extractor/extractor.py`; la differenza è che spaCy ha recall
molto migliore su persone/organizzazioni composte mentre i regex coprono
meglio brand sigli e modelli alfanumerici.

Coerentemente con la policy T-018 (title-only), il caller live in
`classify.py` invoca il NER **solo sul titolo**. Il batch tool
`app/topic_extractor` può invocarlo su title+description.

Pattern di blacklist e mapping tag:
- spaCy IT usa `PER`, `ORG`, `LOC`, `MISC` (4 classi)
- mappa a `topics.type`: PER→person, ORG→brand, LOC→location, MISC→subject
- scartiamo token singoli minuscoli o ≤2 char (rumore)
- scartiamo entità tutto-uppercase ≤2 char (es. "DI", "LA")
- scartiamo i token in `_NER_TOKEN_BLACKLIST` (stop-words/avverbi/mesi IT)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

import structlog


if TYPE_CHECKING:
    from spacy.language import Language


log = structlog.get_logger()


# Stop-words specifiche del corpus IT che spaCy non scarta da sola. La lista
# è incrementale (le aggiungo se vedo falsi positivi). I plurale/maiuscolo
# vengono coperti dal lower() lookup.
_NER_TOKEN_BLACKLIST: frozenset[str] = frozenset({
    "anche", "infatti", "tuttavia", "quindi", "dunque", "perciò", "cioè",
    "ovvero", "ossia", "altresì", "comunque", "soprattutto", "particolarmente",
    "specialmente", "principalmente", "appunto", "ancora", "magari", "ormai",
    "presto", "tardi", "subito", "spesso", "sempre", "raramente", "mai",
    "molto", "poco", "tanto", "troppo", "abbastanza", "piuttosto",
    # preposizioni italiane (edge-trim per evitare "di Bergamo", "del Trump")
    "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
    "il", "lo", "la", "i", "gli", "le", "un", "una", "uno",
    "del", "dello", "della", "dei", "degli", "delle",
    "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "nel", "nello", "nella", "nei", "negli", "nelle",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "col", "coi",
    # mesi (capitalize)
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    # giorni
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
    # parole generiche italiane comuni in titoli che spaCy a volte tagga come PER/ORG
    "colpo", "cosa", "dunque", "grado", "anno", "mese", "giorno", "ora",
    "italia",  # troppo generico come "LOC" — escluso se vuoi tracciare nazione c'è già curated
})


_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(slots=True, frozen=True)
class NerEntity:
    """Entità estratta dal NER, normalizzata."""

    text: str          # surface_form originale dal token
    label: str         # spaCy label: PER | ORG | LOC | MISC
    topic_type: str    # mappato: person | brand | location | subject
    start: int
    end: int


_NER_TO_TOPIC_TYPE: dict[str, str] = {
    "PER": "person",
    "PERSON": "person",  # compat con altri modelli
    "ORG": "brand",
    "LOC": "location",
    "GPE": "location",
    # MISC viene scartato: spaCy IT lo usa per moltissime cose (prodotti,
    # eventi, concetti) ed è troppo rumoroso. Modelli/prodotti li copre già
    # `REGEX_MODEL` (whitelist brand-driven); per concetti astratti aspettiamo
    # promozione manuale via /yf_admin/entities (post-ingest).
}


@lru_cache(maxsize=1)
def get_nlp() -> "Language":
    """Carica il modello spaCy una volta. Lazy load: il costo (~1s) viene
    pagato solo se qualcuno chiama `extract_entities`."""
    import spacy

    log.info("yf.ner.loading_model", name="it_core_news_lg")
    nlp = spacy.load("it_core_news_lg", disable=["lemmatizer", "tagger"])
    # Disabilitiamo lemmatizer/tagger perché non ci servono per la NER e
    # accelerano il pipeline ~3x. Tokenizer + parser + NER restano attivi.
    log.info("yf.ner.model_loaded", name=nlp.meta.get("name"), version=nlp.meta.get("version"))
    return nlp


def reset_nlp_cache() -> None:
    """Forza il reload del modello (utile in test)."""
    get_nlp.cache_clear()


def _is_blacklisted(token_text: str) -> bool:
    lo = token_text.lower().strip()
    if not lo:
        return True
    return lo in _NER_TOKEN_BLACKLIST


def _is_acceptable(text: str, label: str) -> bool:
    """Filtra entità troppo generiche / rumorose."""
    s = text.strip()
    if not s:
        return False
    # length: 2 char minimum per non-acronimi; acronimi <=4 ALL CAPS OK
    if len(s) <= 2 and not s.isupper():
        return False
    # tutto minuscolo → quasi sempre rumore (spaCy ogni tanto sbaglia)
    if s == s.lower():
        return False
    # tutto in blacklist → out
    if _is_blacklisted(s):
        return False
    # single-token MISC: alta probabilità di rumore (es. "Cosa")
    tokens = s.split()
    if label == "MISC" and len(tokens) == 1:
        return False
    # primo token in blacklist → trim (gestito dal caller via _trim_edge)
    # MISC con un solo token lowercase iniziale: skip
    return True


def _trim_edge_blacklist(text: str) -> str:
    """Toglie token leader/trailing in blacklist (es. "Anche Mario Rossi" →
    "Mario Rossi")."""
    parts = text.split()
    while parts and _is_blacklisted(parts[0]):
        parts.pop(0)
    while parts and _is_blacklisted(parts[-1]):
        parts.pop()
    return " ".join(parts)


def extract_entities(text: str) -> list[NerEntity]:
    """Run spaCy NER su `text` e ritorna le entità filtrate.

    Vuoto se `text` è vuoto/whitespace; nessuna eccezione bubbling.
    """
    if not text or not text.strip():
        return []
    try:
        nlp = get_nlp()
        doc = nlp(text)
    except Exception as e:  # noqa: BLE001
        log.warning("yf.ner.extract_failed", error=str(e), text=text[:100])
        return []

    out: list[NerEntity] = []
    for ent in doc.ents:
        label = ent.label_
        topic_type = _NER_TO_TOPIC_TYPE.get(label)
        if topic_type is None:
            continue
        # Trim edge stop-words italiane
        cleaned = _trim_edge_blacklist(ent.text)
        if not cleaned:
            continue
        if not _is_acceptable(cleaned, label):
            continue
        out.append(
            NerEntity(
                text=cleaned,
                label=label,
                topic_type=topic_type,
                start=ent.start_char,
                end=ent.end_char,
            )
        )

    # Dedupe per (cleaned, topic_type): tieni il primo (= prima apparizione)
    seen: set[tuple[str, str]] = set()
    deduped: list[NerEntity] = []
    for e in out:
        key = (e.text.lower(), e.topic_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped
