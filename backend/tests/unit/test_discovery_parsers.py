"""Test puri sui parser di discovery (no rete)."""

from __future__ import annotations

import json

import httpx
import pytest
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
# Bot-challenge title sanitization
# ---------------------------------------------------------------------------


def test_looks_like_bot_challenge_matches_known_strings() -> None:
    assert discovery._looks_like_bot_challenge("Just a moment...")
    assert discovery._looks_like_bot_challenge("Attention Required! | Cloudflare")
    assert discovery._looks_like_bot_challenge("Access denied")
    assert discovery._looks_like_bot_challenge("Checking your browser before…")
    # Case insensitive
    assert discovery._looks_like_bot_challenge("JUST A MOMENT")


def test_looks_like_bot_challenge_skips_real_titles() -> None:
    assert not discovery._looks_like_bot_challenge("Corriere della Sera")
    assert not discovery._looks_like_bot_challenge("Il sito di esempio")
    assert not discovery._looks_like_bot_challenge(None)
    assert not discovery._looks_like_bot_challenge("")


def test_extract_og_drops_bot_challenge_title() -> None:
    """Cloudflare challenge → og.title messo a None così il chiamante può ripiegare."""
    html = HTMLParser(
        '<html><head><title>Just a moment...</title>'
        '<meta property="og:title" content="Just a moment..."></head></html>'
    )
    og = discovery._extract_og(html, "https://example.com")
    assert og.title is None


# ---------------------------------------------------------------------------
# End-to-end: bot-challenge fallback in _discover_inner
# ---------------------------------------------------------------------------


_RSS_FEED_BYTES = (
    b'<?xml version="1.0"?>'
    b'<rss version="2.0"><channel>'
    b"<title>Sito Reale</title>"
    b"<link>https://example.com</link>"
    b"<description>desc</description>"
    b"<item><title>Articolo</title><link>https://example.com/a</link></item>"
    b"</channel></rss>"
)


_CHALLENGE_HTML = (
    b"<html><head><title>Just a moment...</title></head>"
    b'<body><link rel="alternate" type="application/rss+xml" '
    b'href="https://example.com/feed"></body></html>'
)


_CHALLENGE_HTML_WITH_FEED_LINK = (
    b'<html><head><title>Just a moment...</title>'
    b'<link rel="alternate" type="application/rss+xml" '
    b'href="https://example.com/feed"></head></html>'
)


@pytest.mark.asyncio
async def test_discover_inner_falls_back_to_feed_title_under_cloudflare() -> None:
    """Sito dietro Cloudflare → og.title diventa il `<channel><title>` del feed."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/feed"):
            return httpx.Response(
                200,
                headers={"content-type": "application/rss+xml"},
                content=_RSS_FEED_BYTES,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=_CHALLENGE_HTML_WITH_FEED_LINK,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discovery._discover_inner(client, "https://example.com/")

    assert result.kind == "rss"
    assert result.og.title == "Sito Reale"
    assert result.candidates[0].title == "Sito Reale"


@pytest.mark.asyncio
async def test_discover_inner_direct_feed_url_populates_og_title() -> None:
    """URL diretto a un feed RSS → og.title è il titolo del feed (non più None)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            content=_RSS_FEED_BYTES,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discovery._discover_inner(
            client, "https://example.com/feed"
        )

    assert result.kind == "rss"
    assert result.og.title == "Sito Reale"


@pytest.mark.asyncio
async def test_discover_inner_wp_api_falls_back_to_wpjson_name() -> None:
    """Sito WordPress dietro Cloudflare → og.title preso da `/wp-json/` root."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/wp-json/wp/v2/posts?per_page=1"):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b"[]",
            )
        if url.endswith("/wp-json") or url.endswith("/wp-json/"):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=json.dumps(
                    {"name": "FinanzaOnline", "description": "..."}
                ).encode(),
            )
        # HTML challenge con link a wp-json
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=(
                b'<html><head><title>Just a moment...</title>'
                b'<link rel="https://api.w.org/" '
                b'href="https://example.com/wp-json/"></head></html>'
            ),
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discovery._discover_inner(client, "https://example.com/")

    assert result.kind == "wordpress_api"
    assert result.og.title == "FinanzaOnline"


# ---------------------------------------------------------------------------
# Normalize URL
# ---------------------------------------------------------------------------


def test_normalize_url_adds_scheme() -> None:
    assert discovery._normalize_url("example.com") == "https://example.com"
    assert discovery._normalize_url("  http://x.it ") == "http://x.it"
    assert discovery._normalize_url("https://x.it") == "https://x.it"
    assert discovery._normalize_url("") == ""
