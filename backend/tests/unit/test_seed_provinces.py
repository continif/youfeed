"""Unit test per il parser delle province (mojibake fix + slug)."""

from __future__ import annotations

from app.utils.seed_loader import _fix_mojibake


def test_mojibake_fix_recovers_italian_accents() -> None:
    # Casi reali dal CSV province-italiane: lettera mojibake seguita da
    # un'altra lettera (decode UTF-8 a 2 byte) — funziona.
    assert _fix_mojibake("ForlÃ¬-Cesena") == "Forlì-Cesena"
    assert _fix_mojibake("Ã¬") == "ì"
    assert _fix_mojibake("Ã²") == "ò"
    # NB: 'Ã ' (Ã + space normale 0x20) NON è UTF-8 valido (servirebbe NBSP
    # 0xA0). Casi come "FalcomatÃ " ritornano invariati — è atteso.


def test_mojibake_fix_returns_input_when_decode_fails() -> None:
    """Se il byte 0xc3 (Ã) è seguito da un non-continuation byte (es. spazio
    plain), il decode UTF-8 fallisce e ritorniamo l'input invariato."""
    # "FalcomatÃ " (Ã + spazio): c3 20 non è valido UTF-8 → input invariato
    assert _fix_mojibake("FalcomatÃ ") == "FalcomatÃ "


def test_mojibake_fix_idempotent_on_clean_strings() -> None:
    """Stringhe già UTF-8 pulite NON devono essere modificate (o rotte)."""
    assert _fix_mojibake("Roma") == "Roma"
    assert _fix_mojibake("Reggio Calabria") == "Reggio Calabria"
    assert _fix_mojibake("L'Aquila") == "L'Aquila"


def test_mojibake_fix_handles_empty_or_none() -> None:
    assert _fix_mojibake("") == ""


def test_mojibake_fix_returns_input_when_not_recoverable() -> None:
    """Se la stringa contiene caratteri non in CP1252 (es. emoji),
    encode/decode fallisce e la funzione ritorna l'input invariato."""
    assert _fix_mojibake("ciao 🇮🇹") == "ciao 🇮🇹"
