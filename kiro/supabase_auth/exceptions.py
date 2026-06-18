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
Exception types for Phase C Supabase user-auth verification (milestone M2).

Two-layer model (design §7, review §6):
  - These are TYPED PYTHON exceptions carrying an internal, specific reason for
    server-side logs. They perform NO HTTP mapping — translating an exception to
    a status code, machine-readable ``code``, and ``WWW-Authenticate`` header is
    done in M7 (FastAPI exception handlers), not here.
  - The client-facing disclosure rule (M7) collapses everything to a generic
    ``INVALID_TOKEN`` except ``TOKEN_EXPIRED``. To support that, the verifier
    raises only the three concrete types below; the *specific* PyJWT reason is
    kept in ``detail`` for logs and never surfaced to the client.

Hierarchy::

    SupabaseAuthError                 (base for all M2+ runtime auth errors)
    ├── InvalidTokenError             → 401 / INVALID_TOKEN  (generic bucket)   [M7]
    ├── TokenExpiredError             → 401 / TOKEN_EXPIRED   (safe distinction) [M7]
    ├── AuthRateLimitedError          → 429 / RATE_LIMITED + Retry-After (UD-1)  [M7]
    ├── JwksUnavailableError          → 503 / transient       (D5)              [M7]
    ├── SupabaseAuthzError            (authorization base; → 403)               [M8a]
    │   ├── AccountDisabledError      → 403 / ACCOUNT_DISABLED (fail-closed)     [M8a]
    │   ├── UserBannedError           → 403 / ACCOUNT_DISABLED                   [M8a]
    │   ├── UserDeletedError          → 403 / ACCOUNT_DISABLED                   [M8a]
    │   └── OnboardingRequiredError   → 403 / ONBOARDING_REQUIRED                [M8a]
    ├── ProfileUnavailableError       → 500 / server fault    (D4)              [M8a]
    └── UserStateUnavailableError     → 503 / transient        (D5)             [M8a]

Note: configuration problems use ``SupabaseAuthConfigError`` (defined in
``kiro/supabase_auth/config.py``) — that is a startup/config concern, distinct
from these per-request verification errors.
"""

from __future__ import annotations

from typing import Optional


class SupabaseAuthError(Exception):
    """
    Base class for Phase C user-auth verification errors (per-request).

    ``detail`` carries a specific, server-side-only reason for structured logs.
    It must NEVER contain the JWT, its signature, or claim *values* — only a
    short reason string (e.g. "exp in past", "kid not found after refresh").
    The client-facing message/code is assigned later by the M7 handler, not here.
    """

    def __init__(self, message: str, *, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.detail = detail


class InvalidTokenError(SupabaseAuthError):
    """
    The token is not acceptable for any reason other than plain expiry.

    The generic bucket: bad signature, wrong/disallowed algorithm, wrong
    audience/issuer, malformed token, missing/empty required claim, far-future
    ``iat``, immature (``nbf``) token, unknown ``kid`` after a refresh, etc.
    Collapsed deliberately so the client cannot learn *why* verification failed.
    Maps to 401 / ``INVALID_TOKEN`` at M7.
    """


class TokenExpiredError(SupabaseAuthError):
    """
    The token signature/claims are otherwise fine but ``exp`` is in the past
    (beyond the configured leeway). The one distinction safe to expose, because
    it usefully tells the client to refresh and retry. Maps to 401 /
    ``TOKEN_EXPIRED`` at M7.
    """


class JwksUnavailableError(SupabaseAuthError):
    """
    The signing keys could not be retrieved (JWKS endpoint unreachable, timed
    out, returned a non-200, or returned an unparseable document).

    This is a TRANSIENT dependency failure, not an authentication failure: it is
    kept distinct so M7 maps it to 503 (back off and retry) rather than 401
    (re-login). Decision D5.
    """


class AuthRateLimitedError(SupabaseAuthError):
    """
    The auth-failure throttle rejected this attempt (DoS pre-check, M3).

    NOT an authentication verdict: the caller may well hold a valid token — it is
    simply being rate-limited. Kept distinct from ``InvalidTokenError`` so M7 maps
    it to 429 (Too Many Requests) with a ``Retry-After`` header, rather than a
    misleading 401 (UD-1 → R1). Like the base, it carries a secret-free ``detail``
    for server logs and performs NO HTTP mapping (M7's job). The throttle path is
    deliberately NOT audited (avoid amplifying abuse into background DB writes).
    """


# ==================================================================================================
# M8a — Authorization error family (authentication PASSED; the request is denied
# on durable, DB-sourced user state). See M8AuthorizationPlanV3 §9.
# ==================================================================================================
#
# Hierarchy (M8a)::
#
#     SupabaseAuthError
#     ├── SupabaseAuthzError                 (authorization, NOT authentication)
#     │   ├── AccountDisabledError           → 403 ACCOUNT_DISABLED  (fail-closed/unknown bucket)
#     │   ├── UserBannedError                → 403 ACCOUNT_DISABLED
#     │   ├── UserDeletedError               → 403 ACCOUNT_DISABLED
#     │   └── OnboardingRequiredError        → 403 ONBOARDING_REQUIRED
#     ├── ProfileUnavailableError            → 500 (server fault, D4 — NOT authz)
#     └── UserStateUnavailableError          → 503 (transient state-read failure, D5)
#
# The intermediate ``SupabaseAuthzError`` makes the 401-vs-403 discipline
# (PhaseC §7.1) STRUCTURAL: M7's handler default is 401, so M8's handler maps the
# authz family to 403 via explicit branches placed BEFORE the 401 fallback (§9.5).
# These are still typed exceptions carrying a secret-free ``detail`` for logs and
# performing NO HTTP mapping themselves.


class SupabaseAuthzError(SupabaseAuthError):
    """
    Base for AUTHORIZATION failures — the request authenticated successfully
    (identity is established) but is not permitted to proceed on durable user
    state. Distinct from the authentication errors above so the M8 HTTP handler
    can map this whole branch to 403 (never 401 — PhaseC §7.1). Never raised
    directly; a concrete subtype is always used.
    """


class AccountDisabledError(SupabaseAuthzError):
    """
    The account may not proceed and the precise reason is deliberately NOT
    distinguished to the client — the generic / fail-closed bucket. Raised for an
    indeterminate or unrecognized ``UserState`` (fail closed, M4-D4). Maps to 403 /
    ``ACCOUNT_DISABLED`` at M8; the granular reason stays in the server log only.
    """


class UserBannedError(SupabaseAuthzError):
    """
    The user is banned (``auth.users.banned_until`` is in the future). Maps to 403
    / ``ACCOUNT_DISABLED`` at M8 — collapsed with disabled/deleted so the client
    cannot tell banned from deleted (disclosure rule, §9.3).
    """


class UserDeletedError(SupabaseAuthzError):
    """
    The user is soft-deleted (``public.users.deleted_at`` is set). Maps to 403 /
    ``ACCOUNT_DISABLED`` at M8 (collapsed with banned/disabled).
    """


class OnboardingRequiredError(SupabaseAuthzError):
    """
    The user is active but has not completed onboarding, and the route requires it
    (``require_onboarded``). Maps to 403 / ``ONBOARDING_REQUIRED`` at M8 — the one
    authz distinction that IS surfaced, because it tells the client what to do.
    """


class ProfileUnavailableError(SupabaseAuthError):
    """
    A valid JWT resolved to NO ``public.users`` row even after the bounded retry —
    a server-side fault (the Phase A ``handle_new_user`` trigger contract is
    broken), NOT a client/credential error and NOT an authorization decision
    (D4). Maps to 500 at M8 with an alert-worthy server log. Never triggers a
    lazy-provision.
    """


class UserStateUnavailableError(SupabaseAuthError):
    """
    The authoritative user-state read failed transiently (DB down/timeout/pool
    exhausted). A SERVER dependency failure, not an authorization verdict — kept
    distinct so M8 maps it to 503 (back off and retry), NOT 403. Crucially this
    FAILS CLOSED: the request is still rejected (never fail-open), just with a
    retryable status. Decision D5.
    """

