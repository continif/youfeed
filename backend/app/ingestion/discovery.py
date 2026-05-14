"""Discovery URL: qualifica una URL fornita dall'utente.

Output: oggetto `DiscoveryResult` con:
  - kind: 'rss' | 'wordpress_api' | 'invalid'
  - url_feed (per kind=rss) — il feed scelto come "preferito"
  - wp_api_root (per kind=wordpress_api)
  - candidates: lista di tutti i feed RSS rilevati con preview (per UX
    di scelta multipla nella SourceWizard)
  - og: blocco Open Graph del sito (titolo, descrizione, immagine, favicon)
  - reason: stringa human-readable se invalid

Vedi `.claude/INGESTION.md` → "Parte 1 — Elaborazione URL" per la spec.

Niente accesso a DB qui: questa funzione è pura I/O esterno + parsing.
Il salvataggio in `sources` è responsabilità del router/service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import structlog
from selectolax.parser import HTMLParser

log = structlog.get_logger()


USER_AGENT = "YouFeed/1.0 (+https://www.youfeed.it/bot)"

FEED_CONTENT_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
    "application/feed+json",
)

WP_LINK_REL = "https://api.w.org/"

# Path comuni dove cercare un feed se l'HTML non lo dichiara
COMMON_FEED_PATHS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/feed.json",
)

# Titoli ritornati da pagine di anti-bot/challenge (Cloudflare ecc.) invece del
# sito reale. Match case-insensitive su sottostringa: se compare uno di questi
# in `<title>`, scartiamo il titolo HTML e proviamo a ripiegare sul titolo del
# feed RSS o sul nome del sito esposto da `wp-json/`.
BAD_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "cloudflare",
    "checking your browser",
    "ddos protection by",
    "please enable cookies",
    "verify you are human",
    "one moment, please",
)


def _looks_like_bot_challenge(title: str | None) -> bool:
    if not title:
        return False
    low = title.strip().lower()
    return any(m in low for m in BAD_TITLE_MARKERS)


# ---------------------------------------------------------------------------
# Data classes (output)
# ---------------------------------------------------------------------------


@dataclass
class FeedCandidate:
    """Singolo feed candidato + anteprima."""

    url_feed: str
    title: str | None = None
    sample_articles: list[dict[str, str]] = field(default_factory=list)
    # Sample: [{"title": "...", "url": "...", "published_at": "..."}]


@dataclass
class OgPreview:
    """Open Graph + favicon del sito."""

    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None
    favicon: str | None = None


@dataclass
class DiscoveryResult:
    kind: str  # 'rss' | 'wordpress_api' | 'invalid'
    url_site: str | None = None
    url_feed: str | None = None
    wp_api_root: str | None = None
    candidates: list[FeedCandidate] = field(default_factory=list)
    og: OgPreview = field(default_factory=OgPreview)
    reason: str | None = None
    discovery_meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _is_feed_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    primary = content_type.split(";", 1)[0].strip().lower()
    return primary in FEED_CONTENT_TYPES


_CFFI_FALLBACK_STATUSES = frozenset({403, 503, 520, 521, 522, 523, 524, 525, 526})


class _ResponseShim:
    """Adattatore minimale fra `curl_cffi` Response e l'interfaccia httpx
    usata in questo modulo (status_code, headers.get, content, text, url).
    """

    __slots__ = ("status_code", "headers", "content", "text", "url")

    def __init__(self, cr: object) -> None:
        self.status_code = int(getattr(cr, "status_code", 0))
        self.headers = dict(getattr(cr, "headers", {}) or {})
        self.content = getattr(cr, "content", b"")
        self.text = getattr(cr, "text", "")
        self.url = getattr(cr, "url", "")


async def _fetch_impersonate(url: str) -> "_ResponseShim | None":
    """Fallback per siti dietro Cloudflare / anti-bot. Usa `curl_cffi` con
    TLS fingerprint Chrome, l'unica strategia affidabile contro CF challenge.
    """
    try:
        from curl_cffi.requests import AsyncSession  # import lazy
    except ImportError:
        log.debug("yf.discovery.cffi_missing")
        return None
    try:
        async with AsyncSession() as s:
            cr = await s.get(url, impersonate="chrome", timeout=10.0)
        return _ResponseShim(cr)
    except Exception as e:  # curl_cffi solleva tipi vari
        log.debug("yf.discovery.cffi_failed", url=url, error=str(e))
        return None


async def _fetch(client: httpx.AsyncClient, url: str) -> "httpx.Response | _ResponseShim | None":
    try:
        r = await client.get(url, follow_redirects=True, timeout=10.0)
    except httpx.HTTPError as e:
        log.debug("yf.discovery.fetch_failed", url=url, error=str(e))
        # Anche `httpx.HTTPError` può nascondere un blocco TLS — riprova cffi
        return await _fetch_impersonate(url)
    if r.status_code in _CFFI_FALLBACK_STATUSES:
        # Probabile challenge anti-bot: prova con TLS fingerprint browser-like
        alt = await _fetch_impersonate(url)
        if alt is not None and alt.status_code == 200:
            log.info("yf.discovery.cffi_bypass", url=url, original_status=r.status_code)
            return alt
    return r


# ---------------------------------------------------------------------------
# Step 1 — probe diretto
# ---------------------------------------------------------------------------


def _try_parse_feed(content: bytes) -> tuple[str | None, list[dict[str, str]]]:
    """Parse RSS/Atom/JSON Feed. Ritorna (titolo_feed, sample_articles[:3])."""
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        # JSON Feed?
        try:
            data = json.loads(content)
            if data.get("version", "").startswith("https://jsonfeed.org/"):
                title = data.get("title")
                items = data.get("items") or []
                sample = [
                    {
                        "title": str(it.get("title", ""))[:200],
                        "url": str(it.get("url", "")),
                        "published_at": str(it.get("date_published", "")),
                    }
                    for it in items[:3]
                ]
                return title, sample
        except Exception:
            return None, []
        return None, []

    title = (parsed.feed or {}).get("title")
    entries = parsed.entries or []
    if not entries:
        return title, []

    sample = []
    for entry in entries[:3]:
        sample.append(
            {
                "title": str(getattr(entry, "title", ""))[:200],
                "url": str(getattr(entry, "link", "")),
                "published_at": str(
                    getattr(entry, "published", "") or getattr(entry, "updated", "")
                ),
            }
        )
    return title, sample


# ---------------------------------------------------------------------------
# Step 2 — rilevamento WordPress API
# ---------------------------------------------------------------------------


def _wp_root_from_link_header(link_header: str | None) -> str | None:
    """Cerca `Link: <https://example/wp-json/>; rel="https://api.w.org/"`."""
    if not link_header:
        return None
    # Parse semplice (RFC 5988): split per virgola, ogni entry "<url>; rel=...; ..."
    for entry in link_header.split(","):
        entry = entry.strip()
        if not entry.startswith("<"):
            continue
        try:
            url_part, *params = entry.split(";")
            url = url_part.strip()[1:-1]  # togli < >
            for p in params:
                p = p.strip()
                if "=" in p:
                    k, v = p.split("=", 1)
                    v = v.strip().strip('"')
                    if k.strip().lower() == "rel" and v == WP_LINK_REL:
                        # Ritorna il root + /wp/v2 come convenzione standard
                        if url.endswith("/"):
                            return url.rstrip("/") + "/wp/v2"
                        return url + "/wp/v2"
        except Exception:
            continue
    return None


def _wp_root_from_html(html: HTMLParser, base_url: str) -> str | None:
    """Cerca `<link rel="https://api.w.org/" href="...">` nell'HTML."""
    for link in html.css("link[rel]"):
        rel = link.attributes.get("rel", "")
        if rel == WP_LINK_REL:
            href = link.attributes.get("href")
            if href:
                full = urljoin(base_url, href)
                if full.endswith("/"):
                    return full.rstrip("/") + "/wp/v2"
                return full + "/wp/v2"
    return None


async def _verify_wp_api(client: httpx.AsyncClient, wp_api_root: str) -> bool:
    """Probe `/posts?per_page=1` per confermare che l'API è pubblica e funzionante."""
    test_url = wp_api_root.rstrip("/") + "/posts?per_page=1"
    resp = await _fetch(client, test_url)
    if resp is None or resp.status_code != 200:
        return False
    try:
        data = resp.json()
    except Exception:
        return False
    return isinstance(data, list)


async def _wp_site_name(
    client: httpx.AsyncClient, wp_api_root: str
) -> str | None:
    """Fetch `/wp-json/` root → ritorna `name` (titolo del sito WordPress)."""
    # wp_api_root è tipo `https://site/wp-json/wp/v2` → root è `https://site/wp-json`
    root = wp_api_root
    for suffix in ("/wp/v2", "/wp/v2/"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    resp = await _fetch(client, root)
    if resp is None or resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


# ---------------------------------------------------------------------------
# Step 3 — feed RSS in HTML
# ---------------------------------------------------------------------------


def _feeds_from_html(html: HTMLParser, base_url: str) -> list[str]:
    """Estrai URL di feed da `<link rel="alternate" type="...">`."""
    out: list[str] = []
    for link in html.css('link[rel="alternate"]'):
        type_ = (link.attributes.get("type") or "").lower()
        if type_ in FEED_CONTENT_TYPES:
            href = link.attributes.get("href")
            if href:
                out.append(urljoin(base_url, href))
    # Dedup mantenendo l'ordine
    seen: set[str] = set()
    deduped: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


async def _fallback_common_paths(
    client: httpx.AsyncClient, base_url: str
) -> list[str]:
    """Prova path RSS comuni. Ritorna quelli che rispondono con un feed valido."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    found: list[str] = []
    for path in COMMON_FEED_PATHS:
        candidate = origin + path
        resp = await _fetch(client, candidate)
        if resp is None or resp.status_code != 200:
            continue
        if _is_feed_content_type(resp.headers.get("content-type")):
            found.append(candidate)
            continue
        # Anche se Content-Type è generic, prova a parsare
        title, sample = _try_parse_feed(resp.content)
        if title or sample:
            found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# Step OG — preview metadata
# ---------------------------------------------------------------------------


def _extract_og(html: HTMLParser, base_url: str) -> OgPreview:
    og = OgPreview()

    def _meta(prop: str) -> str | None:
        node = html.css_first(f'meta[property="{prop}"]')
        if node is not None:
            v = node.attributes.get("content")
            if v:
                return v.strip()
        node = html.css_first(f'meta[name="{prop}"]')
        if node is not None:
            v = node.attributes.get("content")
            if v:
                return v.strip()
        return None

    og.title = _meta("og:title") or _title_tag(html)
    if _looks_like_bot_challenge(og.title):
        og.title = None
    og.description = _meta("og:description") or _meta("description")
    og.site_name = _meta("og:site_name")
    og_image = _meta("og:image") or _meta("twitter:image")
    if og_image:
        og.image = urljoin(base_url, og_image)

    favicon = html.css_first('link[rel="icon"]') or html.css_first(
        'link[rel~="shortcut"]'
    )
    if favicon is not None:
        href = favicon.attributes.get("href")
        if href:
            og.favicon = urljoin(base_url, href)
    else:
        # Fallback al classico /favicon.ico
        parsed = urlparse(base_url)
        og.favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    return og


def _title_tag(html: HTMLParser) -> str | None:
    node = html.css_first("title")
    if node is not None and node.text():
        return node.text().strip()
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def discover(url: str) -> DiscoveryResult:
    """Qualifica una URL utente. Vedi docstring del modulo."""
    normalized = _normalize_url(url)
    if not normalized:
        return DiscoveryResult(kind="invalid", reason="URL vuota.")

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.5"}

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        return await _discover_inner(client, normalized)


async def _discover_inner(
    client: httpx.AsyncClient, url: str
) -> DiscoveryResult:
    log.info("yf.discovery.start", url=url)

    resp = await _fetch(client, url)
    if resp is None:
        return DiscoveryResult(
            kind="invalid",
            url_site=url,
            reason="Impossibile raggiungere l'URL.",
        )

    final_url = str(resp.url)  # dopo redirect

    # ---- Step 1: la URL stessa è un feed?
    if _is_feed_content_type(resp.headers.get("content-type")):
        title, sample = _try_parse_feed(resp.content)
        if title or sample:
            return DiscoveryResult(
                kind="rss",
                url_site=None,
                url_feed=final_url,
                candidates=[
                    FeedCandidate(
                        url_feed=final_url, title=title, sample_articles=sample
                    )
                ],
                og=OgPreview(title=title),
            )

    # Da qui assumiamo HTML → parsing
    if "html" not in (resp.headers.get("content-type") or "").lower():
        # Content-type sconosciuto: prova comunque a parsare come feed
        title, sample = _try_parse_feed(resp.content)
        if title or sample:
            return DiscoveryResult(
                kind="rss",
                url_feed=final_url,
                candidates=[
                    FeedCandidate(
                        url_feed=final_url, title=title, sample_articles=sample
                    )
                ],
                og=OgPreview(title=title),
            )
        return DiscoveryResult(
            kind="invalid",
            url_site=final_url,
            reason=f"Content-Type non riconosciuto: {resp.headers.get('content-type')}",
        )

    html = HTMLParser(resp.text)
    og = _extract_og(html, final_url)

    # ---- Step 2: WordPress API?
    wp_root = _wp_root_from_link_header(resp.headers.get("link"))
    if not wp_root:
        wp_root = _wp_root_from_html(html, final_url)
    if not wp_root:
        # Probe diretto come ultimo tentativo
        parsed = urlparse(final_url)
        candidate_root = f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2"
        if await _verify_wp_api(client, candidate_root):
            wp_root = candidate_root

    if wp_root and await _verify_wp_api(client, wp_root):
        log.info("yf.discovery.wp_api", root=wp_root)
        # Se l'HTML era un challenge anti-bot, il titolo dal `wp-json/` root
        # (campo `name`) è quasi sempre il nome reale del sito WordPress.
        if not og.title:
            og.title = await _wp_site_name(client, wp_root)
        return DiscoveryResult(
            kind="wordpress_api",
            url_site=final_url,
            wp_api_root=wp_root,
            og=og,
        )

    # ---- Step 3: feed RSS dichiarati nell'HTML
    feed_urls = _feeds_from_html(html, final_url)
    candidates: list[FeedCandidate] = []

    for feed_url in feed_urls:
        feed_resp = await _fetch(client, feed_url)
        if feed_resp is None or feed_resp.status_code != 200:
            continue
        title, sample = _try_parse_feed(feed_resp.content)
        if title or sample:
            candidates.append(
                FeedCandidate(
                    url_feed=feed_url, title=title, sample_articles=sample
                )
            )

    # ---- Step 3 fallback: path comuni
    if not candidates:
        common = await _fallback_common_paths(client, final_url)
        for feed_url in common:
            feed_resp = await _fetch(client, feed_url)
            if feed_resp is None:
                continue
            title, sample = _try_parse_feed(feed_resp.content)
            if title or sample:
                candidates.append(
                    FeedCandidate(
                        url_feed=feed_url, title=title, sample_articles=sample
                    )
                )

    if candidates:
        # Se l'HTML era un challenge anti-bot e og.title è caduto, ripiega sul
        # titolo del primo feed valido (il `<channel><title>` dell'XML).
        if not og.title:
            for c in candidates:
                if c.title:
                    og.title = c.title
                    break
        return DiscoveryResult(
            kind="rss",
            url_site=final_url,
            url_feed=candidates[0].url_feed,  # default = primo
            candidates=candidates,
            og=og,
        )

    # ---- Step 4: niente da fare
    return DiscoveryResult(
        kind="invalid",
        url_site=final_url,
        og=og,
        reason="Nessun feed RSS o API WordPress trovati.",
    )
