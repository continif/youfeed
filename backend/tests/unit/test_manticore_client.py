"""Unit test per app.ingestion.manticore_client (HTTP mockato).

Iniettiamo un `httpx.AsyncClient` finto via il parametro `client=...` esposto
dalle funzioni public. Niente connessione reale a Manticore.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.ingestion import manticore_client as mc


def _mock_client(*, status: int = 200, json_body: Any = None, capture: dict | None = None):
    """Costruisce un AsyncMock(httpx.AsyncClient) che cattura le call."""
    client = AsyncMock(spec=httpx.AsyncClient)

    async def _post(url: str, *, json: Any = None, **_kw):
        if capture is not None:
            capture["url"] = url
            capture["json"] = json
        resp = httpx.Response(status, json=json_body if json_body is not None else {})
        return resp

    client.post = AsyncMock(side_effect=_post)
    return client


# ---------------------------------------------------------------------------
# replace_article
# ---------------------------------------------------------------------------


async def test_replace_article_sends_correct_payload() -> None:
    capture: dict = {}
    client = _mock_client(capture=capture)

    ok = await mc.replace_article(
        article_id=42,
        title="Titolo X",
        description="Desc",
        content_text="testo",
        content_html="<p>html</p>",
        source_id=10,
        source_domain="example.com",
        topic_ids=[1, 2, 3],
        topic_slugs=["a", "b", "c"],
        published_at=datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC),
        kind="rss",
        client=client,
    )

    assert ok is True
    assert capture["url"].endswith("/replace")
    payload = capture["json"]
    assert payload["index"] == "articles_rt"
    assert payload["id"] == 42
    doc = payload["doc"]
    assert doc["title"] == "Titolo X"
    assert doc["description"] == "Desc"
    assert doc["content_text"] == "testo"
    assert doc["content_html"] == "<p>html</p>"
    assert doc["source_id"] == 10
    assert doc["source_domain"] == "example.com"
    assert doc["topic_ids"] == [1, 2, 3]
    assert doc["topic_slugs_csv"] == "a,b,c"
    # timestamp epoch UTC
    assert doc["published_at"] == int(datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC).timestamp())
    assert doc["kind"] == "rss"


async def test_replace_article_returns_false_on_4xx() -> None:
    client = _mock_client(status=400, json_body={"error": "bad"})

    ok = await mc.replace_article(
        article_id=1,
        title="T",
        description=None,
        content_text="",
        content_html=None,
        source_id=1,
        source_domain=None,
        topic_ids=[],
        topic_slugs=[],
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind="rss",
        client=client,
    )
    assert ok is False


async def test_replace_article_handles_none_optional_fields() -> None:
    """description, content_html, source_domain a None: il payload usa "" come sentinel."""
    capture: dict = {}
    client = _mock_client(capture=capture)

    await mc.replace_article(
        article_id=1,
        title="T",
        description=None,
        content_text="x",
        content_html=None,
        source_id=1,
        source_domain=None,
        topic_ids=[],
        topic_slugs=[],
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind="rss",
        client=client,
    )
    doc = capture["json"]["doc"]
    assert doc["description"] == ""
    assert doc["content_html"] == ""
    assert doc["source_domain"] == ""
    assert doc["topic_ids"] == []
    assert doc["topic_slugs_csv"] == ""


async def test_replace_article_returns_false_on_http_error() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(side_effect=httpx.ConnectError("conn refused"))

    ok = await mc.replace_article(
        article_id=1,
        title="T",
        description=None,
        content_text="x",
        content_html=None,
        source_id=1,
        source_domain=None,
        topic_ids=[],
        topic_slugs=[],
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind="rss",
        client=client,
    )
    assert ok is False


# ---------------------------------------------------------------------------
# get_by_ids
# ---------------------------------------------------------------------------


async def test_get_by_ids_parses_search_response() -> None:
    response_body = {
        "hits": {
            "hits": [
                {
                    "_id": 1,
                    "_source": {"title": "A", "content_text": "body A"},
                },
                {
                    "_id": 2,
                    "_source": {"title": "B", "content_text": "body B"},
                },
            ]
        }
    }
    capture: dict = {}
    client = _mock_client(json_body=response_body, capture=capture)

    out = await mc.get_by_ids([1, 2], client=client)

    assert capture["url"].endswith("/search")
    payload = capture["json"]
    assert payload["index"] == "articles_rt"
    assert payload["query"] == {"in": {"_id": [1, 2]}}
    assert set(out.keys()) == {1, 2}
    assert out[1]["title"] == "A"
    assert out[2]["title"] == "B"


async def test_get_by_ids_empty_list_short_circuits() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    out = await mc.get_by_ids([], client=client)
    assert out == {}
    client.post.assert_not_called()


async def test_get_by_ids_returns_empty_on_failure() -> None:
    client = _mock_client(status=500, json_body={"error": "boom"})
    out = await mc.get_by_ids([1], client=client)
    assert out == {}


async def test_get_by_ids_skips_hits_without_id() -> None:
    response_body = {
        "hits": {"hits": [{"_source": {"title": "no id"}}, {"_id": 5, "_source": {"title": "ok"}}]}
    }
    client = _mock_client(json_body=response_body)
    out = await mc.get_by_ids([5], client=client)
    assert list(out.keys()) == [5]


# ---------------------------------------------------------------------------
# delete_article
# ---------------------------------------------------------------------------


async def test_delete_article_sends_id_payload() -> None:
    capture: dict = {}
    client = _mock_client(capture=capture)
    ok = await mc.delete_article(99, client=client)
    assert ok is True
    assert capture["url"].endswith("/delete")
    assert capture["json"] == {"index": "articles_rt", "id": 99}
