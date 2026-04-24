"""Unified error-response schema for the Finance HTTP API.

Before this module, each view built its own error shape — some returned
``{"error": "..."}`` with HTTP 200, others ``{"ok": false, "reason": ...}``,
still others a free-form ``"error_type"`` string derived from the last
exception. The frontend had to parse three different shapes and could never
rely on HTTP status codes.

This module defines:

* ``ErrorCode`` — stable machine-readable identifiers the frontend can
  branch on (enum values are the wire form).
* ``FinanceApiError`` — exception that carries a code, a user-facing
  German message, an HTTP status, and optional structured detail.
* ``error_response(view, err)`` — renders a ``FinanceApiError`` into the
  canonical JSON body + correct HTTP status.
* Pre-built convenience errors (NOT_CONFIGURED, RATE_LIMITED, …) so
  views can just ``raise NOT_CONFIGURED()`` instead of hand-building
  dicts.

Response shape (versioned so future changes stay backwards-compatible)::

    {
      "ok": false,
      "error": {
        "code": "not_configured",   // ErrorCode.value
        "message": "...",           // user-facing German text
        "detail": { ... } | null    // optional structured context
      }
    }

Any view that raises ``FinanceApiError`` gets converted via
``error_response``. Views that succeed keep their existing shape — this
module only standardises the failure path, not the success path.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from aiohttp import web


class ErrorCode(str, Enum):
    """Stable machine-readable error codes exchanged with the frontend."""

    NOT_CONFIGURED = "not_configured"
    INVALID_BODY = "invalid_body"
    MISSING_PARAM = "missing_param"
    NO_CREDENTIALS = "no_credentials"
    INVALID_CREDENTIALS = "invalid_credentials"
    CALLBACK_NOT_HTTPS = "callback_not_https"
    REDIRECT_NOT_REGISTERED = "redirect_not_registered"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_ERROR = "upstream_error"
    RATE_LIMITED = "rate_limited"
    ADMIN_REQUIRED = "admin_required"
    INTERNAL = "internal"


# Default HTTP status per code. Views can override via constructor.
_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.NOT_CONFIGURED: 404,
    ErrorCode.INVALID_BODY: 400,
    ErrorCode.MISSING_PARAM: 400,
    ErrorCode.NO_CREDENTIALS: 400,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.CALLBACK_NOT_HTTPS: 400,
    ErrorCode.REDIRECT_NOT_REGISTERED: 400,
    ErrorCode.UPSTREAM_TIMEOUT: 504,
    ErrorCode.UPSTREAM_ERROR: 502,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.ADMIN_REQUIRED: 403,
    ErrorCode.INTERNAL: 500,
}


class FinanceApiError(Exception):
    """Raised by API views to emit a structured error response."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or _DEFAULT_STATUS.get(code, 500)
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the canonical wire shape."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return {"ok": False, "error": payload}


def error_response(
    view: Any, err: FinanceApiError
) -> web.Response:
    """Render a FinanceApiError using ``HomeAssistantView.json``.

    ``view`` must provide a ``json(payload, status_code=…)`` helper
    — every ``HomeAssistantView`` does.
    """
    return view.json(err.to_dict(), status_code=err.status)


# ---------------------------------------------------------------------------
# Convenience factories — keep the call sites short and consistent.
# ---------------------------------------------------------------------------


def not_configured() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.NOT_CONFIGURED,
        "Finance ist noch nicht konfiguriert. Bitte Setup-Wizard öffnen.",
    )


def invalid_body() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.INVALID_BODY,
        "Ungültiger JSON-Body.",
    )


def missing_param(name: str) -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.MISSING_PARAM,
        f"Pflichtfeld fehlt: {name}",
        detail={"field": name},
    )


def no_credentials() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.NO_CREDENTIALS,
        "Keine API-Credentials gespeichert — Integration neu einrichten.",
    )


def invalid_credentials() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.INVALID_CREDENTIALS,
        "Enable-Banking-Credentials wurden abgelehnt.",
    )


def callback_not_https(callback_url: str) -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.CALLBACK_NOT_HTTPS,
        (
            "Bank-Autorisierung erfordert HTTPS. Aktuelle Callback-URL "
            f"'{callback_url}' ist HTTP — öffne das Finance-Panel über "
            "die HTTPS-URL deiner HA-Instanz (z. B. Nabu Casa) oder "
            "richte ein TLS-Zertifikat ein."
        ),
        detail={"callback_url": callback_url},
    )


def redirect_not_registered(callback_url: str) -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.REDIRECT_NOT_REGISTERED,
        (
            f"Redirect-URL '{callback_url}' ist bei Enable Banking nicht "
            "hinterlegt. Bitte im Enable-Banking-Dashboard als erlaubte "
            "Callback-URL eintragen."
        ),
        detail={"callback_url": callback_url},
    )


def upstream_timeout() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.UPSTREAM_TIMEOUT,
        "Enable-Banking-API hat nicht rechtzeitig geantwortet. Bitte erneut versuchen.",
    )


def upstream_error(reason: str) -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.UPSTREAM_ERROR,
        f"Enable Banking: {reason}",
    )


def rate_limited(until_iso: str | None = None) -> FinanceApiError:
    msg = (
        "Tageslimit der Bank-API erreicht (4 Abfragen/Tag). "
        "Cache bleibt aktiv, neue Live-Daten ab morgen 00:00."
    )
    return FinanceApiError(
        ErrorCode.RATE_LIMITED,
        msg,
        detail={"rate_limited_until": until_iso} if until_iso else None,
    )


def admin_required() -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.ADMIN_REQUIRED,
        "Diese Aktion erfordert Admin-Rechte.",
    )


def internal(reason: str) -> FinanceApiError:
    return FinanceApiError(
        ErrorCode.INTERNAL,
        f"Interner Fehler: {reason}",
    )
