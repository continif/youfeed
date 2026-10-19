"""Export blocklist IP: auth Bearer + contenuto."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.deps import db_dep


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.main import create_app
    from app.routers import security_export

    monkeypatch.setattr(
        security_export, "get_settings", lambda: SimpleNamespace(security_export_token="s3cret")
    )

    async def fake_ips(_session, **_kw):
        return ["1.2.3.4", "5.6.7.8"]

    monkeypatch.setattr(security_export, "recent_blocked_ips", fake_ips)
    app = create_app()

    async def fake_db():
        yield None

    app.dependency_overrides[db_dep] = fake_db
    return TestClient(app)


URL = "/yf_data/security/blocked-ips.txt"


def test_ok_one_ip_per_line(client: TestClient) -> None:
    res = client.get(URL, headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200
    assert res.text == "1.2.3.4\n5.6.7.8\n"
    assert res.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize(
    "header", [None, "Bearer wrong", "Basic s3cret", "s3cret", "Bearer "]
)
def test_rejects_bad_auth(client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header is not None else {}
    assert client.get(URL, headers=headers).status_code == 401


def test_disabled_without_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import security_export

    monkeypatch.setattr(
        security_export, "get_settings", lambda: SimpleNamespace(security_export_token="")
    )
    assert client.get(URL, headers={"Authorization": "Bearer "}).status_code == 401
