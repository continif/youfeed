"""Unit test per app.ingestion.wp_api (parsing puro)."""

from __future__ import annotations

from app.ingestion import wp_api


def _post_skel(**overrides: object) -> dict:
    base: dict = {
        "id": 42,
        "link": "https://wp.example.com/post-42",
        "title": {"rendered": "Titolo &amp; sottotitolo"},
        "excerpt": {"rendered": "<p>Riassunto breve</p>"},
        "content": {"rendered": "<p>Contenuto completo</p>"},
        "date_gmt": "2026-05-06T10:00:00",
        "modified_gmt": "2026-05-06T11:00:00",
        "status": "publish",
        "type": "post",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags() -> None:
    # selectolax separa con spazio tra i tag nested; collapse manuale.
    out = wp_api._strip_html("<p>Ciao <b>mondo</b></p>")
    assert out is not None
    assert " ".join(out.split()) == "Ciao mondo"


def test_strip_html_returns_none_for_empty() -> None:
    assert wp_api._strip_html("") is None
    assert wp_api._strip_html(None) is None


# ---------------------------------------------------------------------------
# _featured_image (preferenze: large > full > medium_large > medium > source_url)
# ---------------------------------------------------------------------------


def test_featured_image_prefers_large_size() -> None:
    post = {
        "_embedded": {
            "wp:featuredmedia": [
                {
                    "source_url": "https://x.com/orig.jpg",
                    "media_details": {
                        "sizes": {
                            "medium": {"source_url": "https://x.com/m.jpg"},
                            "large": {"source_url": "https://x.com/l.jpg"},
                            "full": {"source_url": "https://x.com/f.jpg"},
                        }
                    },
                }
            ]
        }
    }
    assert wp_api._featured_image(post) == "https://x.com/l.jpg"


def test_featured_image_falls_back_to_source_url() -> None:
    post = {
        "_embedded": {
            "wp:featuredmedia": [
                {"source_url": "https://x.com/orig.jpg", "media_details": {}}
            ]
        }
    }
    assert wp_api._featured_image(post) == "https://x.com/orig.jpg"


def test_featured_image_returns_none_when_no_media() -> None:
    assert wp_api._featured_image({}) is None
    assert wp_api._featured_image({"_embedded": {}}) is None


# ---------------------------------------------------------------------------
# _author / _taxonomy
# ---------------------------------------------------------------------------


def test_author_from_embedded() -> None:
    post = {"_embedded": {"author": [{"name": "Mario Rossi"}]}}
    assert wp_api._author(post) == "Mario Rossi"


def test_author_returns_none_when_missing() -> None:
    assert wp_api._author({}) is None
    assert wp_api._author({"_embedded": {"author": []}}) is None


def test_taxonomy_extracts_from_wp_term_groups() -> None:
    post = {
        "_embedded": {
            "wp:term": [
                [{"name": "Politica"}, {"name": "Italia"}],  # categories
                [{"name": "elezioni"}],  # tags
            ]
        }
    }
    assert wp_api._taxonomy(post) == ["Politica", "Italia", "elezioni"]


def test_taxonomy_returns_none_when_empty() -> None:
    assert wp_api._taxonomy({}) is None
    assert wp_api._taxonomy({"_embedded": {"wp:term": []}}) is None


# ---------------------------------------------------------------------------
# _post_to_candidate
# ---------------------------------------------------------------------------


def test_post_to_candidate_full() -> None:
    post = _post_skel(
        _embedded={
            "wp:featuredmedia": [
                {"source_url": "https://x.com/img.jpg", "media_details": {}}
            ],
            "author": [{"name": "Autore X"}],
            "wp:term": [[{"name": "tag-uno"}]],
        }
    )
    c = wp_api._post_to_candidate(post)
    assert c is not None
    assert c.external_id == "42"
    assert c.url_canonical == "https://wp.example.com/post-42"
    assert c.title  # strip HTML entities
    assert "Riassunto breve" in (c.description or "")
    assert c.content_html == "<p>Contenuto completo</p>"
    assert c.author == "Autore X"
    assert c.image_url == "https://x.com/img.jpg"
    assert c.origin_taxonomy == ["tag-uno"]
    assert c.published_at.year == 2026
    assert c.updated_at is not None


def test_post_to_candidate_returns_none_without_link() -> None:
    post = _post_skel()
    post["link"] = None
    assert wp_api._post_to_candidate(post) is None


def test_post_to_candidate_handles_invalid_date() -> None:
    post = _post_skel(date_gmt="not-a-date", modified_gmt=None)
    c = wp_api._post_to_candidate(post)
    assert c is not None
    # fallback a datetime.now(UTC) — verifichiamo solo che sia tz-aware
    assert c.published_at.tzinfo is not None
    assert c.updated_at is None
