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
User-facing protected routes for Phase C (milestone M7).

The Supabase user-auth surface, mounted alongside the existing ``/v1`` proxy
routes but on a DISJOINT path namespace (``/auth/*``). These routes are guarded
by :func:`require_supabase_user` (a verified Supabase user JWT), entirely separate
from the ``PROXY_API_KEY`` guard on ``/v1`` — the two auth planes never mix
(plan §1.2/§9; a user JWT never reaches the Kiro API).

Only the TOKEN-ONLY routes are implemented here. Profile-enriched ``/auth/me``,
onboarding, role gates, and any ``403`` (banned/inactive/ONBOARDING_REQUIRED) are
the DEFERRED authorization milestone — no user-state schema or role claim exists
in-repo, so M7 builds none of it (plan §0.0/§12).

S4 revocation-window note (plan §1.4; PhaseC §5): every route here is token-only
(no DB read). It accepts a valid JWT for the remaining lifetime of that token and
CANNOT observe a mid-TTL ban/disable. This is the explicitly-accepted revocation
window (~1h Supabase default). A ban is caught only on the next DB-touch by a
profile-backed endpoint — which is deferred.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from .supabase_auth.audit import AuditEvent
from .supabase_auth.context import get_request_id
from .supabase_auth.dependencies import _client_ip, require_supabase_user
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
