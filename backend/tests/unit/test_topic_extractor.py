"""Unit test per app.topic_extractor.extractor (regex puri, no DB)."""

from __future__ import annotations

import pytest

from app.topic_extractor import extractor as ex


def _surfaces(items, *, ner_type: str | None = None) -> list[str]:
    return [c.surface_form for c in items if ner_type is None or c.ner_type == ner_type]


# ---------------------------------------------------------------------------
# extract_persons — schema 2-4 token, primo non puntato
# ---------------------------------------------------------------------------


def test_person_two_full_words() -> None:
    out = ex.extract_persons("Ieri ho incontrato Mario Rossi al bar.")
    assert _surfaces(out) == ["Mario Rossi"]


def test_person_three_words() -> None:
    out = ex.extract_persons("Era presente Sergio Mattarella Junior.")
    assert _surfaces(out) == ["Sergio Mattarella Junior"]


def test_person_with_initial_in_middle() -> None:
    """'Donald J. Trump': iniziale puntata in posizione media."""
    out = ex.extract_persons("Il candidato Donald J. Trump ha dichiarato...")
    assert "Donald J. Trump" in _surfaces(out)


def test_person_with_double_initial() -> None:
    """'Donald J. F. Kennedy': due iniziali puntate."""
    out = ex.extract_persons("Visite a Donald J. F. Kennedy ieri.")
    assert "Donald J. F. Kennedy" in _surfaces(out)


def test_person_with_sigla_first() -> None:
    """'JD Vance': sigla all-caps come primo token."""
    out = ex.extract_persons("Il senatore JD Vance ha votato sì.")
    assert "JD Vance" in _surfaces(out)


def test_person_does_not_match_single_capital_word() -> None:
    """Donald da solo a inizio frase NON deve essere considerato persona."""
    out = ex.extract_persons("Era ottimo. Donald iniziò la conferenza.")
    assert _surfaces(out) == []


def test_person_does_not_match_isolated_initial() -> None:
    """'J. Trump' (senza nome iniziale) non deve essere catturato come persona."""
    out = ex.extract_persons("Solo J. Trump ha parlato.")
    # Non c'è un FIRST valido (J. è iniziale, non full o sigla)
    assert "Trump" not in _surfaces(out)
    assert "J. Trump" not in _surfaces(out)


def test_person_in_middle_of_sentence_after_period() -> None:
    """'Donald J. Trump' dopo il punto (di un'iniziale precedente) NON deve essere
    interpretato come falso positivo da fine-frase."""
    out = ex.extract_persons(
        "Il presidente è Donald J. Trump da tre anni."
    )
    assert "Donald J. Trump" in _surfaces(out)


def test_person_skips_blacklisted_sigla() -> None:
    """Sigle italiane comuni (DEL, LE, AL) non vengono mai considerate persone."""
    # "DEL Cristo Roma" non è un nome.
    out = ex.extract_persons("Vide DEL Cristo Roma alla porta.")
    # DEL è in blacklist → match scartato. "Cristo Roma" potrebbe matchare
    # come 2-token full → vero, ma non lo testiamo qui.
    assert all("DEL" not in s for s in _surfaces(out))


def test_person_with_italian_accents() -> None:
    out = ex.extract_persons("Visita a Niccolò Machiavelli al museo.")
    assert "Niccolò Machiavelli" in _surfaces(out)


def test_person_no_match_in_empty_or_whitespace() -> None:
    assert ex.extract_persons("") == []
    assert ex.extract_persons("   ") == []


def test_person_trims_blacklisted_tail_token() -> None:
    """T-016 Fix 2: trim END dei token blacklist (verbi italiani capitalizzati
    come 'Punti'). 'Pierluigi Sandonnini Punti' → 'Pierluigi Sandonnini'."""
    out = ex.extract_persons(
        "Il giornalista Pierluigi Sandonnini Punti aveva scritto"
    )
    assert "Pierluigi Sandonnini" in _surfaces(out)
    assert "Pierluigi Sandonnini Punti" not in _surfaces(out)


def test_person_trims_both_head_and_tail() -> None:
    """T-016 Fix 2: trim su HEAD e TAIL combinati."""
    out = ex.extract_persons("Anche Mario Rossi Disse cose")
    assert "Mario Rossi" in _surfaces(out)


def test_person_drops_when_only_blacklisted_after_trim() -> None:
    """Se dopo trim restano < 2 token, scarta."""
    out = ex.extract_persons("Inoltre Davvero Punti")
    assert out == []


# ---------------------------------------------------------------------------
# extract_popes
# ---------------------------------------------------------------------------


def test_pope_simple() -> None:
    out = ex.extract_popes("Oggi Papa Francesco ha detto messa.")
    assert _surfaces(out) == ["Papa Francesco"]


def test_pope_with_two_names() -> None:
    out = ex.extract_popes("Storia di Papa Giovanni Paolo nel 1978.")
    assert "Papa Giovanni Paolo" in _surfaces(out)


def test_pope_with_roman_numeral() -> None:
    out = ex.extract_popes("Papa Giovanni Paolo II è stato santificato.")
    assert "Papa Giovanni Paolo II" in _surfaces(out)


def test_pope_with_three_names_and_roman() -> None:
    out = ex.extract_popes("Papa Pio Tertio Maria IV (fittizio).")
    assert "Papa Pio Tertio Maria IV" in _surfaces(out)


def test_pope_skips_when_no_names_after_papa() -> None:
    out = ex.extract_popes("Il papa è arrivato a Roma.")
    # "papa" lower-case → no match
    assert _surfaces(out) == []


# ---------------------------------------------------------------------------
# extract_brand_alphanum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("La nuova 7Up costa meno", ["7Up"]),
        ("La 3M annuncia nuovi prodotti", ["3M"]),
        ("La rete O2 è veloce.", ["O2"]),
        ("La BMW e la IBM si fondono", ["BMW", "IBM"]),
        ("La RAI ha trasmesso live.", ["RAI"]),
        # F1 = sport, K2 = montagna — entrambi candidati legittimi
        ("La gara di F1 a Monaco con K2 nei poster", ["F1", "K2"]),
    ],
)
def test_brand_alphanum_matches(text: str, expected: list[str]) -> None:
    out = _surfaces(ex.extract_brand_alphanum(text))
    for e in expected:
        assert e in out


def test_brand_alphanum_skips_blacklisted_short_sigla() -> None:
    """'DI', 'LE' all-caps in mezzo a un titolo non sono brand."""
    out = ex.extract_brand_alphanum("DI questo si parla. LE persone votano.")
    assert "DI" not in _surfaces(out)
    assert "LE" not in _surfaces(out)


def test_brand_alphanum_does_not_match_full_word_with_lowercase() -> None:
    """'Apple' è full word (4+ char) → NON deve essere catturato qui (pattern
    BRAND_SINGLE)."""
    out = ex.extract_brand_alphanum("La Apple presenta un nuovo modello.")
    assert "Apple" not in _surfaces(out)


# ---------------------------------------------------------------------------
# extract_brand_single (mid-sentence)
# ---------------------------------------------------------------------------


def test_brand_single_mid_sentence_after_lowercase() -> None:
    out = ex.extract_brand_single("La nuova Adidas è uscita ieri.")
    assert "Adidas" in _surfaces(out)


def test_brand_single_mid_sentence_after_comma() -> None:
    out = ex.extract_brand_single("Le marche presenti, Apple, Adidas, sono qui.")
    surfaces = _surfaces(out)
    assert "Apple" in surfaces
    assert "Adidas" in surfaces


def test_brand_single_skips_start_of_sentence() -> None:
    """A inizio frase la parola capitalizzata è ambigua (potrebbe essere
    inizio frase normale) → non la consideriamo brand."""
    out = ex.extract_brand_single("Adidas presenta una nuova linea.")
    assert "Adidas" not in _surfaces(out)


def test_brand_single_skips_after_period() -> None:
    out = ex.extract_brand_single("Pioveva. Apple presentò il prodotto.")
    assert "Apple" not in _surfaces(out)


def test_brand_single_skips_blacklisted_words() -> None:
    """'Tuttavia', 'Inoltre', mesi italiani capitalizzati non sono brand."""
    out = ex.extract_brand_single("vediamo, Tuttavia procediamo a luglio")
    assert "Tuttavia" not in _surfaces(out)


def test_brand_single_requires_min_4_chars() -> None:
    out = ex.extract_brand_single("la sua Bmw è veloce")
    # "Bmw" è 3 char (B+mw) — sotto soglia per BRAND_SINGLE (richiede 3 minuscole)
    assert "Bmw" not in _surfaces(out)


@pytest.mark.parametrize(
    "text,word",
    [
        # Sample S-001 (Razer)
        ("Risparmia ben 80€ sulla, Bomba di Razer per laptop.", "Bomba"),
        ("La nuova, Fascia di prodotti è uscita.", "Fascia"),
        ("Sul, Canale ufficiale è disponibile lo spot.", "Canale"),
        # Sample S-002 (Lenovo)
        ("L'offerta non, Rende il prezzo competitivo.", "Rende"),
        ("Il prezzo, Dello sconto è ottimo.", "Dello"),
        # Sample S-003 (Megan Gale)
        ("Lo spot, Campagna pubblicitaria della testimonial.", "Campagna"),
        # Comuni capitalizzati per enfasi titolare
        ("è arrivata, Davvero la novità del mese.", "Davvero"),
        ("Il prezzo è, Soltanto 89€ su Amazon.", "Soltanto"),
        ("ha appena, Annunciato la promozione.", "Annunciato"),
        # Componenti di location multi-parola (estratti già dal dict come frase)
        ("ministro inglese del, Regno Unito ha confermato", "Regno"),
        ("ministro inglese del, Regno Unito ha confermato", "Unito"),
        # Sostantivi giornalistici/finanziari generici
        ("le, Fonti del governo confermano", "Fonti"),
        ("una, Fonte interna ha riferito", "Fonte"),
        ("il, Sostegno economico è arrivato", "Sostegno"),
        ("la, Cassa Depositi ha investito", "Cassa"),
        # T-014: comuni IT collidenti con verbi/aggettivi/sostantivi italiani comuni
        ("la sua, Mira è precisa al millimetro", "Mira"),
        ("è, Alto il rischio di recessione", "Alto"),
        ("la, Posta in gioco è la riforma fiscale", "Posta"),
    ],
)
def test_brand_single_blacklist_extended_italian_common_words(text: str, word: str) -> None:
    """T-001: la blacklist deve scartare sostantivi/avverbi/voci-verbali italiani
    comuni capitalizzati per enfasi (i 3 sample S-001/S-002/S-003 contaminati)."""
    out = ex.extract_brand_single(text)
    assert word not in _surfaces(out), (
        f"'{word}' è entrato come BRAND_SINGLE: lista contaminata"
    )


# ---------------------------------------------------------------------------
# extract_models
# ---------------------------------------------------------------------------


def test_model_brand_plus_number() -> None:
    out = ex.extract_models(
        "La nuova Porsche 911 è più larga del modello precedente.",
        known_brands=["Porsche", "Boeing"],
    )
    assert "Porsche 911" in _surfaces(out)


def test_model_brand_plus_number_plus_word() -> None:
    out = ex.extract_models(
        "Quella Alfa Romeo 33 Stradale gira per Montecarlo.",
        known_brands=["Alfa Romeo", "Porsche"],
    )
    assert "Alfa Romeo 33 Stradale" in _surfaces(out)


def test_model_brand_plus_word_only_no_number() -> None:
    out = ex.extract_models(
        "La Fiat Panda è popolare in Italia.",
        known_brands=["Fiat"],
    )
    assert "Fiat Panda" in _surfaces(out)


def test_model_skips_when_brand_not_known() -> None:
    out = ex.extract_models(
        "La Lamborghini Huracán è veloce.",
        known_brands=["Porsche", "Boeing"],
    )
    assert _surfaces(out) == []


def test_model_brand_longest_match_first() -> None:
    """Quando 'Alfa Romeo' è in known_brands, deve prevalere su 'Alfa'."""
    out = ex.extract_models(
        "Una Alfa Romeo 33 Stradale e una Alfa 156.",
        known_brands=["Alfa", "Alfa Romeo"],
    )
    surfaces = _surfaces(out)
    assert "Alfa Romeo 33 Stradale" in surfaces
    assert "Alfa 156" in surfaces


def test_model_alphanumeric_token_with_dash_lenovo() -> None:
    """T-003: nomi modello con dash interno (Lenovo L27-41, Sony WH-1000XM5)."""
    out = ex.extract_models(
        "Il monitor Lenovo L27-41 è in offerta su Amazon.",
        known_brands=["Lenovo", "Sony"],
    )
    assert "Lenovo L27-41" in _surfaces(out)


def test_model_alphanumeric_token_with_dash_sony() -> None:
    out = ex.extract_models(
        "Le cuffie Sony WH-1000XM5 sono al minimo storico.",
        known_brands=["Sony"],
    )
    assert "Sony WH-1000XM5" in _surfaces(out)


def test_model_camelcase_iphone() -> None:
    """T-003: i nomi prodotto camelCase tipo 'iPhone' devono essere matchati
    quando seguono il brand."""
    out = ex.extract_models(
        "Il nuovo Apple iPhone 15 Pro è in vendita.",
        known_brands=["Apple"],
    )
    surfaces = _surfaces(out)
    # Almeno "Apple iPhone" o "Apple iPhone 15" o "Apple iPhone 15 Pro"
    assert any(s.startswith("Apple iPhone") for s in surfaces), surfaces


# ---------------------------------------------------------------------------
# extract_all (orchestrator)
# ---------------------------------------------------------------------------


def test_extract_all_full_sentence_from_user_example() -> None:
    text = (
        "a Montecarlo vediamo Valteri Bottas con la sua "
        "Alfa Romeo 33 Stradale girare per le strade dello shopping"
    )
    out = ex.extract_all(text, known_brands=["Alfa Romeo", "Porsche"])
    surfaces = _surfaces(out)
    # Persona
    assert "Valteri Bottas" in surfaces
    # Model
    assert "Alfa Romeo 33 Stradale" in surfaces
    # Brand single (Montecarlo è dopo "a" minuscolo)
    assert "Montecarlo" in surfaces


def test_extract_all_dedupe_within_text() -> None:
    """Stessa surface_form non deve apparire più volte per lo stesso ner_type
    nello stesso testo (la frequenza si aggrega per articolo, non per match)."""
    text = "Mario Rossi e poi ancora Mario Rossi al bar."
    out = ex.extract_persons(text)
    assert _surfaces(out) == ["Mario Rossi"]


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_lowercases_and_collapses_whitespace() -> None:
    assert ex.normalize("  Donald J. Trump  ") == "donald j. trump"
    assert ex.normalize("Papa\tFrancesco\nI") == "papa francesco i"
