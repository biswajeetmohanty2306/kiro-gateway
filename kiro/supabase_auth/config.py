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
Validated configuration object for Phase C Supabase user-auth (milestone M0).

This module turns the RAW ``SUPABASE_*`` / ``USER_AUTH_*`` values read in
``kiro/config.py`` into a validated, derived, immutable configuration object.

Design notes (from docs/architecture/PhaseCImplementationPlan.md):
  - Built LAZILY via ``get_config()``. Nothing runs at import time, so importing
    this module never affects app startup. The verifier/routes/middleware that
    later consume the config are out of scope for M0.
  - S2 (trust source): the JWKS URL is derived from ``SUPABASE_URL`` ONLY, never
    from a token's ``iss``/``jku``. The accepted-algorithm set is FIXED by the
    configured scheme and cannot be widened by a token header.
  - S5 (CORS): a wildcard origin ("*") is rejected at construction, because the
    user-facing surface is credentialed and a credentialed wildcard is unsafe.
  - Confirmed scheme (D1): the project signs ASYMMETRICALLY (ECC P-256 / ES256
    via JWKS); HS256 exists only as a legacy/previous key. Default: "asymmetric".

Key material and DB connectivity required by LATER milestones (service-role key,
DB URL) are carried on the object but validated by their own subsystems when
those initialize (M4/M5), not here — M0 validates only what the config object
itself needs to be internally coherent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import FrozenSet, Optional, Tuple

from kiro import config as raw

# JWKS endpoint path for Supabase asymmetric projects, appended to SUPABASE_URL.
_JWKS_PATH = "/auth/v1/.well-known/jwks.json"

# Issuer suffix appended to SUPABASE_URL when SUPABASE_EXPECTED_ISS is not set.
_ISS_SUFFIX = "/auth/v1"

# Accepted algorithm sets, FIXED per scheme (S2). A token's header `alg` may only
# select WITHIN the set for its scheme; it can never widen the set.
_ASYMMETRIC_ALGS: FrozenSet[str] = frozenset({"ES256", "RS256"})
_SYMMETRIC_ALGS: FrozenSet[str] = frozenset({"HS256"})

_VALID_SCHEMES = ("asymmetric", "symmetric")


class SupabaseAuthConfigError(RuntimeError):
    """Raised when the Supabase user-auth configuration is missing or invalid."""


@dataclass(frozen=True)
class SupabaseAuthConfig:
    """
    Immutable, validated Phase C user-auth configuration.

    Constructed via :func:`build_config` / :func:`get_config`; do not instantiate
    directly with raw env values (validation lives in the factory).
    """

    # --- Identity / endpoints ---
    supabase_url: str
    project_ref: str
    scheme: str                       # "asymmetric" | "symmetric"
    accepted_algorithms: FrozenSet[str]
    expected_aud: str
    expected_iss: str
    jwks_url: Optional[str]           # set for asymmetric; None for symmetric

    # --- Key material ---
    # Present only in symmetric mode; empty string otherwise.
    jwt_secret: str = field(repr=False, default="")
    # Consumed by later milestones (M5 audit writes); never client-reachable.
    service_role_key: str = field(repr=False, default="")
    # Consumed by later milestones (M4 async DB layer).
    db_url: str = field(repr=False, default="")

    # --- CORS (S5) ---
    cors_allowed_origins: Tuple[str, ...] = ()

    # --- Verification tuning ---
    jwt_leeway_seconds: int = 60

    # --- DoS / throttle knobs (consumed in M3) ---
    jwks_refresh_cooldown_seconds: int = 60
    auth_failure_rate_limit: int = 20


def _parse_origins(raw_value: str) -> Tuple[str, ...]:
    """Split a comma-separated origins string into a clean tuple (order preserved)."""
    origins = []
    for part in raw_value.split(","):
        origin = part.strip()
        if origin and origin not in origins:
            origins.append(origin)
    return tuple(origins)


def _parse_non_negative_int(name: str, raw_value: object) -> int:
    """
    Parse a raw env string into a non-negative int, or raise a clear error.

    Validation lives here (not at import in kiro/config.py) so an invalid
    numeric value fails gracefully and lazily via SupabaseAuthConfigError,
    consistent with the rest of the Phase C config.
    """
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        raise SupabaseAuthConfigError(
            f"{name} must be an integer, got {raw_value!r}."
        )
    if value < 0:
        raise SupabaseAuthConfigError(f"{name} must be >= 0, got {value}.")
    return value


def build_config() -> SupabaseAuthConfig:
    """
    Build and validate the Supabase user-auth config from the raw env values.

    Raises:
        SupabaseAuthConfigError: if required values are missing or inconsistent.

    This is the only place validation/derivation happens. It is intentionally
    NOT called at import time — see :func:`get_config`.
    """
    supabase_url = (raw.SUPABASE_URL or "").strip().rstrip("/")
    if not supabase_url:
        raise SupabaseAuthConfigError(
            "SUPABASE_URL is required for Phase C user-auth but is not set. "
            "Set it in .env (see .env.example, 'PHASE C: SUPABASE USER-AUTH')."
        )

    scheme = (raw.SUPABASE_JWT_ALG_SCHEME or "asymmetric").strip().lower()
    if scheme not in _VALID_SCHEMES:
        raise SupabaseAuthConfigError(
            f"SUPABASE_JWT_ALG_SCHEME must be one of {_VALID_SCHEMES}, got '{scheme}'."
        )

    # Accepted-algorithm set is fixed by scheme (S2) — never derived from a token.
    if scheme == "asymmetric":
        accepted_algorithms = _ASYMMETRIC_ALGS
        jwks_url = f"{supabase_url}{_JWKS_PATH}"   # derived from trusted config ONLY (S2)
        jwt_secret = ""                            # no shared secret in asymmetric mode
    else:  # symmetric
        accepted_algorithms = _SYMMETRIC_ALGS
        jwks_url = None
        jwt_secret = (raw.SUPABASE_JWT_SECRET or "").strip()
        if not jwt_secret:
            raise SupabaseAuthConfigError(
                "SUPABASE_JWT_ALG_SCHEME='symmetric' requires SUPABASE_JWT_SECRET, "
                "but it is empty. (This project is expected to be 'asymmetric'.)"
            )

    # Expected issuer: explicit override, else derived from SUPABASE_URL.
    expected_iss = (raw.SUPABASE_EXPECTED_ISS or "").strip()
    if not expected_iss:
        expected_iss = f"{supabase_url}{_ISS_SUFFIX}"

    expected_aud = (raw.SUPABASE_EXPECTED_AUD or "authenticated").strip()
    if not expected_aud:
        raise SupabaseAuthConfigError("SUPABASE_EXPECTED_AUD must not be empty.")

    # CORS (S5): reject a wildcard outright — the user-facing surface is
    # credentialed, and a credentialed wildcard is an unsafe combination.
    cors_origins = _parse_origins(raw.USER_AUTH_CORS_ALLOWED_ORIGINS or "")
    if "*" in cors_origins:
        raise SupabaseAuthConfigError(
            "USER_AUTH_CORS_ALLOWED_ORIGINS must not contain '*': a credentialed "
            "wildcard CORS policy is forbidden. List exact origins instead."
        )

    leeway = _parse_non_negative_int(
        "USER_AUTH_JWT_LEEWAY_SECONDS", raw.USER_AUTH_JWT_LEEWAY_SECONDS
    )
    cooldown = _parse_non_negative_int(
        "USER_AUTH_JWKS_REFRESH_COOLDOWN_SECONDS",
        raw.USER_AUTH_JWKS_REFRESH_COOLDOWN_SECONDS,
    )
    failure_limit = _parse_non_negative_int(
        "USER_AUTH_AUTH_FAILURE_RATE_LIMIT", raw.USER_AUTH_AUTH_FAILURE_RATE_LIMIT
    )

    return SupabaseAuthConfig(
        supabase_url=supabase_url,
        project_ref=(raw.SUPABASE_PROJECT_REF or "").strip(),
        scheme=scheme,
        accepted_algorithms=accepted_algorithms,
        expected_aud=expected_aud,
        expected_iss=expected_iss,
        jwks_url=jwks_url,
        jwt_secret=jwt_secret,
        service_role_key=(raw.SUPABASE_SERVICE_ROLE_KEY or "").strip(),
        db_url=(raw.SUPABASE_DB_URL or "").strip(),
        cors_allowed_origins=cors_origins,
        jwt_leeway_seconds=leeway,
        jwks_refresh_cooldown_seconds=cooldown,
        auth_failure_rate_limit=failure_limit,
    )


@lru_cache(maxsize=1)
def get_config() -> SupabaseAuthConfig:
    """
    Return the validated config, building it once on first use (lazy singleton).

    Lazy by design: importing this module must not read or validate env, so the
    gateway boots normally even before Phase C is configured. The config is only
    materialized when an auth subsystem (M2+) first asks for it.

    Use :func:`reset_config_cache` in tests after mutating the environment.
    """
    return build_config()


def reset_config_cache() -> None:
    """Clear the cached config (test helper; call after changing env vars)."""
    get_config.cache_clear()
