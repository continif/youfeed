"""Lista country (ISO-2 + nome) derivata dal MMDB MaxMind GeoLite2-Country.

L'MMDB non espone una tabella di lookup country: bisogna iterare tutti i
network range e collezionare i Q-distinct iso_code visti. È un'operazione
da ~7s, quindi la cache-iamo a livello modulo dopo la prima chiamata.

Usato dal pannello `/yf_admin/security/blocks` per popolare il `<select>`
dei country da bloccare (così non bisogna ricordare a memoria gli ISO-2).
"""

from __future__ import annotations

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


@lru_cache(maxsize=1)
def list_countries() -> list[tuple[str, str]]:
    """Ritorna `[(iso_code, name), ...]` ordinato per nome.

    Cached: la prima chiamata fa il full-scan dell'MMDB (~7s), le successive
    sono instant. Il refresh del DB (script `maxmind-refresh.sh`) implica
    un restart dell'app, che invalida la cache implicitamente.
    """
    settings = get_settings()
    mmdb = Path(settings.maxmind_db_dir) / "GeoLite2-Country.mmdb"
    data = _iter_country_records(mmdb)
    return sorted(data.items(), key=lambda kv: kv[1])
