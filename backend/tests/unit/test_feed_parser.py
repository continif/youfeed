"""Unit test per app.ingestion.feed_parser (parsing puro, no I/O)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from app.ingestion import feed_parser as fp


# ---------------------------------------------------------------------------
# make_url_hash
# ---------------------------------------------------------------------------


def test_make_url_hash_is_deterministic() -> None:
    h1 = fp.make_url_hash("https://example.com/a")
    h2 = fp.make_url_hash("https://example.com/a")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_make_url_hash_differs_for_different_urls() -> None:
    assert fp.make_url_hash("https://a.com") != fp.make_url_hash("https://b.com")


def test_make_url_hash_strips_whitespace() -> None:
    assert fp.make_url_hash("  https://x  ") == fp.make_url_hash("https://x")


# ---------------------------------------------------------------------------
# _parse_dt
# ---------------------------------------------------------------------------


def test_parse_dt_struct_time() -> None:
    st = time.struct_time((2026, 1, 15, 10, 30, 0, 0, 0, 0))
    out = fp._parse_dt(st)
    assert out == datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)


def test_parse_dt_rfc822_string() -> None:
    out = fp._parse_dt("Wed, 06 May 2026 12:00:00 GMT")
    assert out is not None
    assert out.year == 2026 and out.month == 5 and out.day == 6


def test_parse_dt_iso_string_with_z() -> None:
    out = fp._parse_dt("2026-05-06T12:00:00Z")
    assert out is not None
    assert out.tzinfo is not None


def test_parse_dt_returns_none_for_garbage() -> None:
    assert fp._parse_dt("nonsense") is None
    assert fp._parse_dt("") is None
    assert fp._parse_dt(None) is None


# ---------------------------------------------------------------------------
# _extract_image (preferenze ordinate)
# ---------------------------------------------------------------------------


def test_extract_image_prefers_media_thumbnail() -> None:
    entry = {
        "media_thumbnail": [{"url": "https://x.com/thumb.jpg"}],
        "media_content": [{"url": "https://x.com/full.jpg"}],
        "enclosures": [{"href": "https://x.com/enc.jpg", "type": "image/jpeg"}],
    }
    assert fp._extract_image(entry, "https://x.com") == "https://x.com/thumb.jpg"


def test_extract_image_falls_back_to_enclosure() -> None:
    entry = {
        "enclosures": [
            {"href": "https://x.com/audio.mp3", "type": "audio/mpeg"},
            {"href": "https://x.com/img.png", "type": "image/png"},
        ]
    }
    # primo enclosure non-image è scartato, prende il secondo
    assert fp._extract_image(entry, "https://x.com") == "https://x.com/img.png"


def test_extract_image_falls_back_to_html_img() -> None:
    entry = {
        "content": [
            {"value": '<p>testo</p><img src="/relative.jpg"><p>fine</p>'}
        ]
    }
    # urljoin risolve il path relativo contro base_url
    assert fp._extract_image(entry, "https://x.com/articolo") == "https://x.com/relative.jpg"


def test_extract_image_returns_none_when_nothing_matches() -> None:
    assert fp._extract_image({}, "https://x.com") is None
    assert fp._extract_image({"summary": "no img"}, "https://x.com") is None


# ---------------------------------------------------------------------------
# _entry_to_candidate
# ---------------------------------------------------------------------------


def test_entry_to_candidate_minimal() -> None:
    entry = {
        "title": "Titolo",
        "link": "https://x.com/a",
        "published_parsed": time.struct_time((2026, 5, 6, 0, 0, 0, 0, 0, 0)),
    }
    c = fp._entry_to_candidate(entry, "https://x.com")
    assert c is not None
    assert c.title == "Titolo"
    assert c.url_canonical == "https://x.com/a"
    assert c.url_hash == fp.make_url_hash("https://x.com/a")
    assert c.published_at.year == 2026


def test_entry_to_candidate_returns_none_without_link_or_title() -> None:
    assert fp._entry_to_candidate({"title": "x"}, "https://x.com") is None
    assert fp._entry_to_candidate({"link": "https://x.com/a"}, "https://x.com") is None


def test_entry_to_candidate_falls_back_to_now_if_no_dates() -> None:
    entry = {"title": "T", "link": "https://x.com/a"}
    c = fp._entry_to_candidate(entry, "https://x.com")
    assert c is not None
    # published_at deve essere "ora" (entro qualche minuto): basta verificare TZ-aware
    assert c.published_at.tzinfo is not None


def test_entry_to_candidate_truncates_long_title() -> None:
    entry = {"title": "x" * 2000, "link": "https://x.com/a"}
    c = fp._entry_to_candidate(entry, "https://x.com")
    assert c is not None
    assert len(c.title) == 1000


@pytest.mark.parametrize(
    "tags,expected",
    [
        ([{"term": "Politica"}, {"term": "Economia"}], ["Politica", "Economia"]),
        ([{"label": "Cronaca"}], ["Cronaca"]),
        ([], None),
        ([{}], None),
    ],
)
def test_extract_taxonomy(tags: list, expected: list | None) -> None:
    out = fp._extract_taxonomy({"tags": tags})
    assert out == expected
