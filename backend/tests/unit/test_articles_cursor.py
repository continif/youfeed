"""Unit test per il cursor keyset di app.services.articles_service."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import articles_service as svc


def test_cursor_roundtrip() -> None:
    ts = datetime(2026, 5, 6, 12, 30, 45, tzinfo=UTC)
    enc = svc._encode_cursor(ts, 12345)
    dec = svc._decode_cursor(enc)
    assert dec is not None
    out_ts, out_id = dec
    assert out_id == 12345
    # microseconds=0 -> isoformat ritorna senza microsecondi; verifichiamo i campi
    assert out_ts.year == 2026
    assert out_ts.tzinfo is not None


def test_cursor_with_microseconds() -> None:
    ts = datetime(2026, 5, 6, 12, 30, 45, 123456, tzinfo=UTC)
    enc = svc._encode_cursor(ts, 1)
    dec = svc._decode_cursor(enc)
    assert dec is not None
    out_ts, _ = dec
    assert out_ts.microsecond == 123456


def test_cursor_decode_returns_none_for_garbage() -> None:
    assert svc._decode_cursor("not-base64") is None
    assert svc._decode_cursor("") is None
    # base64 valido ma payload malformato
    import base64

    bad = base64.urlsafe_b64encode(b"no-pipe-separator").decode()
    assert svc._decode_cursor(bad) is None


def test_cursor_decode_handles_missing_padding() -> None:
    """encode rimuove il padding `=`; decode deve aggiungerlo."""
    ts = datetime(2026, 5, 6, 12, 30, 45, tzinfo=UTC)
    enc = svc._encode_cursor(ts, 999)
    assert "=" not in enc  # padding rimosso
    dec = svc._decode_cursor(enc)
    assert dec is not None
    assert dec[1] == 999


def test_public_image_url_with_path() -> None:
    assert svc._public_image_url("ab/cd/abcd.webp").endswith("/ab/cd/abcd.webp")


def test_public_image_url_with_none() -> None:
    assert svc._public_image_url(None) is None
