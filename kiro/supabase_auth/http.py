# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
HTTP exception mapping for Phase C user-auth (milestone M7).

This is the SINGLE place the typed ``SupabaseAuthError`` family is turned into an
HTTP response. The pure auth layer (verifier, jwks_cache, user) and the M6
dependency deliberately raise typed exceptions and perform NO HTTP mapping
(verifier docstring, dependencies §"Milestone boundary"); M7 owns that mapping
here so the policy lives in one auditable place and every protected route gets an
identical body/header shape.

Decision matrix (M7 §2/§3 + M8a §9, resolved UD-1/UD-4):

    exception                  status  code                       extra headers
    -----------------------------------------------------------------------------
    TokenExpiredError          401     TOKEN_EXPIRED              WWW-Authenticate
    InvalidIdentityError       401     INVALID_TOKEN             WWW-Authenticate
    InvalidTokenError          401     INVALID_TOKEN             WWW-Authenticate
    AuthRateLimitedError       429     RATE_LIMITED              Retry-After
    JwksUnavailableError       503     AUTH_BACKEND_UNAVAILABLE  Retry-After
    OnboardingRequiredError    403     ONBOARDING_REQUIRED       (none)            [M8a]
    SupabaseAuthzError         403     ACCOUNT_DISABLED          (none)            [M8a]
      (banned/deleted/unknown collapse to one code+message — no disclosure)
    UserStateUnavailableError  503     AUTH_BACKEND_UNAVAILABLE  Retry-After       [M8a]
    ProfileUnavailableError    500     INTERNAL                  (none)            [M8a]
    SupabaseAuthError (base)   401     INVALID_TOKEN             WWW-Authenticate

The authz branches (403) are placed BEFORE the base 401 fallback so authorization
failures never collapse into a 401 (PhaseC §7.1: 401-vs-403 discipline, never
crossed). 403 carries NO WWW-Authenticate (the credential was valid; re-auth does
not help).

Disclosure discipline (plan §11; mirrors the verifier's generic-collapse):
  - The handler maps on the exception *type* only. It NEVER reads ``exc.detail``
    into the response — ``detail`` is a server-log-only reason (it can name the
    PyJWT failure mode) and is surfaced to no client.
  - Every non-expiry auth failure collapses to one ``INVALID_TOKEN`` code with one
    fixed message, so a client cannot learn *why* verification failed. Only
    ``TOKEN_EXPIRED`` is distinguished (safe — it just says "refresh and retry").
  - ``WWW-Authenticate`` / any ``realm`` carries no Supabase URL, issuer, project
    ref, or JWKS URL.

Error-body envelope (UD-4 → structured)::

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

``request_id`` is read from ``request.state.request_id`` (set by the M6
``RequestIdMiddleware``), falling back to the context var, and is omitted entirely
if neither is present (never emitted as ``null``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from .context import get_request_id
from .exceptions import (
    AuthRateLimitedError,
    JwksUnavailableError,
    OnboardingRequiredError,
    ProfileUnavailableError,
    SupabaseAuthError,
    SupabaseAuthzError,
    TokenExpiredError,
    UserStateUnavailableError,
)

# --- Machine-readable codes (plan §2). -------------------------------------- #
# Authentication codes (M7):
CODE_TOKEN_EXPIRED = "TOKEN_EXPIRED"
CODE_INVALID_TOKEN = "INVALID_TOKEN"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_AUTH_BACKEND_UNAVAILABLE = "AUTH_BACKEND_UNAVAILABLE"

# Authorization codes — defined reserved in M7; ACTIVATED in M8a (the authz
# family now emits ACCOUNT_DISABLED / ONBOARDING_REQUIRED). FORBIDDEN stays
# reserved-not-emitted (roles / M8b are deferred).
CODE_ONBOARDING_REQUIRED = "ONBOARDING_REQUIRED"   # 403 (M8a)
CODE_ACCOUNT_DISABLED = "ACCOUNT_DISABLED"         # 403 (M8a)
CODE_FORBIDDEN = "FORBIDDEN"                        # reserved (403) — M8b roles, not emitted

# Server-fault code (M8a): a valid JWT with no profile row after retry (D4).
CODE_INTERNAL = "INTERNAL"                          # 500 (M8a)

# --- Fixed, generic client messages (never derived from exc.detail). -------- #
# Identical for every invalid-token cause (disclosure rule); only expiry differs.
_MSG_TOKEN_EXPIRED = "Token expired."
_MSG_INVALID_TOKEN = "Authentication failed."
_MSG_RATE_LIMITED = "Too many authentication attempts."
_MSG_BACKEND_UNAVAILABLE = "Authentication is temporarily unavailable."
# Authz/server messages (M8a). ACCOUNT_DISABLED is the collapsed bucket for
# banned/deleted/indeterminate — the client never learns which (disclosure rule).
_MSG_ACCOUNT_DISABLED = "Account is not available."
_MSG_ONBOARDING_REQUIRED = "Onboarding is required."
_MSG_INTERNAL = "Internal server error."

# Retry-After seconds. Throttle = the auth-failure window (bootstrap.py = 60s);
# JWKS = a short back-off (the cache serves stale within its grace window).
_RETRY_AFTER_THROTTLE = "60"
_RETRY_AFTER_JWKS = "5"

# RFC 6750 Bearer challenge. error="invalid_token" covers expiry and every other
# bad-token case (expiry is a sub-case; the TOKEN_EXPIRED distinction lives in the
# body code, not the header). No realm → no backend identity disclosure.
_WWW_AUTH_BEARER = 'Bearer error="invalid_token"'


@dataclass(frozen=True)
class _Mapping:
    """The HTTP shape for one exception class (everything but request_id)."""

    status: int
    code: str
    message: str
    headers: Dict[str, str]


def _resolve(exc: SupabaseAuthError) -> _Mapping:
    """
    Map a typed exception to its HTTP shape on TYPE alone (never reads detail).

    Order: most-specific first. ``TokenExpiredError`` before the generic bucket;
    the dedicated throttle/transient types before the ``SupabaseAuthError`` base
    fallback. ``InvalidIdentityError`` is a ``SupabaseAuthError`` subtype (not an
    ``InvalidTokenError``), so it is caught by the base fallback → 401
    INVALID_TOKEN, which is exactly its advisory mapping.
    """
    if isinstance(exc, TokenExpiredError):
        return _Mapping(
            status=401,
            code=CODE_TOKEN_EXPIRED,
            message=_MSG_TOKEN_EXPIRED,
            headers={"WWW-Authenticate": _WWW_AUTH_BEARER},
        )
    if isinstance(exc, AuthRateLimitedError):
        # 429, Retry-After, and deliberately NO WWW-Authenticate (not a
        # credential challenge — the caller may hold a valid token).
        return _Mapping(
            status=429,
            code=CODE_RATE_LIMITED,
            message=_MSG_RATE_LIMITED,
            headers={"Retry-After": _RETRY_AFTER_THROTTLE},
        )
    if isinstance(exc, JwksUnavailableError):
        # Transient dependency failure (D5): 503 + Retry-After, no challenge.
        return _Mapping(
            status=503,
            code=CODE_AUTH_BACKEND_UNAVAILABLE,
            message=_MSG_BACKEND_UNAVAILABLE,
            headers={"Retry-After": _RETRY_AFTER_JWKS},
        )

    # --- M8a authorization branches (BEFORE the 401 fallback). --------------- #
    # The authz family means authentication PASSED; these are 403, NOT 401
    # (PhaseC §7.1, never crossed). 403 carries NO WWW-Authenticate — the
    # credential was fine, so re-auth would not help.
    if isinstance(exc, OnboardingRequiredError):
        # The one authz distinction surfaced (tells the client what to do).
        return _Mapping(
            status=403,
            code=CODE_ONBOARDING_REQUIRED,
            message=_MSG_ONBOARDING_REQUIRED,
            headers={},
        )
    if isinstance(exc, SupabaseAuthzError):
        # Banned / deleted / indeterminate (fail-closed) collapse to ONE code +
        # message — the client never learns which (disclosure rule, §9.3).
        return _Mapping(
            status=403,
            code=CODE_ACCOUNT_DISABLED,
            message=_MSG_ACCOUNT_DISABLED,
            headers={},
        )
    if isinstance(exc, UserStateUnavailableError):
        # Transient state-read failure (D5): 503 + Retry-After. Fail-closed
        # (the request was rejected, not granted), retryable.
        return _Mapping(
            status=503,
            code=CODE_AUTH_BACKEND_UNAVAILABLE,
            message=_MSG_BACKEND_UNAVAILABLE,
            headers={"Retry-After": _RETRY_AFTER_JWKS},
        )
    if isinstance(exc, ProfileUnavailableError):
        # Valid JWT, no profile row after retry (D4): server fault → 500. Generic
        # message; the specific reason stays in the server log only.
        return _Mapping(
            status=500,
            code=CODE_INTERNAL,
            message=_MSG_INTERNAL,
            headers={},
        )

    # Base fallback: InvalidTokenError, InvalidIdentityError, and any future
    # SupabaseAuthError subtype that lacks its own branch → generic 401.
    return _Mapping(
        status=401,
        code=CODE_INVALID_TOKEN,
        message=_MSG_INVALID_TOKEN,
        headers={"WWW-Authenticate": _WWW_AUTH_BEARER},
    )


def _request_id(request: Request) -> Optional[str]:
    """Best-effort correlation id: request.state first, then the context var."""
    rid = getattr(getattr(request, "state", None), "request_id", None)
    if rid:
        return rid
    return get_request_id()


def build_error_body(code: str, message: str, request_id: Optional[str]) -> dict:
    """
    Construct the structured error envelope (UD-4).

    Takes only ``(code, message, request_id)`` — NEVER an exception — so there is
    no path by which ``exc.detail`` or a claim value can reach the client body.
    ``request_id`` is omitted entirely when unavailable (never a ``null`` field).
    """
    error: Dict[str, str] = {"code": code, "message": message}
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


async def supabase_auth_exception_handler(
    request: Request, exc: SupabaseAuthError
) -> JSONResponse:
    """
    FastAPI exception handler for the whole ``SupabaseAuthError`` family.

    Registered once via :func:`register_exception_handlers`. Maps the exception to
    its status/code/headers (§2), builds the structured body, and logs a single
    secret-free server line (the type name + ``detail`` are safe for logs — detail
    is secret-free by the M2/M4 contract — but never reach the response).
    """
    mapping = _resolve(exc)
    rid = _request_id(request)

    # Server-side correlation line. `detail` is server-log-only and secret-free by
    # contract; it is logged here, NEVER placed in the response.
    logger.info(
        "user-auth rejected: type={} status={} code={} request_id={} detail={}",
        type(exc).__name__,
        mapping.status,
        mapping.code,
        rid,
        getattr(exc, "detail", None),
    )

    return JSONResponse(
        status_code=mapping.status,
        content=build_error_body(mapping.code, mapping.message, rid),
        headers=mapping.headers,
    )


def register_exception_handlers(app) -> None:
    """
    Register the single ``SupabaseAuthError`` handler on the app.

    Called from ``main.py`` next to the existing validation handler. Registration
    is unconditional and harmless when no route raises (dormant deployments simply
    never trigger it); catching the base class covers every current and future
    subtype through one policy.
    """
    app.add_exception_handler(SupabaseAuthError, supabase_auth_exception_handler)
