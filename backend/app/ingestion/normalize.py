"""Normalizzazione contenuto articolo.

Input: `ArticleCandidate` con `content_html` grezzo (dal feed o da WP API).
Output: `NormalizedContent` con:
  - content_text: testo plain pulito (per indicizzazione full-text Manticore)
  - content_html_safe: HTML sanitizzato con bleach (per render)
  - image_url: completata con OG/twitter:image se mancava nel feed
  - internal_links: lista di link interni alla source (per "altri articoli")

Per articoli RSS che hanno solo `description` corta, facciamo un opzionale
fetch della pagina con trafilatura per estrarre il testo completo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import bleach
import httpx
import structlog
import trafilatura
from selectolax.parser import HTMLParser

from .feed_parser import USER_AGENT, TIMEOUT, ArticleCandidate

log = structlog.get_logger()

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s", "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "td", "th",
]
ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
}

MIN_HTML_LEN_FOR_FULL_FETCH = 400  # se il content_html è più corto di questo, prova full fetch


@dataclass
class NormalizedContent:
    content_text: str
    content_html_safe: str | None
    image_url: str | None
    internal_links: list[dict[str, str]] = field(default_factory=list)
    raw_meta: dict[str, Any] = field(default_factory=dict)


def _strip_html_to_text(html: str) -> str:
    """HTML -> testo plain.

    Rimuove `<script>`/`<style>`/`<noscript>` per non finire codice JS/CSS
    nell'indice full-text Manticore. Esegue un doppio parse perché molti
    feed RSS contengono tag *HTML-encoded* (`&lt;strong&gt;...`): il primo
    parse decodifica le entity, il secondo rimuove i tag che riemergono.
    """
    if not html:
        return ""
    try:
        text = _html_to_text_once(html)
        # Se ancora rimangono "<...>" il content era double-encoded:
        # ri-parsa per togliere i tag che il primo passaggio ha decodificato.
        if "<" in text and ">" in text:
            text = _html_to_text_once(text)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _html_to_text_once(html: str) -> str:
    doc = HTMLParser(html)
    for node in doc.css("script, style, noscript"):
        node.decompose()
    return doc.text(separator=" ")


def _sanitize_html(html: str) -> str:
    """Rimuove script/style/eventi e tag non whitelisted."""
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def _extract_internal_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Lista di link interni alla source: [{url, text}]."""
    if not html or not base_url:
        return []
    try:
        host = urlparse(base_url).netloc
    except Exception:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        doc = HTMLParser(html)
    except Exception:
        return []
    for a in doc.css("a[href]"):
        href = a.attributes.get("href") or ""
        href_full = urljoin(base_url, href)
        try:
            link_host = urlparse(href_full).netloc
        except Exception:
            continue
        if not link_host or link_host != host:
            continue
        if href_full in seen:
            continue
        seen.add(href_full)
        text = (a.text() or "").strip()
        if text:
            out.append({"url": href_full, "text": text[:200]})
        if len(out) >= 20:
            break
    return out


def _og_image_from_html(html: str, base_url: str) -> str | None:
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    for prop in ("og:image", "twitter:image"):
        node = doc.css_first(f'meta[property="{prop}"]') or doc.css_first(
            f'meta[name="{prop}"]'
        )
        if node is not None:
            v = node.attributes.get("content")
            if v:
                return urljoin(base_url, v.strip())
    return None


async def _fetch_full_page(url: str, client: httpx.AsyncClient) -> str | None:
    from . import robots as robots_mod
    if not await robots_mod.can_fetch(url, client=client):
        log.info("yf.normalize.robots_blocked", url=url)
        return None
    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as e:
        log.debug("yf.normalize.full_fetch_failed", url=url, error=str(e))
        return None
    if resp.status_code != 200 or "html" not in (resp.headers.get("content-type") or "").lower():
        return None
    return resp.text


async def normalize(
    candidate: ArticleCandidate,
    *,
    fetch_full_if_short: bool = True,
    client: httpx.AsyncClient | None = None,
) -> NormalizedContent:
    """Pulisce + arricchisce il candidate. Non muta l'input."""
    html_raw = candidate.content_html or ""
    image_url = candidate.image_url
    full_html: str | None = None
    full_text_from_traf: str | None = None

    short = len(html_raw) < MIN_HTML_LEN_FOR_FULL_FETCH
    if fetch_full_if_short and short:
        own_client = client is None
        c = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.5"},
            timeout=TIMEOUT,
        )
        try:
            full_html = await _fetch_full_page(candidate.url_canonical, c)
        finally:
            if own_client:
                await c.aclose()

        if full_html:
            try:
                full_text_from_traf = trafilatura.extract(
                    full_html,
                    include_comments=False,
                    include_tables=False,
                    favor_recall=False,
                )
            except Exception as e:
                log.debug("yf.normalize.trafilatura_failed", error=str(e))
                full_text_from_traf = None

            if not image_url:
                image_url = _og_image_from_html(full_html, candidate.url_canonical)

    # content_text: preferisci trafilatura sull'HTML completo, poi su content_html grezzo,
    # poi su description.
    if full_text_from_traf:
        content_text = full_text_from_traf
    elif html_raw:
        content_text = _strip_html_to_text(html_raw)
    else:
        content_text = candidate.description or ""

    # content_html_safe: sanitizza il content_html più "ricco" disponibile.
    safe_html: str | None = None
    if html_raw:
        safe_html = _sanitize_html(html_raw)
    elif full_html:
        # estrai blocco main del full page (best-effort)
        try:
            main_html = trafilatura.extract(
                full_html, output_format="html", include_links=True
            )
            if main_html:
                safe_html = _sanitize_html(main_html)
        except Exception:
            safe_html = None

    internal_links = _extract_internal_links(
        html_raw or full_html or "", candidate.url_canonical
    )

    return NormalizedContent(
        content_text=content_text[:50000],  # safety cap
        content_html_safe=safe_html[:200000] if safe_html else None,
        image_url=image_url,
        internal_links=internal_links,
        raw_meta={"used_full_fetch": full_html is not None},
    )
