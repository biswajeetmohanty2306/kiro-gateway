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
JWKS retrieval and key cache for Phase C user-auth (milestone M2).

PURE module: no FastAPI, no DB. The ``httpx.AsyncClient`` used to fetch the
JWKS is injected via the constructor (decision M2-D5) — in production (M7) this
is the shared client at ``app.state.http_client``; in tests it is a local/mock
client. The module never reaches into app state.

What M2 implements:
  - In-memory ``kid -> public key`` cache.
  - Single-flight async refresh guarded by an ``asyncio.Lock`` (mirrors the
    proven pattern in ``kiro/auth.py``): N concurrent misses cause ONE fetch.
  - Rotation refresh: an unknown ``kid`` triggers a single refresh, then re-looks.
  - Positive TTL (decision M2-D2): the JWKS is proactively refetched once its
    age exceeds ``ttl_seconds``, bounding how long a retired key stays usable.

What M2 deliberately does NOT implement (left as a clean seam for M3):
  - Negative-caching of unknown ``kid`` values.
  - Refresh cooldown / debounce against unknown-``kid`` floods (DoS valve).
So in M2, repeated unknown-``kid`` lookups WILL each trigger a refetch. This is
a documented, intentional limitation closed in M3.

Security (S2): the fetch URL is supplied by trusted config (derived from
``SUPABASE_URL`` at M0) and is NEVER taken from a token's ``iss``/``jku``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional

import httpx
import jwt

from .exceptions import InvalidTokenError, JwksUnavailableError


class JwksCache:
    """
    Caches Supabase JWKS public keys by ``kid`` with single-flight refresh.

    Not safe to share across event loops, but safe for concurrent use within a
    single asyncio loop (the refresh lock serializes fetches).
    """

    def __init__(
        self,
        jwks_url: str,
        http_client: httpx.AsyncClient,
        *,
        ttl_seconds: int = 600,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if not jwks_url:
            # Defensive: an asymmetric config must always carry a JWKS URL.
            raise ValueError("jwks_url must be a non-empty URL")
        self._jwks_url = jwks_url
        self._http = http_client
        self._ttl = ttl_seconds
        self._time_fn = time_fn

        self._keys: Dict[str, Any] = {}      # kid -> crypto public key object
        self._last_fetch: Optional[float] = None
        self._fetch_count: int = 0           # bumped on each successful fetch
        self._lock = asyncio.Lock()

    # -- public API ----------------------------------------------------------

    async def get_key(self, kid: str) -> Any:
        """
        Return the public key for ``kid``, refreshing the JWKS if the cache is
        stale (TTL) or the ``kid`` is unknown (rotation).

        Raises:
            JwksUnavailableError: the JWKS could not be retrieved AND no usable
                cached key for ``kid`` exists (transient dependency failure → 503
                at M7).
            InvalidTokenError: the ``kid`` is genuinely absent after a successful
                refresh (→ generic 401 INVALID_TOKEN at M7).
        """
        if self._is_stale() or kid not in self._keys:
            try:
                await self._refresh_single_flight()
            except JwksUnavailableError:
                # Resilience: if a (merely stale) refresh fails transiently but
                # we still hold the requested key, serve it rather than failing.
                if kid in self._keys:
                    return self._keys[kid]
                raise

        key = self._keys.get(kid)
        if key is None:
            # Known endpoint reachable, but no such kid — a real bad/forged token.
            raise InvalidTokenError(
                "Token key not recognized.",
                detail=f"kid not found after refresh (kid={kid!r})",
            )
        return key

    # -- internals -----------------------------------------------------------

    def _is_stale(self) -> bool:
        if self._last_fetch is None:
            return True
        return (self._time_fn() - self._last_fetch) > self._ttl

    async def _refresh_single_flight(self) -> None:
        """
        Fetch the JWKS at most once across concurrent callers.

        The ``_fetch_count`` generation check collapses a thundering herd: the
        first coroutine through the lock fetches; any coroutine that was waiting
        sees the count advanced and returns without a second fetch.
        """
        gen = self._fetch_count
        async with self._lock:
            if self._fetch_count != gen:
                # Another coroutine refreshed while we waited for the lock.
                return
            await self._fetch_and_store()

    async def _fetch_and_store(self) -> None:
        try:
            response = await self._http.get(self._jwks_url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Network error, timeout, non-2xx, or unparseable JSON body.
            raise JwksUnavailableError(
                "Unable to retrieve signing keys.",
                detail=f"JWKS fetch failed for host "
                f"{self._safe_host()}: {type(exc).__name__}",
            ) from exc

        keys = self._parse_jwks(document)
        if not keys:
            raise JwksUnavailableError(
                "Signing key set was empty or unparseable.",
                detail=f"no usable keys in JWKS from host {self._safe_host()}",
            )

        self._keys = keys
        self._last_fetch = self._time_fn()
        self._fetch_count += 1

    @staticmethod
    def _parse_jwks(document: Any) -> Dict[str, Any]:
        """Parse a JWKS document into a ``kid -> public key`` mapping."""
        keys: Dict[str, Any] = {}
        if not isinstance(document, dict):
            return keys
        for entry in document.get("keys", []) or []:
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            if not kid:
                continue
            try:
                # PyJWK builds the underlying crypto key from the JWK dict.
                parsed = jwt.PyJWK.from_dict(entry)
            except Exception:
                # Skip individual malformed/unsupported entries; a usable key
                # for the requested kid may still be present.
                continue
            keys[kid] = parsed.key
        return keys

    def _safe_host(self) -> str:
        """Host of the JWKS URL for logs — never includes a token or query."""
        try:
            return httpx.URL(self._jwks_url).host or "<unknown>"
        except Exception:
            return "<unknown>"
