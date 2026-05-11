"""Parser RSS/Atom: feed URL -> lista di ArticleCandidate.

Funzione pura: nessun accesso a DB. Si limita a:
- HTTP GET con etag/last_modified per `304 Not Modified`
- parsing con feedparser
- normalizzazione campi (title, link, published_at, author, content_html, image)

Niente dedup qui: la dedup avviene a livello DB via `articles.url_hash`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import structlog
from selectolax.parser import HTMLParser

log = structlog.get_logger()

USER_AGENT = "YouFeed/1.0 (+https://www.youfeed.it/bot)"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)


@dataclass
class ArticleCandidate:
    """Articolo grezzo estratto dal feed, pronto per l'upsert in `articles`."""

    external_id: str | None
    url_canonical: str
    url_hash: str
    title: str
    description: str | None
    content_html: str | None
    author: str | None
    published_at: datetime
    updated_at: datetime | None
    image_url: str | None
    origin_taxonomy: list[str] | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    """Output di una fetch RSS."""

    not_modified: bool = False
    articles: list[ArticleCandidate] = field(default_factory=list)
    new_etag: str | None = None
    new_last_modified: str | None = None
    feed_title: str | None = None
    error: str | None = None


def make_url_hash(url: str) -> str:
    """SHA-256 lowercase canonico — usato come unique constraint in PG."""
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    """Accetta struct_time di feedparser, stringa RFC822 o ISO. Tutto in UTC."""
    if not value:
        return None
    if hasattr(value, "tm_year"):
        # feedparser struct_time -> assumiamo UTC (feedparser normalizza a GMT)
        return datetime(*value[:6], tzinfo=UTC)
    if isinstance(value, str):
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


def _extract_image(entry: Any, base_url: str) -> str | None:
    """Cerca un'immagine nel feed entry, in ordine di preferenza."""
    # 1. media:thumbnail / media:content
    for key in ("media_thumbnail", "media_content"):
        items = entry.get(key) or []
        if items:
            first = items[0] if isinstance(items, list) else items
            url = first.get("url") if isinstance(first, dict) else None
            if url:
                return urljoin(base_url, url)

    # 2. enclosure (image/*)
    for enc in entry.get("enclosures") or []:
        if isinstance(enc, dict):
            t = (enc.get("type") or "").lower()
            href = enc.get("href") or enc.get("url")
            if href and t.startswith("image/"):
                return urljoin(base_url, href)

    # 3. <img> nel content/summary
    html_blob = ""
    for c in entry.get("content") or []:
        if isinstance(c, dict) and c.get("value"):
            html_blob = c["value"]
            break
    if not html_blob:
        html_blob = entry.get("summary") or ""
    if html_blob:
        try:
            doc = HTMLParser(html_blob)
            img = doc.css_first("img")
            if img is not None:
                src = img.attributes.get("src")
                if src:
                    return urljoin(base_url, src)
        except Exception:
            pass

    return None


def _extract_content_html(entry: Any) -> str | None:
    """Preferisce `content[0].value` (full); fallback su `summary`."""
    for c in entry.get("content") or []:
        if isinstance(c, dict) and c.get("value"):
            return str(c["value"])
    summary = entry.get("summary")
    if summary:
        return str(summary)
    return None


def _extract_taxonomy(entry: Any) -> list[str] | None:
    """Tag/categorie dal feed (utile come hint per classify)."""
    tags = entry.get("tags") or []
    out: list[str] = []
    for t in tags:
        if isinstance(t, dict):
            term = t.get("term") or t.get("label")
            if term:
                out.append(str(term))
    return out or None


def _entry_to_candidate(entry: Any, base_url: str) -> ArticleCandidate | None:
    link = entry.get("link")
    title = entry.get("title")
    if not link or not title:
        return None
    link = str(link).strip()
    title = str(title).strip()
    if not link or not title:
        return None

    published = _parse_dt(entry.get("published_parsed") or entry.get("published"))
    updated = _parse_dt(entry.get("updated_parsed") or entry.get("updated"))
    if published is None:
        published = updated or datetime.now(UTC)

    external_id = entry.get("id") or entry.get("guid")
    author = entry.get("author")
    description = entry.get("summary")
    content_html = _extract_content_html(entry)
    image_url = _extract_image(entry, base_url)

    return ArticleCandidate(
        external_id=str(external_id) if external_id else None,
        url_canonical=link,
        url_hash=make_url_hash(link),
        title=title[:1000],
        description=str(description)[:2000] if description else None,
        content_html=content_html,
        author=str(author) if author else None,
        published_at=published,
        updated_at=updated,
        image_url=image_url,
        origin_taxonomy=_extract_taxonomy(entry),
        raw_meta={"link_origin": entry.get("link") or ""},
    )


async def fetch_rss(
    url_feed: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Scarica e parsifica un feed RSS/Atom.

    Usa `If-None-Match` / `If-Modified-Since` se forniti — ritorna
    `not_modified=True` su 304.
    """
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    own_client = client is None
    client = client or httpx.AsyncClient(headers=headers, timeout=TIMEOUT)
    try:
        try:
            resp = await client.get(url_feed, headers=headers, follow_redirects=True)
        except httpx.HTTPError as e:
            log.warning("yf.fetch_rss.http_error", url=url_feed, error=str(e))
            return FetchResult(error=f"http_error: {e!s}")

        if resp.status_code == 304:
            return FetchResult(not_modified=True)
        if resp.status_code != 200:
            return FetchResult(error=f"http_{resp.status_code}")

        parsed = feedparser.parse(resp.content)
        # base URL per resolve di link relativi nei contenuti
        base = (parsed.feed or {}).get("link") or url_feed
        base_parsed = urlparse(base)
        if not base_parsed.scheme:
            base = url_feed

        candidates: list[ArticleCandidate] = []
        for entry in parsed.entries or []:
            cand = _entry_to_candidate(entry, base)
            if cand is not None:
                candidates.append(cand)

        return FetchResult(
            articles=candidates,
            new_etag=resp.headers.get("etag"),
            new_last_modified=resp.headers.get("last-modified"),
            feed_title=(parsed.feed or {}).get("title"),
        )
    finally:
        if own_client:
            await client.aclose()
