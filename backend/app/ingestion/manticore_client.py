"""Client async per Manticore via HTTP JSON API (porta 9308).

Usiamo HTTP per evitare di aggiungere un driver MySQL solo per parlare con
Manticore. Le operazioni che ci servono (replace di un singolo doc, delete,
search semplice) sono tutte coperte dall'API JSON.

Endpoints:
- POST /replace        (upsert per id)
- POST /delete         (cancella per id o per query)
- POST /search         (search con full-text)

Riferimento: https://manual.manticoresearch.com/Updating_documents/REPLACE
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger()

INDEX_NAME = "articles_rt"


def _base_url() -> str:
    s = get_settings()
    return f"http://{s.manticore_host}:{s.manticore_http_port}"


async def replace_article(
    *,
    article_id: int,
    title: str,
    description: str | None,
    content_text: str,
    content_html: str | None,
    source_id: int,
    source_domain: str | None,
    topic_ids: list[int],
    topic_slugs: list[str],
    published_at: datetime,
    kind: str,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Upsert (replace) di un articolo nell'indice articles_rt.

    Manticore non ha 'NULL' nelle attributes: per stringhe usiamo "" come
    sentinel, per multi `[]`. Il `published_at` va in epoch seconds (UTC).
    """
    doc: dict[str, Any] = {
        "title": title or "",
        "description": description or "",
        "content_text": content_text or "",
        "content_html": content_html or "",
        "source_id": int(source_id),
        "source_domain": source_domain or "",
        "topic_ids": [int(t) for t in topic_ids],
        "topic_slugs_csv": ",".join(topic_slugs),
        "published_at": int(published_at.timestamp()),
        "kind": kind or "",
    }
    payload = {"index": INDEX_NAME, "id": int(article_id), "doc": doc}

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        try:
            resp = await client.post(f"{_base_url()}/replace", json=payload)
        except httpx.HTTPError as e:
            log.warning(
                "yf.manticore.replace_failed",
                article_id=article_id,
                error=str(e),
            )
            return False

        if resp.status_code >= 400:
            log.warning(
                "yf.manticore.replace_status",
                article_id=article_id,
                status=resp.status_code,
                body=resp.text[:500],
            )
            return False
        return True
    finally:
        if own_client:
            await client.aclose()


async def get_by_ids(
    ids: list[int],
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[int, dict[str, Any]]:
    """Ritorna {article_id: doc_attributes} dall'indice articles_rt.

    Usa /search con `query.equals` su `_id` (la pseudo-colonna del docid in
    Manticore JSON API). Limit safety = len(ids) per evitare paginazione.
    """
    if not ids:
        return {}
    payload = {
        "index": INDEX_NAME,
        "limit": min(len(ids), 200),
        # NB: Manticore vuole `id` come nome della colonna doc_id per il
        # filtro `in`; la response continua a usare `_id`. (Bug 2026-05:
        # in passato qui c'era `_id` e get_by_ids ritornava sempre vuoto.)
        "query": {"in": {"id": [int(i) for i in ids]}},
        "_source": [
            "title",
            "description",
            "content_text",
            "content_html",
            "source_id",
            "topic_ids",
            "topic_slugs_csv",
            "published_at",
            "kind",
        ],
    }
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        try:
            resp = await client.post(f"{_base_url()}/search", json=payload)
        except httpx.HTTPError as e:
            log.warning("yf.manticore.search_failed", error=str(e))
            return {}
        if resp.status_code >= 400:
            log.warning(
                "yf.manticore.search_status",
                status=resp.status_code,
                body=resp.text[:500],
            )
            return {}
        data = resp.json()
    finally:
        if own_client:
            await client.aclose()

    hits = (data.get("hits") or {}).get("hits") or []
    out: dict[int, dict[str, Any]] = {}
    for h in hits:
        try:
            doc_id = int(h.get("_id"))
        except (TypeError, ValueError):
            continue
        out[doc_id] = h.get("_source") or {}
    return out


async def search_articles(
    query: str,
    *,
    source_ids: list[int] | None = None,
    limit: int = 20,
    offset: int = 0,
    highlight: bool = True,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Full-text search su `articles_rt`.

    Filtri:
      - `query`: stringa libera, matchata con `match` su title/description/
        content_text (morphology italiana via libstemmer_it).
      - `source_ids`: se passato (non None), restringe a quel set (per il
        feed utente loggato → solo le sue sources iscritte).

    Ritorna dict pronto:
      {
        "total": int,
        "hits": [
          {"id": int, "source_id": int, "published_at": int (epoch),
           "kind": str, "topic_ids": [int], "title": str, "description": str,
           "highlights": {"title": "...", "description": "...", "content_text": "..."}
          }, ...
        ]
      }

    Highlights da Manticore sono già <mark>...</mark> wrappati.
    """
    if not query.strip():
        return {"total": 0, "hits": []}

    payload: dict[str, Any] = {
        "index": INDEX_NAME,
        "limit": max(1, min(limit, 50)),
        "offset": max(0, min(offset, 1000)),
        "query": {
            "bool": {
                "must": [
                    {"query_string": query.strip()},
                ],
            },
        },
        # Boost recency: ordina principalmente per relevance (default _score),
        # poi prossimità temporale (più recenti prima a parità).
        "sort": [
            {"_score": {"order": "desc"}},
            {"published_at": {"order": "desc"}},
        ],
        "_source": [
            "title", "description", "source_id", "published_at",
            "topic_ids", "topic_slugs_csv", "kind",
        ],
    }
    if source_ids is not None:
        if not source_ids:
            return {"total": 0, "hits": []}
        payload["query"]["bool"]["filter"] = [
            {"in": {"source_id": [int(s) for s in source_ids]}}
        ]
    if highlight:
        payload["highlight"] = {
            "fields": ["title", "description", "content_text"],
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "fragment_size": 180,
            "limit_snippets": 1,
        }

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        try:
            resp = await client.post(f"{_base_url()}/search", json=payload)
        except httpx.HTTPError as e:
            log.warning("yf.manticore.search_failed", query=query[:80], error=str(e))
            return {"total": 0, "hits": []}
        if resp.status_code >= 400:
            log.warning(
                "yf.manticore.search_status",
                status=resp.status_code, body=resp.text[:500],
            )
            return {"total": 0, "hits": []}
        data = resp.json()
    finally:
        if own_client:
            await client.aclose()

    hits_raw = (data.get("hits") or {}).get("hits") or []
    total = (data.get("hits") or {}).get("total", 0)
    out_hits: list[dict[str, Any]] = []
    for h in hits_raw:
        try:
            doc_id = int(h.get("_id"))
        except (TypeError, ValueError):
            continue
        src = h.get("_source") or {}
        hl = h.get("highlight") or {}
        out_hits.append({
            "id": doc_id,
            "source_id": int(src.get("source_id") or 0),
            "published_at": int(src.get("published_at") or 0),
            "kind": src.get("kind") or "",
            "topic_ids": list(src.get("topic_ids") or []),
            "title": src.get("title") or "",
            "description": src.get("description") or "",
            "highlights": {
                "title": (hl.get("title") or [""])[0] if hl.get("title") else "",
                "description": (hl.get("description") or [""])[0] if hl.get("description") else "",
                "content_text": (hl.get("content_text") or [""])[0] if hl.get("content_text") else "",
            },
        })
    return {"total": int(total), "hits": out_hits}


async def delete_article(
    article_id: int, *, client: httpx.AsyncClient | None = None
) -> bool:
    payload = {"index": INDEX_NAME, "id": int(article_id)}
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await client.post(f"{_base_url()}/delete", json=payload)
        return resp.status_code < 400
    except httpx.HTTPError as e:
        log.warning("yf.manticore.delete_failed", article_id=article_id, error=str(e))
        return False
    finally:
        if own_client:
            await client.aclose()
