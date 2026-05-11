"""Unit test per app.ingestion.classify (matching dictionary, no DB)."""

from __future__ import annotations

from dataclasses import dataclass

from app.ingestion import classify


# Costruisco "Topic-like" oggetti senza importare il modello SA (richiederebbe DB).
@dataclass
class FakeTopic:
    id: int
    display_name: str
    aliases: list[str] | None
    type: str = "brand"  # default; override per test su location ambigue
    slug: str = "fake-slug"  # default; override per test su case-sensitive


def _build_index(
    topics: list[FakeTopic],
    *,
    slug_to_id: dict[str, int] | None = None,
    topic_id_to_type: dict[int, str] | None = None,
) -> classify._CompiledIndex:
    term_map_ci, term_map_cs = classify._build_term_maps(topics)
    return classify._compile_index(
        term_map_ci, term_map_cs, slug_to_id, topic_id_to_type
    )


# ---------------------------------------------------------------------------
# _build_term_map
# ---------------------------------------------------------------------------


def test_build_term_map_includes_display_name_and_aliases() -> None:
    t = FakeTopic(id=1, display_name="Roma", aliases=["AS Roma", "Giallorossi"])
    out = classify._build_term_map([t])
    assert "roma" in out
    assert "as roma" in out
    assert "giallorossi" in out
    assert all(out[k] == [1] for k in out)


def test_build_term_map_handles_collisions() -> None:
    """Un termine può puntare a topic multipli (es. "Mercurio": pianeta vs società)."""
    a = FakeTopic(id=1, display_name="Mercurio", aliases=None)
    b = FakeTopic(id=2, display_name="Pianeta", aliases=["Mercurio"])
    out = classify._build_term_map([a, b])
    assert sorted(out["mercurio"]) == [1, 2]


def test_build_term_map_skips_ambiguous_location_terms() -> None:
    """T-009: comuni italiani con nome che coincide con sostantivi/aggettivi
    italiani comuni (Bomba, Campagna, Canale, ...) sono skippati dall'index
    del classifier per evitare falsi positivi su news non-cronaca."""
    bomba = FakeTopic(id=10, display_name="Bomba", aliases=None, type="location")
    out = classify._build_term_map([bomba])
    assert "bomba" not in out, (
        "Comune ambiguo non deve entrare nel term map del classifier"
    )


def test_build_term_map_keeps_non_ambiguous_location_terms() -> None:
    """Le città/comuni con nome non-ambiguo (Roma, Milano, Bologna, ...) restano."""
    roma = FakeTopic(id=11, display_name="Roma", aliases=None, type="location")
    out = classify._build_term_map([roma])
    assert "roma" in out


def test_build_term_map_keeps_brand_with_ambiguous_word() -> None:
    """Se un termine è in `_AMBIGUOUS_LOCATION_TERMS` ma il topic è di tipo
    diverso da `location` (es. un brand chiamato 'Massa'), resta indicizzato."""
    massa_brand = FakeTopic(id=12, display_name="Massa", aliases=None, type="brand")
    out = classify._build_term_map([massa_brand])
    assert "massa" in out
    assert out["massa"] == [12]


def test_scan_does_not_match_inside_italian_elision() -> None:
    """T-010: 'Dell' non deve matchare in 'dell'altra' / 'dell'intelligenza'.
    L'apostrofo italiano è parte del boundary."""
    dell = FakeTopic(id=20, display_name="Dell", aliases=None, type="brand")
    idx = _build_index([dell])
    # Match ok: spazio prima + spazio dopo
    assert classify._scan("Dell fa computer buoni", idx) == {20: 1}
    # Match KO: dopo c'è apostrofo (elisione "dell'altra")
    assert classify._scan("dell'altra notte ha parlato", idx) == {}
    assert classify._scan("dell'intelligenza artificiale", idx) == {}
    # Anche con apostrofo curly tipografico
    assert classify._scan("dell’altra notte", idx) == {}


def test_scan_matches_brand_with_apostrophe_in_italian_text() -> None:
    """L'apostrofo nel boundary non deve impedire i match legittimi del brand
    in testo italiano normale (preceduto/seguito da spazio o punteggiatura)."""
    levoit = FakeTopic(id=21, display_name="Levoit", aliases=None, type="brand")
    idx = _build_index([levoit])
    assert classify._scan("Il nuovo Levoit Windi è in vendita", idx) == {21: 1}
    assert classify._scan("Levoit, il marchio cinese, lancia il prodotto.", idx) == {21: 1}


def test_scan_does_not_match_substring_of_other_word() -> None:
    """'Wind' non deve matchare in 'Windi'. Verifica che il boundary funzioni
    anche con uppercase iniziale (case-insensitive)."""
    wind = FakeTopic(id=22, display_name="Wind", aliases=None, type="brand")
    idx = _build_index([wind])
    assert classify._scan("Levoit Windi Mini 2026 è in offerta", idx) == {}


def test_scan_matches_word_after_italian_elision() -> None:
    """T-010 (caso simmetrico): l'apostrofo NON deve bloccare i match della
    parola DOPO l'elisione. Boundary asimmetrico: apostrofo solo nel lookahead."""
    ai = FakeTopic(id=30, display_name="Intelligenza Artificiale", aliases=None, type="subject")
    idx = _build_index([ai])
    # Match dopo elisione "dell'"
    assert classify._scan("Era dell'intelligenza artificiale ovunque", idx) == {30: 1}
    # Match dopo elisione curly "dell’"
    assert classify._scan("Nell’era dell’intelligenza artificiale", idx) == {30: 1}


def test_scan_case_sensitive_lancia_brand_vs_verb() -> None:
    """T-013: 'Lancia' brand auto deve matchare solo se Title Case (brand);
    'lancia' lowercase è il verbo italiano e NON deve matchare."""
    lancia = FakeTopic(
        id=40, display_name="Lancia", aliases=None, type="brand", slug="lancia"
    )
    idx = _build_index([lancia])
    # Match solo se "Lancia" Title Case (contesto brand auto)
    assert classify._scan("La nuova Lancia Ypsilon è in vendita", idx) == {40: 1}
    # NO match se "lancia" lowercase (verbo "lanciare" 3sg)
    assert classify._scan("Qualcomm lancia il nuovo chip", idx) == {}
    # NO match se "LANCIA" all-caps (titolo urlato — improbabile per il brand)
    assert classify._scan("LANCIA il nuovo prodotto", idx) == {}


def test_scan_case_sensitive_lanciano_comune_vs_verb_3pl() -> None:
    """T-013: 'Lanciano' comune (CH) deve matchare solo Title Case;
    'lanciano' lowercase è verbo 'lanciare' 3pl, da NON matchare."""
    lanciano = FakeTopic(
        id=41, display_name="Lanciano", aliases=None, type="location", slug="lanciano"
    )
    idx = _build_index([lanciano])
    assert classify._scan("Le aziende di Lanciano festeggiano", idx) == {41: 1}
    # Verbo: "i marchi lanciano nuovi prodotti"
    assert classify._scan("I marchi lanciano nuovi prodotti", idx) == {}


def test_scan_case_insensitive_default_for_other_topics(db_session=None) -> None:
    """I topic NON in `_CASE_SENSITIVE_SLUGS` continuano a matchare
    case-insensitive (default)."""
    apple = FakeTopic(
        id=42, display_name="Apple", aliases=None, type="brand", slug="apple"
    )
    idx = _build_index([apple])
    assert classify._scan("L'azienda Apple ha presentato", idx) == {42: 1}
    assert classify._scan("nuovo modello apple oggi", idx) == {42: 1}  # lowercase ok


def test_build_term_map_skips_short_terms() -> None:
    t = FakeTopic(id=1, display_name="A", aliases=["bb"])
    out = classify._build_term_map([t])
    assert "a" not in out  # < 2 chars
    assert "bb" in out


# ---------------------------------------------------------------------------
# _compile_index + _scan
# ---------------------------------------------------------------------------


def test_scan_finds_whole_words_only() -> None:
    idx = _build_index([FakeTopic(id=1, display_name="Roma", aliases=None)])
    # "Romano" NON deve matchare "Roma"
    assert classify._scan("Romano cesare", idx) == {}
    # ma "a Roma" sì
    assert classify._scan("Vivo a Roma da anni", idx) == {1: 1}


def test_scan_supports_italian_accents_in_boundary() -> None:
    """Termine con accento (es. "città") non deve matchare se preceduto/seguito da accentate."""
    idx = _build_index([FakeTopic(id=1, display_name="città", aliases=None)])
    # match: parola intera con punteggiatura attorno
    assert classify._scan("La città è grande.", idx) == {1: 1}
    # no match: lettera accentata adiacente lo fa diventare boundary-violation
    assert classify._scan("Bellacittàe", idx) == {}


def test_scan_is_case_insensitive() -> None:
    idx = _build_index([FakeTopic(id=1, display_name="Milano", aliases=None)])
    assert classify._scan("MILANO è bella", idx) == {1: 1}
    assert classify._scan("milano è bella", idx) == {1: 1}


def test_scan_prefers_longest_match() -> None:
    """Quando "Roma Capitale" e "Roma" sono entrambi termini, "Roma Capitale" vince."""
    topics = [
        FakeTopic(id=1, display_name="Roma", aliases=None),
        FakeTopic(id=2, display_name="Roma Capitale", aliases=None),
    ]
    idx = _build_index(topics)
    counts = classify._scan("Visita a Roma Capitale", idx)
    # Solo l'id=2 (Roma Capitale) deve aver matchato; "Roma" da solo no
    assert counts.get(2) == 1
    assert counts.get(1) is None


def test_scan_empty_string() -> None:
    idx = _build_index([FakeTopic(id=1, display_name="Roma", aliases=None)])
    assert classify._scan("", idx) == {}


def test_scan_counts_multiple_matches() -> None:
    idx = _build_index([FakeTopic(id=1, display_name="Roma", aliases=None)])
    out = classify._scan("Roma è Roma. A Roma piove.", idx)
    assert out[1] == 3


# ---------------------------------------------------------------------------
# Scoring (title*3 + body*1)
#
# `classify.classify` accede al DB. Replichiamo qui la logica di scoring
# manualmente da _scan, per verificarne il comportamento atteso.
# ---------------------------------------------------------------------------


def test_score_formula_title_weight_three_body_weight_one() -> None:
    idx = _build_index([FakeTopic(id=1, display_name="Roma", aliases=None)])
    title_counts = classify._scan("Roma vince a Roma", idx)  # 2 occorrenze
    body_counts = classify._scan("Le strade di Roma erano vuote", idx)  # 1 occorrenza
    # score = 2*3 + 1*1 = 7
    score = title_counts.get(1, 0) * 3.0 + body_counts.get(1, 0) * 1.0
    assert score == 7.0


# ---------------------------------------------------------------------------
# Composite rules (T-015): google + gemini → google-gemini
# ---------------------------------------------------------------------------


def test_composite_rule_collapses_components_into_synthetic_topic() -> None:
    """Quando MATCHANO entrambe le componenti di una regola composite, le due
    TopicMatch vengono rimosse e sostituite da un singolo TopicMatch con
    topic_id del composite."""
    slug_to_id = {"google": 100, "gemini": 200, "google-gemini": 300}
    idx = _build_index([], slug_to_id=slug_to_id)
    matches = [
        classify.TopicMatch(topic_id=100, score=2.0, in_title=True, in_body=True),
        classify.TopicMatch(topic_id=200, score=4.0, in_title=False, in_body=True),
        classify.TopicMatch(topic_id=42, score=1.0, in_title=False, in_body=True),  # estraneo
    ]
    out = classify._apply_composite_rules(matches, idx)
    out_ids = {m.topic_id for m in out}
    assert 100 not in out_ids and 200 not in out_ids
    assert 300 in out_ids
    assert 42 in out_ids  # match estraneo invariato
    composite = next(m for m in out if m.topic_id == 300)
    assert composite.score == 6.0  # somma componenti
    assert composite.in_title is True  # OR delle componenti
    assert composite.source == "composite"


def test_composite_rule_skips_when_only_one_component_matched() -> None:
    """Solo `google` matcha: nessuna sostituzione."""
    slug_to_id = {"google": 100, "gemini": 200, "google-gemini": 300}
    idx = _build_index([], slug_to_id=slug_to_id)
    matches = [
        classify.TopicMatch(topic_id=100, score=2.0, in_title=True, in_body=True),
    ]
    out = classify._apply_composite_rules(matches, idx)
    assert {m.topic_id for m in out} == {100}


def test_composite_rule_skips_when_composite_topic_missing_in_db() -> None:
    """Se il topic composite non è in DB (slug non in slug_to_id), nessuna
    sostituzione e le componenti restano intatte."""
    slug_to_id = {"google": 100, "gemini": 200}  # google-gemini assente
    idx = _build_index([], slug_to_id=slug_to_id)
    matches = [
        classify.TopicMatch(topic_id=100, score=2.0, in_title=True, in_body=True),
        classify.TopicMatch(topic_id=200, score=4.0, in_title=False, in_body=True),
    ]
    out = classify._apply_composite_rules(matches, idx)
    assert {m.topic_id for m in out} == {100, 200}


# ---------------------------------------------------------------------------
# T-016 Fix 4: drop PERSON colliding with curated non-person topic
# ---------------------------------------------------------------------------


def test_person_collides_with_curated_subject() -> None:
    """'Quantum Technology Monitor' contiene 'Monitor' che è un curated
    subject → la sequenza non è un PERSON, va scartata."""
    from app.topic_extractor.extractor import Candidate

    monitor = FakeTopic(
        id=99, display_name="Monitor", aliases=None, type="subject"
    )
    idx = _build_index([monitor], topic_id_to_type={99: "subject"})
    cand = Candidate(
        surface_form="Quantum Technology Monitor", ner_type="REGEX_PER"
    )
    assert classify._person_collides_with_curated(cand, idx) is True


def test_person_does_not_collide_with_real_person_curated() -> None:
    """Se un token coincide con un altro PERSON curated, non scartiamo
    (collisione tra persone è OK, il dedupe a valle gestisce)."""
    from app.topic_extractor.extractor import Candidate

    other_person = FakeTopic(
        id=88, display_name="Mario", aliases=None, type="person"
    )
    idx = _build_index([other_person], topic_id_to_type={88: "person"})
    cand = Candidate(surface_form="Mario Rossi", ner_type="REGEX_PER")
    assert classify._person_collides_with_curated(cand, idx) is False


def test_person_short_token_does_not_trigger_collision() -> None:
    """Token < 4 char (es. 'di', 'la') ignorati per evitare match spuri."""
    from app.topic_extractor.extractor import Candidate

    di = FakeTopic(id=77, display_name="DI", aliases=None, type="brand")
    idx = _build_index([di], topic_id_to_type={77: "brand"})
    cand = Candidate(surface_form="Mario Di Bella", ner_type="REGEX_PER")
    assert classify._person_collides_with_curated(cand, idx) is False


# ---------------------------------------------------------------------------
# Title skip pattern: articoli affiliate/commerciali → no extraction
# ---------------------------------------------------------------------------


def test_title_skip_pattern_matches_offerta_offerte() -> None:
    """Articoli con 'offerta'/'offerte' nel titolo (qualsiasi case) → skip."""
    pat = classify._TITLE_SKIP_PATTERN
    assert pat.search("Migliori offerte di maggio 2026")
    assert pat.search("L'offerta del giorno su Amazon")
    assert pat.search("OFFERTA Apple iPhone 17 256 GB")
    assert pat.search("Quante offerte con i NO IVA DAYS")
    # Boundary: dentro un'altra parola NON matcha
    assert not pat.search("controfferta dell'avversario")
    # Titoli normali NON matchano
    assert not pat.search("Tagli alle tasse e nuove riforme economiche")
