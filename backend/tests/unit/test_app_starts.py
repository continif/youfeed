"""Smoke test: verifica che l'app FastAPI si istanzi senza errori e
che `/yf_version` risponda correttamente (no DB richiesto)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # Import ritardato così le env fixture sono già applicate
    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_version_endpoint(client: TestClient) -> None:
    res = client.get("/yf_version")
    assert res.status_code == 200
    body = res.json()
    assert "version" in body
    assert "env" in body
