"""Unit test per app.ingestion.image_processor (parti pure, no HTTP)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.ingestion import image_processor as ip


# ---------------------------------------------------------------------------
# _hash_url / _shard_dir
# ---------------------------------------------------------------------------


def test_hash_url_is_deterministic_and_64_chars() -> None:
    h1 = ip._hash_url("https://x.com/a.jpg")
    h2 = ip._hash_url("https://x.com/a.jpg")
    assert h1 == h2
    assert len(h1) == 64


def test_hash_url_differs_for_different_urls() -> None:
    assert ip._hash_url("https://x.com/a.jpg") != ip._hash_url("https://x.com/b.jpg")


def test_hash_url_strips_whitespace() -> None:
    assert ip._hash_url("  https://x.com/a.jpg  ") == ip._hash_url("https://x.com/a.jpg")


def test_shard_dir_layout(tmp_path: Path) -> None:
    h = "abcd1234" + "0" * 56
    out = ip._shard_dir(tmp_path, h)
    # Sharding: {hash[:2]}/{hash[2:4]}
    assert out == tmp_path / "ab" / "cd"


# ---------------------------------------------------------------------------
# _resize_max
# ---------------------------------------------------------------------------


def _make_image(w: int, h: int) -> Image.Image:
    return Image.new("RGB", (w, h), color=(200, 100, 50))


def test_resize_max_downsizes_to_target_width() -> None:
    im = _make_image(2000, 1000)
    out = ip._resize_max(im, 1200)
    assert out.width == 1200
    assert out.height == 600  # ratio preservato


def test_resize_max_does_not_upscale() -> None:
    im = _make_image(800, 400)
    out = ip._resize_max(im, 1200)
    # Larghezza già <= max: ritorna l'originale (stesso oggetto)
    assert out is im
    assert out.width == 800


def test_resize_max_preserves_aspect_ratio_with_odd_sizes() -> None:
    im = _make_image(1500, 900)
    out = ip._resize_max(im, 370)
    assert out.width == 370
    # 900 * 370 / 1500 = 222
    assert out.height == 222


# ---------------------------------------------------------------------------
# process_image: integrazione con file system + httpx mock
#
# Mocchiamo `httpx.AsyncClient` via monkey-patch del modulo. Il test verifica
# che dato un buffer JPEG valido vengano scritte le due varianti `_d.webp`
# (desktop) e `_m.webp` (mobile) nel layout sharded atteso.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code: int, content: bytes, ctype: str = "image/jpeg") -> None:
        self.status_code = status_code
        self.headers = {"content-type": ctype}
        self._chunks = [content]

    async def aiter_bytes(self):  # type: ignore[no-untyped-def]
        for c in self._chunks:
            yield c

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def stream(self, _method: str, _url: str, **_kw: object) -> "_FakeResponse":
        return self._response

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None


def _jpeg_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(220, 220, 220)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


@pytest.fixture
def isolated_images_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Reset cache settings + redirect images_dir su tmp
    from app.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path))
    yield tmp_path
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def test_process_image_writes_two_variants(
    isolated_images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mock httpx.AsyncClient con response JPEG valido 1500x900
    fake = _FakeClient(_FakeResponse(status_code=200, content=_jpeg_bytes(1500, 900)))
    monkeypatch.setattr(ip.httpx, "AsyncClient", lambda **_kw: fake)

    result = await ip.process_image("https://x.com/foo.jpg")

    assert result is not None
    base = isolated_images_dir / Path(result.relative_path).parent
    h = ip._hash_url("https://x.com/foo.jpg")
    assert (base / f"{h}_d.webp").exists()
    assert (base / f"{h}_m.webp").exists()
    # Desktop = min(1500, 1200) = 1200; height = 900 * 1200/1500 = 720
    assert result.width == 1200
    assert result.height == 720


async def test_process_image_rejects_too_small(
    isolated_images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 100x50 -> sotto MIN_WIDTH/MIN_HEIGHT
    fake = _FakeClient(_FakeResponse(status_code=200, content=_jpeg_bytes(100, 50)))
    monkeypatch.setattr(ip.httpx, "AsyncClient", lambda **_kw: fake)

    result = await ip.process_image("https://x.com/tiny.jpg")
    assert result is None


async def test_process_image_rejects_non_image_content_type(
    isolated_images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(
        _FakeResponse(status_code=200, content=b"<html/>", ctype="text/html")
    )
    monkeypatch.setattr(ip.httpx, "AsyncClient", lambda **_kw: fake)

    result = await ip.process_image("https://x.com/page.html")
    assert result is None


async def test_process_image_rejects_4xx(
    isolated_images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(_FakeResponse(status_code=404, content=b""))
    monkeypatch.setattr(ip.httpx, "AsyncClient", lambda **_kw: fake)

    result = await ip.process_image("https://x.com/missing.jpg")
    assert result is None


async def test_process_image_is_idempotent(
    isolated_images_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seconda chiamata non ridownloada: rilegge i file dal disco."""
    fake = _FakeClient(_FakeResponse(status_code=200, content=_jpeg_bytes(800, 600)))
    monkeypatch.setattr(ip.httpx, "AsyncClient", lambda **_kw: fake)

    r1 = await ip.process_image("https://x.com/cache.jpg")
    assert r1 is not None

    # Per la seconda call, nessuna risposta HTTP: spediamo None se viene chiamato
    monkeypatch.setattr(
        ip.httpx,
        "AsyncClient",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("non-doveva-fare-fetch")),
    )

    r2 = await ip.process_image("https://x.com/cache.jpg")
    assert r2 is not None
    assert r2.relative_path == r1.relative_path
    assert r2.width == r1.width and r2.height == r1.height
