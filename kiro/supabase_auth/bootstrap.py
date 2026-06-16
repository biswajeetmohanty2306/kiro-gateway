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
Guarded eager construction of the Phase C user-auth stack (milestone M6).

``build_supabase_auth()`` is called once from the FastAPI lifespan. It wires
the implemented Phase C units (M0 config, M2 verifier, M3 JWKS cache + rate
limiter, M5 audit logger) into a single immutable bundle stored on
``app.state.supabase_auth``.

Activation signal (M6-D8, resolved): Phase C is ACTIVE when ``get_config()``
succeeds. If config is absent/invalid (``SupabaseAuthConfigError``) the builder
returns ``None`` — the app boots normally with all user-auth wiring dormant, so
deployments that do not use Supabase are unaffected.

Eager + fail-fast (design §8): process-wide singletons (cache, limiter) are
built at startup so the first request does not race to construct them. A
present-but-malformed config fails startup fast (the exception propagates),
matching the existing CORS fail-fast posture. A *transient* JWKS outage does
NOT happen here — fetches are lazy (M3), so boot never depends on Supabase
availability.

JWKS HTTP client (M6-D2, resolved): a DEDICATED short-timeout ``httpx`` client,
NOT the app's streaming client (whose 300s read timeout is wrong for a key
fetch that should fast-fail).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx
from loguru import logger

from .audit import AuditLogger
from .config import SupabaseAuthConfig, SupabaseAuthConfigError, get_config
from .db import build_audit_pool
from .jwks_cache import JwksCache
from .ratelimit import FixedWindowRateLimiter
from .verifier import JwtVerifier

# Rate-limiter window for the auth-failure throttle (M3). The config carries the
# COUNT (``auth_failure_rate_limit``) but no window, so the window is a wiring
# constant here: failures-per-minute.
AUTH_FAILURE_WINDOW_SECONDS: float = 60.0

# Dedicated JWKS client timeouts (M6-D2): fast-fail, never the streaming client's
# long read timeout. A key fetch that cannot complete quickly should error so M3
# can serve stale / negative-cache rather than hang the request.
_JWKS_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


@dataclass(frozen=True)
class SupabaseAuthBundle:
    """
    The wired Phase C components, hung on ``app.state.supabase_auth``.

    A single container so "is Phase C active?" is one ``is not None`` check and
    lifespan teardown has one ``aclose()`` to call. ``_jwks_client`` and
    ``_audit_pool`` are retained only so teardown can close them.
    """

    config: SupabaseAuthConfig
    jwks_cache: JwksCache
    verifier: JwtVerifier
    rate_limiter: FixedWindowRateLimiter
    audit_logger: AuditLogger
    _jwks_client: httpx.AsyncClient
    _audit_pool: Optional[Any] = None  # AuditConnectionPool | None

    async def aclose(self) -> None:
        """Close owned resources (JWKS client, audit pool). Best-effort."""
        try:
            await self._jwks_client.aclose()
        except Exception as exc:  # noqa: BLE001 — teardown must not raise.
            logger.warning("JWKS client close failed: {}", type(exc).__name__)
        if self._audit_pool is not None:
            await self._audit_pool.close()


async def build_supabase_auth(
    *,
    config_loader: Callable[[], SupabaseAuthConfig] = get_config,
    jwks_client: Optional[httpx.AsyncClient] = None,
    audit_pool_builder: Callable[..., Awaitable[Any]] = build_audit_pool,
) -> Optional[SupabaseAuthBundle]:
    """
    Build the Phase C bundle, or ``None`` if Supabase user-auth is not configured.

    Args:
        config_loader: returns the validated config (default: M0 ``get_config``).
            Injectable for tests.
        jwks_client: an ``httpx.AsyncClient`` to use for JWKS fetches. Default
            ``None`` builds a dedicated short-timeout client (M6-D2). Injectable
            for tests (a fake client avoids real network).
        audit_pool_builder: async ``(db_url, ...) -> acquirer | None``
            (default: M6 ``build_audit_pool``). Injectable for tests.

    Returns:
        A :class:`SupabaseAuthBundle` when configured, else ``None`` (dormant).

    Raises:
        Any non-config error during construction (e.g. a DB-pool connection
        failure when ``db_url`` is set) propagates to fail startup fast. A
        missing/invalid config does NOT raise — it returns ``None``.
    """
    # 1. Activation guard (M6-D8): config success == Phase C active.
    try:
        config = config_loader()
    except SupabaseAuthConfigError as exc:
        logger.info(
            "Phase C user-auth: not configured, skipping wiring ({})",
            type(exc).__name__,
        )
        return None

    # 2. The M2 verifier resolves keys via JWKS; an asymmetric config carries a
    #    jwks_url. Without one (symmetric scheme), the M2 verifier has no key
    #    path — Phase C stays dormant rather than build a broken verifier.
    if not config.jwks_url:
        logger.warning(
            "Phase C user-auth: scheme '{}' has no JWKS URL; user-auth dormant "
            "(M6 wires the asymmetric/JWKS path only).",
            config.scheme,
        )
        return None

    # 3. Dedicated short-timeout JWKS client (M6-D2), unless one is injected.
    owns_client = jwks_client is None
    client = jwks_client if jwks_client is not None else httpx.AsyncClient(
        timeout=_JWKS_TIMEOUT, follow_redirects=True
    )

    try:
        # 4. Eager singletons (fail-fast).
        jwks_cache = JwksCache.from_config(config, client)
        verifier = JwtVerifier(config, jwks_cache)
        rate_limiter = FixedWindowRateLimiter(
            config.auth_failure_rate_limit, AUTH_FAILURE_WINDOW_SECONDS
        )

        # 5. Audit: DB-backed when db_url is set, else dormant (AuditLogger(None)).
        audit_pool = await audit_pool_builder(config.db_url)
        audit_logger = AuditLogger(audit_pool)
    except Exception:
        # Construction failed (e.g. DB pool connect error). Close the client we
        # created so a failed boot does not leak a connection, then re-raise to
        # fail startup fast.
        if owns_client:
            await client.aclose()
        raise

    logger.info(
        "Phase C user-auth wired (scheme={}, audit={}).",
        config.scheme,
        "db" if audit_pool is not None else "dormant",
    )
    return SupabaseAuthBundle(
        config=config,
        jwks_cache=jwks_cache,
        verifier=verifier,
        rate_limiter=rate_limiter,
        audit_logger=audit_logger,
        _jwks_client=client,
        _audit_pool=audit_pool,
    )
