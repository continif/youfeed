"""Image processing: scarica image_url, ricodifica in WebP, salva su disco.

Storage layout (vedi `Claude/DATABASE.md`):
  IMAGES_DIR/{hash[:2]}/{hash[2:4]}/{hash}_m.webp   # 370px (mobile)
  IMAGES_DIR/{hash[:2]}/{hash[2:4]}/{hash}_d.webp   # 1200px max (desktop)

`hash` = sha256(url) — stesso hash che usiamo per la dedup articoli (ma
calcolato sull'URL immagine, indipendente).

Path pubblico (servito da Apache): IMAGES_PUBLIC_PREFIX/{hash[:2]}/.../_m.webp
La colonna `articles.image_local_path` salva il path RELATIVO a IMAGES_DIR
(senza prefisso), così cambiare la public-mount-point non richiede update DB.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

log = structlog.get_logger()

USER_AGENT = "YouFeed/1.0 (+https://www.youfeed.it/bot)"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
MAX_BYTES = 12 * 1024 * 1024  # 12 MB hard cap (rifiutiamo immagini enormi)
MIN_WIDTH = 200  # immagini più piccole non sono utili per le card
MIN_HEIGHT = 100


@dataclass
class ProcessedImage:
    relative_path: str  # path relativo a IMAGES_DIR (es. "ab/cd/abcd...._d.webp")
    width: int
    height: int


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _shard_dir(images_dir: Path, h: str) -> Path:
    return images_dir / h[:2] / h[2:4]


def _resize_max(im: Image.Image, max_width: int) -> Image.Image:
    """Ridimensiona mantenendo proporzioni se larghezza > max_width."""
    if im.width <= max_width:
        return im
    ratio = max_width / im.width
    new_h = int(im.height * ratio)
    return im.resize((max_width, new_h), Image.Resampling.LANCZOS)


async def _download(url: str, client: httpx.AsyncClient) -> bytes | None:
    try:
        async with client.stream("GET", url, follow_redirects=True) as resp:
            if resp.status_code != 200:
                log.debug("yf.image.http_status", url=url, status=resp.status_code)
                return None
            ctype = (resp.headers.get("content-type") or "").lower()
            if not ctype.startswith("image/"):
                log.debug("yf.image.not_image", url=url, ctype=ctype)
                return None
            buf = io.BytesIO()
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    log.debug("yf.image.too_large", url=url, bytes=total)
                    return None
                buf.write(chunk)
            return buf.getvalue()
    except httpx.HTTPError as e:
        log.debug("yf.image.fetch_failed", url=url, error=str(e))
        return None


async def process_image(image_url: str) -> ProcessedImage | None:
    """Scarica + decode + resize -> WebP. Ritorna il path relativo della
    variante DESKTOP (la mobile è derivata col suffisso `_m`).

    Idempotente: se i file esistono già, ritorna i metadata senza riscaricare.
    """
    settings = get_settings()
    images_dir = Path(settings.images_dir).resolve()
    images_dir.mkdir(parents=True, exist_ok=True)

    h = _hash_url(image_url)
    shard = _shard_dir(images_dir, h)
    shard.mkdir(parents=True, exist_ok=True)
    desktop_path = shard / f"{h}_d.webp"
    mobile_path = shard / f"{h}_m.webp"

    if desktop_path.exists():
        try:
            with Image.open(desktop_path) as im:
                w, h_px = im.size
            return ProcessedImage(
                relative_path=str(desktop_path.relative_to(images_dir)),
                width=w,
                height=h_px,
            )
        except (UnidentifiedImageError, OSError):
            desktop_path.unlink(missing_ok=True)
            mobile_path.unlink(missing_ok=True)

    headers = {"User-Agent": USER_AGENT, "Accept": "image/*"}
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT) as client:
        data = await _download(image_url, client)
    if not data:
        return None

    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            # Convert a RGB (alcune immagini in P/RGBA tendono a fallire WebP encoding strict)
            if im.mode in ("P", "RGBA"):
                im = im.convert("RGBA")
            elif im.mode != "RGB":
                im = im.convert("RGB")

            if im.width < MIN_WIDTH or im.height < MIN_HEIGHT:
                log.debug(
                    "yf.image.too_small",
                    url=image_url,
                    width=im.width,
                    height=im.height,
                )
                return None

            # Variante desktop
            desktop_im = _resize_max(im, settings.image_desktop_max_width)
            desktop_im.save(
                desktop_path,
                "WEBP",
                quality=settings.image_webp_quality,
                method=4,
            )

            # Variante mobile (sempre <= mobile_width)
            mobile_im = _resize_max(im, settings.image_mobile_width)
            mobile_im.save(
                mobile_path,
                "WEBP",
                quality=settings.image_webp_quality,
                method=4,
            )

            return ProcessedImage(
                relative_path=str(desktop_path.relative_to(images_dir)),
                width=desktop_im.width,
                height=desktop_im.height,
            )
    except (UnidentifiedImageError, OSError) as e:
        log.warning("yf.image.decode_failed", url=image_url, error=str(e))
        return None
