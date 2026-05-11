"""CSRF middleware: double-submit cookie pattern.

Il backend genera un token random (cookie `yf_csrf`, NON HttpOnly così la
SPA può leggerlo via JavaScript). Per ogni richiesta non-safe (POST/PUT/
PATCH/DELETE) la SPA legge il cookie e rimanda lo stesso valore in header
`X-YF-CSRF`. Il middleware confronta i due. Se non combaciano → 403.

Esenzioni:
  - metodi safe (GET, HEAD, OPTIONS)
  - richieste con header `Authorization: Bearer ...` (app mobile, no cookie)
  - login/register endpoint (cookie ancora non emesso al primo contatto)
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Endpoint dove non possiamo richiedere il token CSRF (no cookie iniziale)
CSRF_BOOTSTRAP_PATHS = frozenset(
    {
        "/yf_auth/register",
        "/yf_auth/login",
        "/yf_auth/forgot-password",
        "/yf_auth/reset-password",
        "/yf_auth/verify-email",
        "/yf_auth/resend-verification",
    }
)

CSRF_COOKIE_NAME = "yf_csrf"
CSRF_HEADER_NAME = "x-yf-csrf"


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()
        path = request.url.path

        # Validazione su metodi non-safe, escludendo bootstrap auth, Bearer
        # e admin (HTTP Basic auth, no session cookie → CSRF inapplicabile).
        needs_check = (
            method not in SAFE_METHODS
            and path not in CSRF_BOOTSTRAP_PATHS
            and not path.startswith("/yf_admin")
            and not request.headers.get("authorization", "").lower().startswith("bearer ")
            and not request.headers.get("authorization", "").lower().startswith("basic ")
        )

        if needs_check:
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if (
                not cookie_token
                or not header_token
                or not secrets.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "csrf_failed",
                            "message": "Token CSRF mancante o non valido.",
                        }
                    },
                )

        response = await call_next(request)

        # Emetti/rinfresca il cookie CSRF se assente
        if CSRF_COOKIE_NAME not in request.cookies:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=_new_token(),
                max_age=60 * 60 * 24 * 30,  # 30 giorni
                secure=request.url.scheme == "https",
                httponly=False,  # la SPA deve leggerlo
                samesite="lax",
            )

        return response
