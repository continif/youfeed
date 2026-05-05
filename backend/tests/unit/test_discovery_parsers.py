"""Test puri sui parser di discovery (no rete)."""

from __future__ import annotations

from selectolax.parser import HTMLParser

from app.ingestion import discovery


# ---------------------------------------------------------------------------
# Parsing feed (RSS/Atom/JSON Feed)
# ---------------------------------------------------------------------------


def test_try_parse_rss_minimal() -> None:
    rss = b"""<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Esempio</title>
        <link>https://example.com</link>
        <description>desc</description>
        <item>
          <title>Articolo 1</title>
          <link>https://example.com/a1</link>
          <pubDate>Mon, 05 May 2026 08:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>"""
    title, sample = discovery._try_parse_feed(rss)
    assert title == "Esempio"
    assert len(sample) == 1
    assert sample[0]["title"] == "Articolo 1"
    assert sample[0]["url"] == "https://example.com/a1"


def test_try_parse_atom_minimal() -> None:
    atom = b"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>AtomFeed</title>
      <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
      <updated>2026-05-05T18:30:02Z</updated>
      <entry>
        <title>Voce 1</title>
        <link href="https://example.com/v1"/>
        <id>urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a</id>
        <updated>2026-05-05T18:30:02Z</updated>
      </entry>
    </feed>"""
    title, sample = discovery._try_parse_feed(atom)
    assert title == "AtomFeed"
    assert len(sample) == 1
    assert sample[0]["url"] == "https://example.com/v1"


def test_try_parse_garbage_returns_empty() -> None:
    title, sample = discovery._try_parse_feed(b"<html>not a feed</html>")
    assert title is None
    assert sample == []


# ---------------------------------------------------------------------------
# WordPress detection
# ---------------------------------------------------------------------------


def test_wp_root_from_link_header() -> None:
    h = '<https://example.com/wp-json/>; rel="https://api.w.org/"'
    assert (
        discovery._wp_root_from_link_header(h)
        == "https://example.com/wp-json/wp/v2"
    )


def test_wp_root_from_link_header_multiple() -> None:
    h = (
        '<https://example.com/page>; rel="canonical", '
        '<https://example.com/wp-json/>; rel="https://api.w.org/"'
    )
    assert (
        discovery._wp_root_from_link_header(h)
        == "https://example.com/wp-json/wp/v2"
    )


def test_wp_root_from_link_header_absent() -> None:
    h = '<https://example.com/page>; rel="canonical"'
    assert discovery._wp_root_from_link_header(h) is None
    assert discovery._wp_root_from_link_header(None) is None


def test_wp_root_from_html() -> None:
    html = HTMLParser(
        """
    <html><head>
      <link rel="https://api.w.org/" href="https://example.com/wp-json/">
    </head><body></body></html>
    """
    )
    assert (
        discovery._wp_root_from_html(html, "https://example.com")
        == "https://example.com/wp-json/wp/v2"
    )


# ---------------------------------------------------------------------------
# Feed in HTML
# ---------------------------------------------------------------------------


def test_feeds_from_html() -> None:
    html = HTMLParser(
        """
    <html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml" title="RSS">
      <link rel="alternate" type="application/atom+xml" href="https://other.example/atom" title="Atom">
      <link rel="alternate" type="application/json" href="/feed.json">
    </head></html>
    """
    )
    feeds = discovery._feeds_from_html(html, "https://example.com")
    assert "https://example.com/feed.xml" in feeds
    assert "https://other.example/atom" in feeds
    # application/json non è un feed
    assert "https://example.com/feed.json" not in feeds


def test_feeds_from_html_jsonfeed() -> None:
    html = HTMLParser(
        """
    <html><head>
      <link rel="alternate" type="application/feed+json" href="/feed.json">
    </head></html>
    """
    )
    feeds = discovery._feeds_from_html(html, "https://example.com")
    assert feeds == ["https://example.com/feed.json"]


# ---------------------------------------------------------------------------
# OG extraction
# ---------------------------------------------------------------------------


def test_extract_og_full() -> None:
    html = HTMLParser(
        """
    <html><head>
      <title>Sito Esempio</title>
      <meta property="og:title" content="Pagina Esempio">
      <meta property="og:description" content="Descrizione bella">
      <meta property="og:image" content="https://cdn.example/img.jpg">
      <meta property="og:site_name" content="Esempio">
      <link rel="icon" href="/favicon.ico">
    </head></html>
    """
    )
    og = discovery._extract_og(html, "https://example.com/path")
    assert og.title == "Pagina Esempio"
    assert og.description == "Descrizione bella"
    assert og.image == "https://cdn.example/img.jpg"
    assert og.site_name == "Esempio"
    assert og.favicon == "https://example.com/favicon.ico"


def test_extract_og_fallback_title() -> None:
    """Senza og:title, usa <title>; senza og:image, lascia None."""
    html = HTMLParser("<html><head><title>Solo Title</title></head></html>")
    og = discovery._extract_og(html, "https://example.com")
    assert og.title == "Solo Title"
    assert og.image is None
    # Favicon di fallback
    assert og.favicon == "https://example.com/favicon.ico"


# ---------------------------------------------------------------------------
# Normalize URL
# ---------------------------------------------------------------------------


def test_normalize_url_adds_scheme() -> None:
    assert discovery._normalize_url("example.com") == "https://example.com"
    assert discovery._normalize_url("  http://x.it ") == "http://x.it"
    assert discovery._normalize_url("https://x.it") == "https://x.it"
    assert discovery._normalize_url("") == ""
