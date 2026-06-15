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
Supabase user-JWT verification pipeline for Phase C (milestone M2).

PURE module: no FastAPI, no DB. It takes a raw JWT string, verifies it against
the JWKS public keys (via an injected ``JwksCache``), validates standard claims,
and returns an immutable ``VerifiedClaims`` (decision M2-D1).

Trust-source rules (review S2), all enforced here:
  - The accepted algorithm set is FIXED by config (asymmetric → {ES256, RS256}).
    The token header's ``alg`` may only SELECT within that set; it can never
    widen it. ``alg: none`` is rejected. This is the core alg-confusion defense.
  - The JWKS URL lives in config (derived from SUPABASE_URL); a forged ``iss``
    cannot redirect key retrieval — issuer is only ever *checked*, never used to
    locate keys.

This module does NOT build ``AuthenticatedUser`` and does NOT interpret
``app_metadata`` / ``user_metadata`` (that, with the untrusted-metadata rule, is
M4). It returns verified standard claims plus the opaque metadata blobs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, FrozenSet, Mapping, Optional

import jwt

from .config import SupabaseAuthConfig
from .exceptions import InvalidTokenError, TokenExpiredError
from .jwks_cache import JwksCache


def _freeze(value: Any) -> Mapping[str, Any]:
    """Return a read-only view of a dict claim; empty mapping if absent/!dict."""
    if isinstance(value, dict):
        return MappingProxyType(dict(value))
    return MappingProxyType({})


@dataclass(frozen=True)
class VerifiedClaims:
    """
    Immutable result of a successful verification (decision M2-D1).

    Carries verified standard claims only. ``app_metadata`` / ``user_metadata``
    are exposed as opaque read-only mappings; M4 (AuthenticatedUser) applies the
    trust rules (user_metadata is untrusted) — M2 makes no trust judgement about
    them. Identity consumers must key on ``sub`` only, never ``email``.
    """

    sub: str
    aud: str
    iss: str
    iat: int
    exp: int
    email: Optional[str] = None
    app_metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    user_metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


class JwtVerifier:
    """
    Verifies Supabase-issued user JWTs. Stateless apart from the JWKS cache it
    holds; safe for concurrent use within one event loop.
    """

    def __init__(
        self,
        config: SupabaseAuthConfig,
        jwks_cache: JwksCache,
        *,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._jwks = jwks_cache
        self._time_fn = time_fn
        self._accepted: FrozenSet[str] = config.accepted_algorithms

    async def verify(self, token: str) -> VerifiedClaims:
        """
        Verify ``token`` and return its claims, or raise a typed auth error.

        Raises:
            TokenExpiredError: signature/claims fine but ``exp`` is past (→ 401
                TOKEN_EXPIRED at M7).
            InvalidTokenError: any other rejection (→ 401 INVALID_TOKEN at M7).
            JwksUnavailableError: keys could not be fetched (→ 503 at M7);
                propagated from the cache.
        """
        if not token or not isinstance(token, str):
            raise InvalidTokenError("Malformed token.", detail="empty/non-str token")

        # 1. Parse the UNVERIFIED header — used only to pick a key and pre-reject.
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(
                "Malformed token.", detail=f"unparseable header: {type(exc).__name__}"
            ) from exc

        alg = header.get("alg")
        kid = header.get("kid")

        # 2. Pre-check alg against the fixed set (decode re-enforces this; S2).
        #    Explicitly catches `alg: none` and any alg outside the set early.
        if alg not in self._accepted:
            raise InvalidTokenError(
                "Token algorithm not accepted.",
                detail=f"alg {alg!r} not in accepted set",
            )

        # 3. A kid is mandatory for Supabase asymmetric tokens.
        if not kid:
            raise InvalidTokenError("Token key id missing.", detail="no kid in header")

        # 4. Resolve the verification key (may refresh JWKS; JwksUnavailableError
        #    propagates unchanged for the M7 503 mapping).
        key = await self._jwks.get_key(kid)

        # 5. Verify signature + standard claims. `algorithms` is the pinning lever.
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(self._accepted),
                audience=self._config.expected_aud,
                issuer=self._config.expected_iss,
                leeway=self._config.jwt_leeway_seconds,
                options={
                    "require": ["exp", "iat", "aud", "iss", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            # The ONE distinction safe to expose to the client.
            raise TokenExpiredError("Token has expired.", detail="exp in past") from exc
        except jwt.PyJWTError as exc:
            # Collapse everything else to the generic bucket (disclosure rule):
            # bad signature, wrong alg/aud/iss, immature (nbf), missing claim, etc.
            raise InvalidTokenError(
                "Token is invalid.", detail=f"{type(exc).__name__}"
            ) from exc

        # 6. Far-future `iat` rejection — PyJWT does not do this (review missing-req).
        iat = claims.get("iat")
        now = self._time_fn()
        if not isinstance(iat, (int, float)) or iat > now + self._config.jwt_leeway_seconds:
            raise InvalidTokenError(
                "Token issue time is invalid.", detail="iat in the future / non-numeric"
            )

        # 7. sub must be present and non-empty (the identity join key).
        sub = claims.get("sub")
        if not sub or not isinstance(sub, str):
            raise InvalidTokenError(
                "Token subject missing.", detail="empty/non-str sub"
            )

        email = claims.get("email")
        return VerifiedClaims(
            sub=sub,
            aud=self._config.expected_aud,
            iss=self._config.expected_iss,
            iat=int(iat),
            exp=int(claims["exp"]),
            email=email if isinstance(email, str) else None,
            app_metadata=_freeze(claims.get("app_metadata")),
            user_metadata=_freeze(claims.get("user_metadata")),
        )
