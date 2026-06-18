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
User-facing protected routes for Phase C (milestones M7 + M8a).

The Supabase user-auth surface, mounted alongside the existing ``/v1`` proxy
routes but on a DISJOINT path namespace (``/auth/*``). These routes are guarded
by Supabase user-JWT dependencies, entirely separate from the ``PROXY_API_KEY``
guard on ``/v1`` — the two auth planes never mix (plan §1.2/§9; a user JWT never
reaches the Kiro API).

Routes by enforcement layer:
  - ``GET  /auth/me``        — token-only (M7): identity echo, no DB read.
  - ``POST /auth/logout``    — token-only (M7): audit-only logout, 204.
  - ``GET  /auth/profile``   — profile-backed (M8a): runs the authoritative state
        gate then the user-scoped body read. This is where a deleted/banned user
        is caught (403 ACCOUNT_DISABLED) — the S1 enforcement surface.
  - ``POST /auth/onboarding``— state-gated (M8a): requires an ACTIVE user (NOT
        ``require_onboarded`` — you must reach it while un-onboarded, PhaseC §6.2);
        atomic conditional transition, idempotent, best-effort audit.

S4 revocation-window note (PhaseC §5): ``/auth/me`` and ``/auth/logout`` are
token-only — they accept a valid JWT for its remaining lifetime and CANNOT observe
a mid-TTL ban/disable. The profile-backed routes (``/auth/profile``,
``/auth/onboarding``) run the DB-sourced state gate and ARE the enforcement point.
Roles / ``require_role`` remain deferred (M8b — no RBAC design exists).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from .supabase_auth.audit import AuditEvent
from .supabase_auth.context import get_request_id
from .supabase_auth.dependencies import (
    _client_ip,
    get_auth_state,
    get_current_user_profile,
    require_supabase_user,
)
from .supabase_auth.onboarding import complete_onboarding
from .supabase_auth.profile import UserProfile
from .supabase_auth.user import AuthenticatedUser

router = APIRouter(tags=["User Auth"])


@router.get("/auth/me")
async def auth_me(
    user: AuthenticatedUser = Depends(require_supabase_user),
) -> dict:
    """
    Return the authenticated user's identity (token-only; no DB).

    Echoes ONLY the trusted, non-sensitive identity fields: ``user_id`` (the
    Supabase ``sub`` — the sole join key), informational ``email``, and the token
    freshness bounds. It deliberately does NOT return the raw token, and does NOT
    expose the opaque ``app_metadata`` / ``user_metadata`` blobs (identity
    consumers key on ``user_id`` only — M4).

    S4: token-only, so a mid-TTL ban is not visible here (see module docstring).
    """
    return {
        "user_id": user.user_id,
        "email": user.email,
        "claims_issued_at": user.claims_issued_at,
        "claims_expires_at": user.claims_expires_at,
    }


@router.post("/auth/logout", status_code=204)
async def auth_logout(
    request: Request,
    user: AuthenticatedUser = Depends(require_supabase_user),
) -> Response:
    """
    Record a logout event and return ``204 No Content`` (audit-only posture).

    The backend takes NO server-side token action: token revocation is the
    client's responsibility (it discards its refresh token against Supabase). This
    endpoint exists so the security record reflects the logout — it writes one
    best-effort ``AuditEvent.LOGOUT`` row (PhaseC line 205; M5 §3.1) and returns.

    The audit write is fire-and-forget and never blocks or fails the response
    (M5 best-effort guarantee). The bundle is guaranteed present because
    ``require_supabase_user`` pre-empts a dormant backend before this runs.
    """
    bundle = getattr(request.app.state, "supabase_auth", None)
    if bundle is not None:
        bundle.audit_logger.record(
            AuditEvent.LOGOUT,
            user_id=user.user_id,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=get_request_id(),
        )
    return Response(status_code=204)


@router.get("/auth/profile")
async def auth_profile(
    profile: UserProfile = Depends(get_current_user_profile),
) -> dict:
    """
    Return the authenticated, ACTIVE user's profile body (M8a — profile-backed).

    Enforcement happens in the dependency chain: ``get_current_user_profile`` runs
    the authoritative state gate (``get_auth_state``) first, so a deleted/banned
    user is rejected with ``403 ACCOUNT_DISABLED`` BEFORE this handler runs — this
    is the S1 enforcement surface. Only ACTIVE users reach here.

    Returns the display fields + onboarding flag. Never the raw token, never the
    authorization-state internals (``deleted_at``/``banned_until`` are not exposed).
    """
    return {
        "user_id": profile.user_id,
        "email": profile.email,
        "name": profile.name,
        "gender": profile.gender,
        "birth_date": profile.birth_date.isoformat()
        if profile.birth_date is not None and hasattr(profile.birth_date, "isoformat")
        else profile.birth_date,
        "country": profile.country,
        "onboarding_completed": profile.onboarding_completed,
    }


@router.post("/auth/onboarding")
async def auth_onboarding(
    request: Request,
    user: AuthenticatedUser = Depends(get_auth_state),
) -> dict:
    """
    Complete onboarding for the authenticated, ACTIVE user (M8a).

    Depends on ``get_auth_state`` (must be ACTIVE) — deliberately NOT
    ``require_onboarded``, because an un-onboarded user must be able to reach this
    route to onboard (PhaseC §6.2). Performs the atomic conditional ``false→true``
    transition (A3); a re-submit when already onboarded is a benign idempotent
    no-op returning ``200`` with current state (D8), NOT a 409.

    On a real ``false→true`` transition, emits one best-effort
    ``AuditEvent.ONBOARDING_COMPLETED`` row (NOT on an idempotent no-op) — the audit
    is fire-and-forget, OUTSIDE the DB transition, so a failed audit never rolls
    back a completed onboarding (M5 §6).
    """
    bundle = request.app.state.supabase_auth  # non-None: get_auth_state authenticated
    # The privileged acquirer (the same pool the readers use). The onboarding
    # transition runs as the 'authenticated' role inside its own transaction so
    # users_update_own RLS applies (see onboarding.py).
    result = await complete_onboarding(bundle._audit_pool, user.user_id)

    if result.transitioned:
        bundle.audit_logger.record(
            AuditEvent.ONBOARDING_COMPLETED,
            user_id=user.user_id,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=get_request_id(),
        )

    return {"onboarding_completed": result.onboarding_completed}
