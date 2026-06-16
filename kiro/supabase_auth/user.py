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
AuthenticatedUser identity object for Phase C (milestone M4).

PURE module: no FastAPI, no database, no network — zero I/O (design §6). It maps
an already-verified ``VerifiedClaims`` (produced by M2) into an immutable,
``sub``-keyed ``AuthenticatedUser`` that downstream code can carry.

Scope boundary (design §1, §5): M4 establishes *who the request is* and nothing
more. It makes NO authorization decision — it resolves no roles, looks up no
account state, and bans/disables no one. The repository defines neither a
user-state schema nor a role-claim convention (design §0.1), so M4 must not
invent either. Role resolution and user-state enforcement are DEFERRED to a
future authorization milestone.

Metadata rule (design §4, CM-4): ``app_metadata`` and ``user_metadata`` are
carried through as OPAQUE, read-only mappings. This module never indexes into
them, never extracts a role, never derives state — it interprets neither.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .exceptions import SupabaseAuthError
from .verifier import VerifiedClaims


class InvalidIdentityError(SupabaseAuthError):
    """
    A verified-claims → identity mapping invariant was broken.

    The single error type M4 introduces (design §7). In practice this means a
    ``sub`` that is empty or not a string reached the mapper — which M2 already
    guards against, so this is a belt-and-braces check for any non-M2 caller.
    Like its ``SupabaseAuthError`` base, it carries a short, secret-free
    ``detail`` for server logs (never the token, claim values, or email) and
    performs NO HTTP mapping — that is M7's job. Maps (advisory) to 401 /
    ``INVALID_TOKEN`` at M7.
    """


def _freeze(value: Any) -> Mapping[str, Any]:
    """Return a read-only view of a dict; empty read-only mapping otherwise.

    Mirrors the verifier's ``_freeze`` so the identity object is immutable
    regardless of whether the metadata arrived as a live ``MappingProxyType``
    (the M2 path) or a plain dict (a defensive non-M2 path).
    """
    if isinstance(value, dict):
        return MappingProxyType(dict(value))
    if isinstance(value, MappingProxyType):
        return value
    return MappingProxyType({})


@dataclass(frozen=True)
class AuthenticatedUser:
    """
    Immutable, ``sub``-keyed identity for an authenticated request (M4).

    Identity ONLY. Carries no roles and no account state by design (design §2.1)
    — M4 makes no authorization decision. Never carries the raw JWT, signature,
    or any key material (disclosure discipline, mirroring ``SupabaseAuthError``).

    ``app_metadata`` / ``user_metadata`` are exposed as OPAQUE read-only
    mappings: present for a future milestone (or logging/UX) but uninterpreted
    here. Identity consumers must key on ``user_id`` only, never ``email``.
    """

    # --- Trusted identity (from M2's cryptographically-verified claims) ---
    user_id: str                       # := VerifiedClaims.sub; the only join key
    email: Optional[str] = None        # informational only; never a key/authz input

    # --- Token freshness bounds (trusted; for freshness reasoning only) ---
    claims_issued_at: int = 0          # := VerifiedClaims.iat
    claims_expires_at: int = 0         # := VerifiedClaims.exp

    # --- Opaque, read-only, uninterpreted metadata (carried through as-is) ---
    app_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    user_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )


def build_authenticated_user(claims: VerifiedClaims) -> AuthenticatedUser:
    """
    Map verified claims to an ``AuthenticatedUser`` (design §3, CM-1…CM-5).

    Total, deterministic, and I/O-free: the same ``VerifiedClaims`` always yields
    an equal ``AuthenticatedUser``, with no clock, network, or DB read. This is
    the SINGLE construction path for the identity object (design §2.3); the
    object is never instantiated ad hoc elsewhere.

    Args:
        claims: a successful M2 verification result.

    Returns:
        The immutable identity object.

    Raises:
        InvalidIdentityError: ``sub`` is empty or not a string (CM-1). This is
            the ONLY error M4 raises — it makes no authorization decision and
            never raises a ban/inactive/state error (no such types exist in M4).
    """
    # CM-1: sub is the sole identity key; re-assert M2's guarantee defensively.
    sub = claims.sub
    if not sub or not isinstance(sub, str):
        raise InvalidIdentityError(
            "Identity subject missing.", detail="empty/non-str sub"
        )

    # CM-2: email is informational; keep it only if it is a string, else None.
    #       Never normalized, never trusted, never used as a key.
    email = claims.email if isinstance(claims.email, str) else None

    return AuthenticatedUser(
        user_id=sub,
        email=email,
        # CM-3: freshness bounds copied through unchanged.
        claims_issued_at=int(claims.iat),
        claims_expires_at=int(claims.exp),
        # CM-4: metadata carried through OPAQUE — not indexed, not interpreted.
        app_metadata=_freeze(claims.app_metadata),
        user_metadata=_freeze(claims.user_metadata),
    )
