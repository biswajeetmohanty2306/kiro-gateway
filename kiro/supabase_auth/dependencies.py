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
FastAPI authentication dependency for Phase C (milestone M6).

``get_current_user`` is the SINGLE FastAPI-aware auth entry point. It runs the
end-to-end authenticated-request flow against the components wired onto
``app.state.supabase_auth`` (built by ``bootstrap.build_supabase_auth``):

    Authorization header → (rate-limit) → JWT verify (JWKS internal) →
    AuthenticatedUser → best-effort audit on failure → request context.

Milestone boundary (design §4):
  - This dependency RAISES the existing typed exceptions only
    (``InvalidTokenError`` / ``TokenExpiredError`` / ``JwksUnavailableError``
    from M2, ``InvalidIdentityError`` from M4). It introduces NO new exception
    type and performs NO HTTP status mapping — turning these into 401/403/503 +
    ``WWW-Authenticate`` + bodies is M7's job.
  - NO routes, NO authorization (roles/user-state), NO HTTP responses here.

Two wiring choices, both security-improving refinements of the plan's flow:
  - Rate-limit BEFORE token extraction, so a flood of header-less / malformed
    requests is throttled too (extracting first would let no-token floods bypass
    the limiter).
  - NO audit row on the throttle path: emitting a best-effort DB write per
    throttled request would amplify the very abuse the throttle exists to stop.

Client IP provenance (M6-D5): the trusted socket peer (``request.client.host``);
``X-Forwarded-For`` is NOT trusted by default (a spoofable header must not drive
throttling or be recorded as fact). A trusted-proxy rule can be added later.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import Request

from .audit import AuditEvent
from .context import get_request_id
from .exceptions import (
    AuthRateLimitedError,
    InvalidTokenError,
    JwksUnavailableError,
    OnboardingRequiredError,
    ProfileUnavailableError,
    SupabaseAuthError,
    SupabaseAuthzError,
)
from .profile import UserProfile
from .user import AuthenticatedUser, build_authenticated_user
from .user_state import enforce_active

# Bucket for requests with no determinable client IP — they share one budget
# (conservative: an unknown-IP flood is throttled together rather than exempt).
_UNKNOWN_IP = "unknown"

# Bounded missing-profile retry (M8a / D4): a valid JWT with no public.users row
# is almost always trigger-lag right after signup. Retry ONCE after a short delay
# before treating it as a server fault (ProfileUnavailableError → 500). Never a
# lazy-provision.
_PROFILE_RETRY_DELAY_SECONDS = 0.25


def _client_ip(request: Request) -> str:
    """Trusted client IP = the socket peer. ``X-Forwarded-For`` is ignored (M6-D5)."""
    client = request.client
    if client and client.host:
        return client.host
    return _UNKNOWN_IP


def _extract_bearer(request: Request) -> Optional[str]:
    """
    Return the bearer token from ``Authorization: Bearer <token>``, or ``None``
    if the header is absent, not a Bearer scheme, or empty.
    """
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def get_current_user(request: Request) -> AuthenticatedUser:
    """
    Authenticate the request and return its :class:`AuthenticatedUser`.

    Raises a typed :class:`SupabaseAuthError` subtype on any failure (no HTTP
    mapping — M7). On success, also sets ``request.state.user``.

    Flow (design §3):
      0. resolve the wired bundle off ``app.state`` (dormant → raise).
      1. rate-limit the client IP (DoS pre-check) — throttled → raise, no audit.
      2. extract the bearer token — missing/malformed → raise + audit.
      3. verify the JWT (JWKS lookup is internal to the verifier) → raise + audit.
      4. build the identity object → raise + audit.
      5. success: reset the IP's failure budget, set context, return — NO audit
         (per M5 D6: routine successes are not audited).
    """
    bundle = getattr(request.app.state, "supabase_auth", None)
    if bundle is None:
        # Phase C not configured / dormant. Defensive: in M6 this dependency is
        # attached to no route, so this path is unreachable in normal operation.
        # Collapse to INVALID_TOKEN (M2's generic bucket); M7 owns the real
        # mapping decision. No audit logger exists to call here.
        raise InvalidTokenError(
            "User authentication is not available.",
            detail="phase C user-auth dormant (no app.state.supabase_auth)",
        )

    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    request_id = get_request_id()

    def _audit_failure() -> None:
        # Best-effort, fire-and-forget; never blocks or raises (M5 guarantees).
        bundle.audit_logger.record(
            AuditEvent.AUTH_FAILURE,
            ip_address=client_ip,
            user_agent=user_agent,
            request_id=request_id,
        )

    # 1. DoS pre-check (counts the attempt). Throttle path emits NO audit, to
    #    avoid amplifying abuse into background DB writes. Raises the dedicated
    #    AuthRateLimitedError so M7 maps it to 429 + Retry-After (UD-1 → R1),
    #    never a misleading 401.
    if not bundle.rate_limiter.allow(client_ip):
        raise AuthRateLimitedError(
            "Too many authentication attempts.",
            detail="auth-failure rate limit exceeded",
        )

    # 2. Extract the bearer token.
    token = _extract_bearer(request)
    if token is None:
        _audit_failure()
        raise InvalidTokenError(
            "Missing or malformed Authorization header.",
            detail="no/non-bearer Authorization header",
        )

    # 3. Verify (signature + claims; JWKS resolved inside verify()).
    try:
        claims = await bundle.verifier.verify(token)
    except SupabaseAuthError:
        # Typed (TokenExpiredError / InvalidTokenError / JwksUnavailableError);
        # re-raise unchanged for M7 to map. Audit the failure first.
        _audit_failure()
        raise

    # 4. Build the immutable identity object (M4).
    try:
        user = build_authenticated_user(claims)
    except SupabaseAuthError:  # InvalidIdentityError
        _audit_failure()
        raise

    # 5. Success: clear this IP's failure budget, propagate context, return.
    #    No audit row on success (M5 D6 volume rule).
    bundle.rate_limiter.reset(client_ip)
    request.state.user = user
    return user


async def require_supabase_user(request: Request) -> AuthenticatedUser:
    """
    Route-facing dependency wrapping :func:`get_current_user` for M7.

    Adds ONE behaviour over the M6 dependency: a dormant pre-empt. If Phase C is
    not wired (``app.state.supabase_auth is None``) this raises
    :class:`JwksUnavailableError` (→ 503 ``AUTH_BACKEND_UNAVAILABLE`` at M7),
    NOT the generic :class:`InvalidTokenError` ``get_current_user`` would raise —
    a dormant backend is a server-side "auth unavailable" condition, not a bad
    credential, so it must never look like a 401 to the client (plan §1.3, §3).

    Under the activation strategy (plan §1.5) ``routes_user`` is mounted only when
    Phase C is active, so this branch is defensive belt-and-braces; it also keeps
    the dependency safe if a deployment mounts the router unconditionally.

    Still performs NO HTTP mapping: it raises a typed :class:`SupabaseAuthError`
    subtype only. M7's exception handler turns it into a response.
    """
    if getattr(request.app.state, "supabase_auth", None) is None:
        raise JwksUnavailableError(
            "User authentication is not available.",
            detail="phase C user-auth dormant (no app.state.supabase_auth)",
        )
    return await get_current_user(request)


async def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """
    Non-raising variant of :func:`get_current_user` (plan §1.3; PhaseC §2.2).

    Returns the :class:`AuthenticatedUser` when the request carries a valid token,
    or ``None`` on ANY auth failure (missing/expired/invalid token, throttle,
    dormant backend, JWKS outage). It NEVER raises a :class:`SupabaseAuthError`
    and so never produces a 401/403/429/503 — for endpoints that vary behaviour by
    auth presence without requiring it.

    The wrapped :func:`get_current_user` still runs its best-effort failure audit
    and rate-limit accounting; this wrapper only suppresses the raised exception.
    """
    try:
        return await get_current_user(request)
    except SupabaseAuthError:
        return None


# ==================================================================================================
# M8a — Authorization layering (READ 1 state gate → READ 2 profile body → onboarding gate).
# Each dependency calls the one below it and adds exactly one check, raising typed
# authz/server errors only (HTTP mapping is http.py). See M8AuthorizationPlanV3 §7.1.
# ==================================================================================================


def _audit_authz_denied(request: Request, bundle, user_id: str) -> None:
    """
    Emit a best-effort ``AUTHZ_DENIED`` audit row at an authorization gate.

    The subject is known here (the request authenticated), so ``user_id`` is
    recorded. Fire-and-forget; never blocks or fails the request (M5 best-effort).
    Called only on a 403 authz denial — NOT for server faults (500) or transient
    read failures (503), which are not authorization decisions (V3 §10).
    """
    bundle.audit_logger.record(
        AuditEvent.AUTHZ_DENIED,
        user_id=user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(),
    )


async def get_auth_state(request: Request) -> AuthenticatedUser:
    """
    Authorization enforcement dependency (M8a READ 1).

    Authenticates (via :func:`require_supabase_user` — 401 family, or 503 if the
    backend is dormant), then performs the AUTHORITATIVE, RLS-bypassing state read
    and enforces it fail-closed. Returns the :class:`AuthenticatedUser` when the
    request may proceed (state is ACTIVE); otherwise raises a typed error that M8's
    handler maps:
      - deleted / banned / indeterminate → 403 (``SupabaseAuthzError`` family),
        and one best-effort ``AUTHZ_DENIED`` audit row is emitted at this gate;
      - missing ``public.users`` row (after one bounded retry — D4) → 500
        (``ProfileUnavailableError``), NOT audited as a denial (it is a server
        fault);
      - transient state-read failure → 503 (``UserStateUnavailableError``), NOT
        audited and NEVER fail-open.

    Endpoints that only need "is this user allowed?" depend on this directly,
    without paying for the profile-body read. Also stashes the resolved
    ``AuthState`` on ``request.state.auth_state`` for handlers that want it.
    """
    user = await require_supabase_user(request)
    bundle = request.app.state.supabase_auth  # non-None (require_supabase_user checked)

    # READ 1, with the single bounded missing-profile retry (D4): a brand-new
    # signup may briefly precede its handle_new_user-trigger row.
    auth_state = await bundle.state_reader.read_auth_state(user.user_id)
    if not auth_state.row_exists:
        await asyncio.sleep(_PROFILE_RETRY_DELAY_SECONDS)
        auth_state = await bundle.state_reader.read_auth_state(user.user_id)

    try:
        enforce_active(auth_state)
    except SupabaseAuthzError:
        # 403 authorization denial → audit at the gate, then re-raise unchanged.
        _audit_authz_denied(request, bundle, user.user_id)
        raise
    # ProfileUnavailableError (500) / UserStateUnavailableError (503) propagate
    # un-audited: they are a server fault / a transient failure, not a denial.

    request.state.auth_state = auth_state
    return user


async def get_current_user_profile(request: Request) -> UserProfile:
    """
    Profile-body dependency (M8a READ 2).

    Depends on :func:`get_auth_state`, so enforcement has already passed and the
    user is ACTIVE. Reads the profile body over the user-scoped, RLS-respecting
    connection and returns a :class:`UserProfile`. Stashes it on
    ``request.state.profile``. Raises :class:`ProfileUnavailableError` (→ 500) if
    the active user's row is unexpectedly unreadable.
    """
    user = await get_auth_state(request)
    bundle = request.app.state.supabase_auth
    profile = await bundle.profile_reader.fetch_profile(user.user_id)
    request.state.profile = profile
    return profile


async def require_onboarded(request: Request) -> UserProfile:
    """
    Onboarding gate (M8a).

    Depends on :func:`get_current_user_profile` (active user + body). If onboarding
    is not complete, raises :class:`OnboardingRequiredError` (→ 403
    ``ONBOARDING_REQUIRED``) and emits a best-effort ``AUTHZ_DENIED`` audit row.
    Returns the :class:`UserProfile` when onboarded.
    """
    profile = await get_current_user_profile(request)
    if not profile.onboarding_completed:
        bundle = request.app.state.supabase_auth
        _audit_authz_denied(request, bundle, profile.user_id)
        raise OnboardingRequiredError(
            "Onboarding is required.", detail="onboarding_completed is false"
        )
    return profile
