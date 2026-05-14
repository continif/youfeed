"""Parser robots.txt con cache per la pipeline di ingestion.

Comportamento standard (RFC 9309 / robotstxt.org):
- Una sola lettura per dominio, cached in memoria con TTL 24h.
- HTTP 404/410 sul robots.txt = allow-all (assenza di policy → niente
  restrizione).
- Errori di rete o 5xx temporanei → fail-open (best-effort: non bloccare
  l'ingestion solo perché il loro server è instabile). Loggato.
- Match contro `USER_AGENT_TOKEN` (`YouFeed`), che è la stringa che
  i webmaster useranno per regolarci selettivamente.

API: `await can_fetch(url, client=…) -> bool`.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from .user_agent import USER_AGENT, USER_AGENT_TOKEN


log = structlog.get_logger()


_TTL_SECONDS = 24 * 3600
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_cache: dict[str, tuple[RobotFileParser | None, float]] = {}
_lock = asyncio.Lock()


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _allow_all_parser() -> RobotFileParser:
    rp = RobotFileParser()
    rp.parse([])  # corpus vuoto → can_fetch ritorna sempre True
    return rp


async def _fetch_parser(
    client: httpx.AsyncClient, origin: str
) -> RobotFileParser | None:
    """None = errore network/5xx → caller adotta fail-open."""
    url = f"{origin}/robots.txt"
    try:
        resp = await client.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
    except (httpx.HTTPError, OSError) as e:
        log.warning("yf.robots.fetch_failed", url=url, error=str(e))
        return None

    if resp.status_code == 200:
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp
    if resp.status_code in (404, 410):
        # Convenzione standard: nessun robots.txt = consenti tutto.
        return _allow_all_parser()
    # 401/403/5xx → fail-open ma niente caching positivo (riproveremo)
    log.info("yf.robots.unexpected_status", url=url, status=resp.status_code)
    return None


async def can_fetch(
    url: str, *, client: httpx.AsyncClient | None = None
) -> bool:
    """`True` se possiamo fare il fetch di `url`.

    Decisione presa contro `USER_AGENT_TOKEN`. In caso di errori di
    rete/server sull'host del robots.txt → fail-open (`True`).
    """
    origin = _origin(url)
    now = time.monotonic()

    async with _lock:
        cached = _cache.get(origin)
        if cached and now - cached[1] < _TTL_SECONDS:
            rp = cached[0]
        else:
            close_client = False
            if client is None:
                client = httpx.AsyncClient()
                close_client = True
            try:
                rp = await _fetch_parser(client, origin)
            finally:
                if close_client:
                    await client.aclose()
            # Cache solo i risultati positivi/definitivi (None significa errore
            # transitorio: vogliamo riprovare alla prossima richiesta).
            if rp is not None:
                _cache[origin] = (rp, now)

    if rp is None:
        return True  # fail-open
    try:
        return rp.can_fetch(USER_AGENT_TOKEN, url)
    except Exception:  # noqa: BLE001
        return True


def reset_cache() -> None:
    """Utile dai test e dopo deploy se vogliamo forzare il refresh."""
    _cache.clear()
