"""Unit test per app.workers.activity_log._to_row (event JSON -> row dict)."""

from __future__ import annotations

import uuid

from app.workers import activity_log


def test_to_row_full_event() -> None:
    sid = "11111111-2222-3333-4444-555555555555"
    event = {
        "user_id": 42,
        "session_id": sid,
        "fingerprint": "fp-abc",
        "event_type": "click",
        "route": "/me/feed",
        "method": "GET",
        "target_type": "article",
        "target_id": "1234",
        "metadata": {"k": "v"},
        "ip": "127.0.0.1",
        "country": "IT",
        "asn": 12874,
        "ua": "Mozilla/5.0",
        "status": 200,
        "latency_ms": 14,
        "ts": "2026-05-06T12:00:00+00:00",
    }
    row = activity_log._to_row(event)
    assert row["user_id"] == 42
    assert row["session_id"] == uuid.UUID(sid)
    assert row["fingerprint"] == "fp-abc"
    assert row["event_type"] == "click"
    assert row["target_type"] == "article"
    assert row["target_id"] == "1234"
    assert row["metadata"] == {"k": "v"}
    assert row["country"] == "IT"
    assert row["status"] == 200
    assert row["latency_ms"] == 14
    assert row["ts"].year == 2026


def test_to_row_handles_invalid_session_id() -> None:
    event = {"event_type": "click", "session_id": "not-a-uuid"}
    row = activity_log._to_row(event)
    assert row["session_id"] is None


def test_to_row_handles_z_suffix_iso() -> None:
    event = {"event_type": "click", "ts": "2026-05-06T12:00:00Z"}
    row = activity_log._to_row(event)
    assert row["ts"].year == 2026
    assert row["ts"].tzinfo is not None


def test_to_row_falls_back_to_now_for_missing_ts() -> None:
    event = {"event_type": "click"}
    row = activity_log._to_row(event)
    assert row["ts"].tzinfo is not None  # tz-aware


def test_to_row_falls_back_to_now_for_invalid_ts() -> None:
    event = {"event_type": "click", "ts": "garbage"}
    row = activity_log._to_row(event)
    assert row["ts"].tzinfo is not None


def test_to_row_truncates_event_type_and_method() -> None:
    event = {"event_type": "x" * 100, "method": "EXTRA-LONG-METHOD"}
    row = activity_log._to_row(event)
    assert len(row["event_type"]) <= 32
    assert row["method"] is not None and len(row["method"]) <= 8


def test_to_row_method_empty_becomes_none() -> None:
    event = {"event_type": "click", "method": ""}
    row = activity_log._to_row(event)
    assert row["method"] is None


def test_to_row_default_event_type_is_http_request() -> None:
    row = activity_log._to_row({})
    assert row["event_type"] == "http_request"
