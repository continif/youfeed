"""WordPress REST API: wp_api_root -> lista di ArticleCandidate.

Endpoint usato: `{wp_api_root}/posts?per_page=20&_embed=true&orderby=date&order=desc`.
`_embed=true` ci porta media (immagine featured) e termini (categorie/tag) nello
stesso payload, evitando N+1 chiamate.

Filtraggio incrementale: usiamo `?after=ISO8601` con il `last_success_at` della
source per non riscaricare tutto. Niente etag standard sull'API WP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from .feed_parser import (
    USER_AGENT,
    TIMEOUT,
    ArticleCandidate,
    FetchResult,
    make_url_hash,
)

log = structlog.get_logger()

PER_PAGE = 20


def _strip_html(s: str | None) -> str | None:
    if not s:
        return None
    # WP `excerpt.rendered` arriva come HTML breve; manteniamo HTML, sarà
    # trafilatura o il sanitize a pulire più avanti. Qui solo strip semplice
    # dei tag wrapper per `description`.
    from selectolax.parser import HTMLParser

    try:
        text = HTMLParser(s).text(separator=" ").strip()
    except Exception:
        return s.strip()
    return text or None


def _featured_image(post: dict[str, Any]) -> str | None:
    embedded = post.get("_embedded") or {}
    media = embedded.get("wp:featuredmedia") or []
    if not media:
        return None
    first = media[0]
    if not isinstance(first, dict):
        return None
    # preferenza ai media_details.sizes.large/full > source_url
    details = first.get("media_details") or {}
    sizes = details.get("sizes") or {}
    for key in ("large", "full", "medium_large", "medium"):
        if key in sizes and isinstance(sizes[key], dict):
            url = sizes[key].get("source_url")
            if url:
                return str(url)
    src = first.get("source_url")
    return str(src) if src else None


def _author(post: dict[str, Any]) -> str | None:
    embedded = post.get("_embedded") or {}
    authors = embedded.get("author") or []
    if authors and isinstance(authors[0], dict):
        name = authors[0].get("name")
        if name:
            return str(name)
    return None


def _taxonomy(post: dict[str, Any]) -> list[str] | None:
    """Estrae nomi di categorie+tag da `wp:term` (richiede `?_embed=true`)."""
    embedded = post.get("_embedded") or {}
    terms = embedded.get("wp:term") or []
    out: list[str] = []
    for group in terms:
        if not isinstance(group, list):
            continue
        for t in group:
            if isinstance(t, dict):
                name = t.get("name")
                if name:
                    out.append(str(name))
    return out or None


def _post_to_candidate(post: dict[str, Any]) -> ArticleCandidate | None:
    link = post.get("link")
    title_block = post.get("title") or {}
    title = title_block.get("rendered") if isinstance(title_block, dict) else None
    if not link or not title:
        return None

    title = _strip_html(str(title)) or str(title)
    description = _strip_html((post.get("excerpt") or {}).get("rendered"))

    content_block = post.get("content") or {}
    content_html = (
        content_block.get("rendered") if isinstance(content_block, dict) else None
    )

    date_str = post.get("date_gmt") or post.get("date")
    try:
        published = (
            datetime.fromisoformat(str(date_str)).replace(tzinfo=UTC)
            if date_str
            else datetime.now(UTC)
        )
    except ValueError:
        published = datetime.now(UTC)

    modified_str = post.get("modified_gmt") or post.get("modified")
    updated: datetime | None = None
    if modified_str:
        try:
            updated = datetime.fromisoformat(str(modified_str)).replace(tzinfo=UTC)
        except ValueError:
            updated = None

    return ArticleCandidate(
        external_id=str(post.get("id")) if post.get("id") is not None else None,
        url_canonical=str(link),
        url_hash=make_url_hash(str(link)),
        title=title[:1000],
        description=description[:2000] if description else None,
        content_html=str(content_html) if content_html else None,
        author=_author(post),
        published_at=published,
        updated_at=updated,
        image_url=_featured_image(post),
        origin_taxonomy=_taxonomy(post),
        raw_meta={"wp_status": post.get("status"), "wp_type": post.get("type")},
    )


async def fetch_wp(
    wp_api_root: str,
    *,
    after: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Scarica gli ultimi post via WP REST API.

    `after`: se fornito, filtra a server-side via `?after=ISO8601` per
    incrementalità. Tipicamente passiamo `source.last_success_at`.
    """
    params: dict[str, str] = {
        "per_page": str(PER_PAGE),
        "_embed": "true",
        "orderby": "date",
        "order": "desc",
        "status": "publish",
    }
    if after is not None:
        params["after"] = after.astimezone(UTC).isoformat().replace("+00:00", "")

    url = f"{wp_api_root.rstrip('/')}/posts?{urlencode(params)}"
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.5"}

    own_client = client is None
    client = client or httpx.AsyncClient(headers=headers, timeout=TIMEOUT)
    try:
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as e:
            log.warning("yf.fetch_wp.http_error", url=url, error=str(e))
            return FetchResult(error=f"http_error: {e!s}")

        if resp.status_code != 200:
            return FetchResult(error=f"http_{resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            return FetchResult(error="invalid_json")

        if not isinstance(data, list):
            return FetchResult(error="unexpected_payload")

        candidates: list[ArticleCandidate] = []
        for post in data:
            if not isinstance(post, dict):
                continue
            cand = _post_to_candidate(post)
            if cand is not None:
                candidates.append(cand)

        return FetchResult(articles=candidates)
    finally:
        if own_client:
            await client.aclose()
