"""Lista country (ISO-2 + nome) derivata dal MMDB MaxMind GeoLite2-Country.

L'MMDB non espone una tabella di lookup country: bisogna iterare tutti i
network range e collezionare i distinct iso_code (~7s). Per evitare di
ripagarlo ad ogni boot:

- cache **su disco** in un JSON accanto al security_db: si rigenera SOLO
  quando l'MMDB è stato aggiornato (mtime confrontato), altrimenti carica
  in <1ms.
- cache **in memoria** via `@lru_cache(maxsize=1)`: subsequent calls nello
  stesso processo non ricaricano nemmeno il JSON.

Usato dal pannello `/yf_admin/security/blocks` per popolare il `<select>`
dei country da bloccare (così non bisogna ricordare a memoria gli ISO-2).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import maxminddb
import structlog

from app.config import get_settings


log = structlog.get_logger()


def _iter_country_records(mmdb_path: Path) -> dict[str, str]:
    """Iterazione completa del MMDB → dict {iso_code: name_en}. Slow path."""
    out: dict[str, str] = {}
    if not mmdb_path.exists():
        log.warning("yf.security.countries_mmdb_missing", path=str(mmdb_path))
        return out
    try:
        reader = maxminddb.open_database(str(mmdb_path))
    except Exception as e:  # noqa: BLE001
        log.warning("yf.security.countries_mmdb_open_failed", error=str(e))
        return out
    try:
        for _net, rec in reader:
            if not isinstance(rec, dict):
                continue
            country = rec.get("country") or rec.get("registered_country") or {}
            if not isinstance(country, dict):
                continue
            iso = country.get("iso_code")
            if not iso or iso in out:
                continue
            names = country.get("names") or {}
            out[iso] = names.get("en") or iso
    finally:
        reader.close()
    return out


def _cache_path() -> Path:
    """JSON di cache: vive accanto a security.db (stessa dir scrivibile)."""
    settings = get_settings()
    return Path(settings.security_db_path).parent / "countries_cache.json"


def _load_cache(mmdb: Path, cache: Path) -> dict[str, str] | None:
    """Ritorna il dict cached SE il JSON esiste ed è più nuovo dell'MMDB,
    altrimenti None (= rebuild)."""
    if not cache.exists() or not mmdb.exists():
        return None
    try:
        if cache.stat().st_mtime < mmdb.stat().st_mtime:
            return None  # MMDB più recente → cache stale
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("yf.security.countries_cache_load_failed", error=str(e))
        return None


def _save_cache(cache: Path, data: dict[str, str]) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log.warning("yf.security.countries_cache_save_failed", error=str(e))


@lru_cache(maxsize=1)
def list_countries() -> list[tuple[str, str]]:
    """Ritorna `[(iso_code, name), ...]` ordinato per nome.

    Caricamento:
      1. cache JSON su disco (se più recente dell'MMDB) → instant
      2. altrimenti full-scan MMDB (~7s) + salva JSON per le prossime volte

    Per forzare rebuild manuale: cancellare il file `countries_cache.json`
    o aggiornare mtime dell'MMDB (es. `touch`).
    """
    settings = get_settings()
    mmdb = Path(settings.maxmind_db_dir) / "GeoLite2-Country.mmdb"
    cache = _cache_path()

    cached = _load_cache(mmdb, cache)
    if cached is not None:
        log.info("yf.security.countries_loaded_from_cache", count=len(cached))
        return sorted(cached.items(), key=lambda kv: kv[1])

    data = _iter_country_records(mmdb)
    if data:
        _save_cache(cache, data)
        log.info("yf.security.countries_rebuilt", count=len(data))
    return sorted(data.items(), key=lambda kv: kv[1])
