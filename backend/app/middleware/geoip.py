"""GeoIP middleware: legge l'IP reale (CF-Connecting-IP) e arricchisce con MaxMind.

Popola `request.state.client_ip`, `request.state.country`, `request.state.asn`.
Tutti i middleware/handler successivi possono fare affidamento su questi
campi (potranno essere None se la lookup fallisce o l'IP non è classificabile).
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import TYPE_CHECKING

import maxminddb
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


log = structlog.get_logger()


class GeoIPMiddleware(BaseHTTPMiddleware):
    """Risolve client IP + ASN/Country da MaxMind MMDB.

    Apre i file MMDB una volta al boot e li mantiene in memoria; il refresh
    su disco è gestito esternamente (cron `maxmind-refresh.sh` + reload
    del processo, oppure SIGHUP futuro).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        db_dir = Path(settings.maxmind_db_dir)
        country_path = db_dir / "GeoLite2-Country.mmdb"
        asn_path = db_dir / "GeoLite2-ASN.mmdb"

        self._country_reader: maxminddb.Reader | None = None
        self._asn_reader: maxminddb.Reader | None = None

        if country_path.exists():
            try:
                self._country_reader = maxminddb.open_database(str(country_path))
            except Exception as e:  # noqa: BLE001
                log.warning("yf.geoip.country_open_failed", error=str(e))
        else:
            log.warning("yf.geoip.country_db_missing", path=str(country_path))

        if asn_path.exists():
            try:
                self._asn_reader = maxminddb.open_database(str(asn_path))
            except Exception as e:  # noqa: BLE001
                log.warning("yf.geoip.asn_open_failed", error=str(e))
        else:
            log.warning("yf.geoip.asn_db_missing", path=str(asn_path))

    @staticmethod
    def _resolve_client_ip(request: Request) -> str | None:
        """CF-Connecting-IP > X-Forwarded-For (primo) > peer."""
        cf = request.headers.get("CF-Connecting-IP")
        if cf:
            return cf.strip()
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        if request.client is not None:
            return request.client.host
        return None

    def _lookup(self, ip_str: str) -> tuple[str | None, int | None]:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None, None

        country: str | None = None
        asn: int | None = None

        if self._country_reader is not None:
            try:
                rec = self._country_reader.get(str(ip))
                if isinstance(rec, dict):
                    country = (rec.get("country", {}) or {}).get("iso_code")
            except Exception:  # noqa: BLE001
                pass

        if self._asn_reader is not None:
            try:
                rec = self._asn_reader.get(str(ip))
                if isinstance(rec, dict):
                    asn = rec.get("autonomous_system_number")
            except Exception:  # noqa: BLE001
                pass

        return country, asn

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        ip = self._resolve_client_ip(request)
        request.state.client_ip = ip
        request.state.country = None
        request.state.asn = None

        if ip is not None:
            country, asn = self._lookup(ip)
            request.state.country = country
            request.state.asn = asn

        return await call_next(request)
