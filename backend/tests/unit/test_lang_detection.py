"""Rilevamento lingua fonti + filtro match Wikidata (regressioni Fisco/INPS)."""

from __future__ import annotations

import pytest

from app.ingestion.lang import detect_language, is_engine_language
from app.services.wikidata_service import _score_hit, infer_type_from_p31

EN_TITLES = [
    "Apple unveils the new iPhone with a faster chip",
    "Why the Fed is not cutting rates after the report",
    "How to build your first app with this tool",
    "Google says it will fix the bug in the browser",
]
IT_TITLES = [
    "Il nuovo iPhone di Apple arriva in Italia",
    "Perché la Bce non taglia i tassi dopo il rapporto",
    "Come costruire la tua prima app con questo strumento",
    "Ecco cosa ha detto Google sul bug del browser",
]


def test_detect_english():
    assert detect_language(EN_TITLES) == "en"


def test_detect_italian():
    assert detect_language(IT_TITLES) == "it"


def test_weak_signal_is_unknown():
    assert detect_language(["Apple", "Tesla"]) is None


@pytest.mark.parametrize(
    ("lang", "expected"), [(None, True), ("it", True), ("en", False), ("fr", False)]
)
def test_engine_language(lang, expected):
    assert is_engine_language(lang) is expected


def _hit(label, lang, desc, mtype="label", text=None):
    return {
        "label": label,
        "description": desc,
        "match": {"type": mtype, "language": lang, "text": text or label},
    }


def test_fisco_does_not_match_foreign_company():
    # "FISCO" en, nessuna description / sigla maiuscola vs parola normale
    assert _score_hit("fisco", _hit("FISCO", "en", None), raw_term_is_not_upper=True) is None
    assert (
        _score_hit(
            "fisco", _hit("FISCO", "en", "Chinese trade association"), raw_term_is_not_upper=True
        )
        is None
    )


def test_inps_ignores_mul_alias_and_keeps_italian_label():
    mul = _hit("Indah Prakasa Sentosa", "mul", "Indonesian company", "alias", "INPS")
    assert _score_hit("inps", mul) is None
    it = _hit("INPS", "it", "ente previdenziale italiano")
    assert _score_hit("inps", it, raw_term_is_not_upper=True) == (1.0, "label_it_exact")


def test_ente_infers_organization():
    assert infer_type_from_p31({"Q699386"}) == "organization"
