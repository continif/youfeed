"""Eccezioni applicative + handler globali per FastAPI.

Convenzione di risposta errore (JSON):
    {
      "error": {
        "code": "string_machine_readable",
        "message": "Messaggio umano",
        "details": {...}            // opzionale, chiave-valore aggiuntivi
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Errore applicativo con codice macchina + payload opzionale."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


def _error_response(
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra gli handler che producono risposte JSON consistenti."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_req: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Preserva eventuali header come WWW-Authenticate (HTTP Basic prompt
        # del browser) sollevati da `HTTPException(headers={...})`.
        return _error_response(
            code=f"http_{exc.status_code}",
            message=str(exc.detail) if exc.detail else "HTTP error",
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _req: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            code="validation_error",
            message="Richiesta non valida",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": exc.errors()},
        )
