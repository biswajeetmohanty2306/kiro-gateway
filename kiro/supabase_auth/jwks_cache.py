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
JWKS retrieval and key cache for Phase C user-auth (milestones M2 + M3).

PURE module: no FastAPI, no DB. The ``httpx.AsyncClient`` used to fetch the
JWKS is injected via the constructor (decision M2-D5) — in production (M7) this
is the shared client at ``app.state.http_client``; in tests it is a local/mock
client. The module never reaches into app state.

M2 delivered: the positive ``kid -> key`` cache, single-flight async refresh,
rotation refresh on unknown ``kid``, and a positive TTL.

M3 adds (DoS resilience for the unauthenticated surface, review S3):
  - Negative cache (T1): a confirmed-absent ``kid`` is rejected without a network
    call until its negative-TTL expires. Seeded ONLY on an authoritative miss —
    i.e. a ``kid`` still absent after a successful fetch THIS cycle. A
    cooldown-blocked miss is NOT negative-cached, so a legitimately just-rotated
    key is only delayed until the cooldown clears, not for the full negative-TTL.
  - Bounded negative cache (T3): hard LRU cap so a distinct-``kid`` flood cannot
    grow memory without bound.
  - Global refresh cooldown (T2, decision M3-D3): at most one refresh attempt per
    cooldown window per cache/endpoint — GLOBAL, not per ``kid`` (a per-kid
    cooldown would not stop a distinct-kid flood).
  - Stale-serve grace (M3-D4): during a JWKS outage, a known ``kid`` is served
    from the (stale) cache up to a grace window, after which even a known ``kid``
    yields a transient failure.
  - Observability counters (§7.1): refresh attempts/successes/failures, negative-
    cache hits, cooldown-blocked refreshes. Plain monotonic ints, PII-free.

M3 does NOT wire anything into FastAPI; the per-source auth-failure throttle is a
separate pure primitive (``ratelimit.py``) wired at M7.

Outage / 503 strategy (resolution matrix, plan §6):
  - cold cache + cannot fetch              -> JwksUnavailableError (503 at M7)
  - warm known kid, refresh fails/blocked  -> serve stale within grace, else 503
  - warm unknown kid, authoritative miss   -> InvalidTokenError (401) + negative-cache
  - warm unknown kid, cooldown-blocked      -> InvalidTokenError (401), NOT cached (M3-D6)

Security (S2): the fetch URL is supplied by trusted config (derived from
``SUPABASE_URL`` at M0) and is NEVER taken from a token's ``iss``/``jku``.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

import httpx
import jwt

from .config import SupabaseAuthConfig
from .exceptions import InvalidTokenError, JwksUnavailableError


class JwksCache:
    """
    Caches Supabase JWKS public keys by ``kid`` with single-flight refresh,
    negative caching, a global refresh cooldown, and stale-serve grace.

    Not safe to share across event loops, but safe for concurrent use within a
    single asyncio loop (the refresh lock serializes fetches).
    """

    def __init__(
        self,
        jwks_url: str,
        http_client: httpx.AsyncClient,
        *,
        ttl_seconds: int = 600,
        cooldown_seconds: int = 60,
        negative_ttl_seconds: int = 300,
        negative_max_size: int = 1024,
        stale_grace_seconds: int = 3600,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if not jwks_url:
            # Defensive: an asymmetric config must always carry a JWKS URL.
            raise ValueError("jwks_url must be a non-empty URL")
        if negative_max_size < 1:
            raise ValueError("negative_max_size must be >= 1")
        self._jwks_url = jwks_url
        self._http = http_client
        self._ttl = ttl_seconds
        self._cooldown = cooldown_seconds
        self._negative_ttl = negative_ttl_seconds
        self._negative_max_size = negative_max_size
        self._stale_grace = stale_grace_seconds
        self._time_fn = time_fn

        self._keys: Dict[str, Any] = {}        # kid -> crypto public key object
        self._negative: "OrderedDict[str, float]" = OrderedDict()  # kid -> created
        self._last_fetch: Optional[float] = None          # last SUCCESSFUL fetch (TTL/grace)
        self._last_refresh_attempt: Optional[float] = None  # last ATTEMPT (cooldown)
        self._fetch_count: int = 0             # bumped on each successful fetch
        self._lock = asyncio.Lock()

        # -- observability counters (§7.1): monotonic, PII-free ----------------
        self.jwks_refresh_attempts: int = 0
        self.jwks_refresh_successes: int = 0
        self.jwks_refresh_failures: int = 0
        self.negative_cache_hits: int = 0
        self.cooldown_blocked_refreshes: int = 0

    @classmethod
    def from_config(
        cls,
        config: SupabaseAuthConfig,
        http_client: httpx.AsyncClient,
        *,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> "JwksCache":
        """Build a cache from a validated config (asymmetric scheme). For M7 wiring."""
        if not config.jwks_url:
            raise ValueError(
                "config.jwks_url is empty — JWKS cache requires the asymmetric scheme"
            )
        return cls(
            config.jwks_url,
            http_client,
            ttl_seconds=config.jwks_cache_ttl_seconds,
            cooldown_seconds=config.jwks_refresh_cooldown_seconds,
            negative_ttl_seconds=config.jwks_negative_ttl_seconds,
            negative_max_size=config.jwks_negative_cache_max_size,
            stale_grace_seconds=config.jwks_stale_grace_seconds,
            time_fn=time_fn,
        )

    # -- public API ----------------------------------------------------------

    async def get_key(self, kid: str) -> Any:
        """
        Return the public key for ``kid``, applying the M3 resolution matrix.

        Raises:
            JwksUnavailableError: keys cannot be retrieved and no usable cached
                key exists (cold cache, or stale beyond grace) — transient,
                mapped to 503 at M7.
            InvalidTokenError: ``kid`` is not among the current keys (a bad/forged
                token, or a key not yet learned within the cooldown) — mapped to
                generic 401 INVALID_TOKEN at M7.
        """
        # 1. Fresh negative-cache entry → reject with NO network call (T1).
        if self._is_negative_fresh(kid):
            self.negative_cache_hits += 1
            raise InvalidTokenError(
                "Token key not recognized.", detail="kid negative-cached"
            )

        # 2. Positive cache hit and not stale → steady state, no network.
        if kid in self._keys and not self._is_stale():
            return self._keys[kid]

        # 3. A refresh is wanted (stale, or unknown kid). Gate on the GLOBAL
        #    cooldown (T2) BEFORE the single-flight lock (T4 preserved inside).
        gen_before = self._fetch_count
        if self._cooldown_active():
            self.cooldown_blocked_refreshes += 1
        else:
            try:
                await self._refresh_single_flight()
            except JwksUnavailableError:
                # Fetch failed; resolve from current state per the matrix below.
                pass

        # 4. Resolve.
        key = self._keys.get(kid)
        if key is not None:
            # Known kid. Serve even if stale, unless the outage exceeded grace.
            if self._is_stale() and self._beyond_stale_grace():
                raise JwksUnavailableError(
                    "Signing keys are stale and cannot be refreshed.",
                    detail="stale-serve grace exceeded",
                )
            return key

        # kid absent from the positive cache.
        if self._last_fetch is None:
            # Never had a successful fetch → we genuinely cannot verify yet.
            raise JwksUnavailableError(
                "Unable to retrieve signing keys.",
                detail="no keys available (cold cache)",
            )

        # Warm cache, kid absent. Negative-cache ONLY if a fetch actually
        # completed this cycle (authoritative absence). A cooldown-blocked miss
        # is left un-cached so a just-rotated key is delayed only until cooldown
        # clears, not for the full negative-TTL (M3-D6 tradeoff bound).
        if self._fetch_count > gen_before:
            self._add_negative(kid)
        raise InvalidTokenError(
            "Token key not recognized.", detail="kid not present in current key set"
        )

    # -- timing predicates ---------------------------------------------------

    def _is_stale(self) -> bool:
        if self._last_fetch is None:
            return True
        return (self._time_fn() - self._last_fetch) > self._ttl

    def _beyond_stale_grace(self) -> bool:
        if self._last_fetch is None:
            return True
        return (self._time_fn() - self._last_fetch) > self._stale_grace

    def _cooldown_active(self) -> bool:
        if self._last_refresh_attempt is None:
            return False
        return (self._time_fn() - self._last_refresh_attempt) < self._cooldown

    # -- negative cache ------------------------------------------------------

    def _is_negative_fresh(self, kid: str) -> bool:
        created = self._negative.get(kid)
        if created is None:
            return False
        if (self._time_fn() - created) > self._negative_ttl:
            # Stale negative entry → drop it; the kid may now be re-checked.
            del self._negative[kid]
            return False
        self._negative.move_to_end(kid)  # mark recently used (LRU)
        return True

    def _add_negative(self, kid: str) -> None:
        self._negative[kid] = self._time_fn()
        self._negative.move_to_end(kid)
        while len(self._negative) > self._negative_max_size:
            self._negative.popitem(last=False)  # evict least-recently-used (T3)

    # -- refresh -------------------------------------------------------------

    async def _refresh_single_flight(self) -> None:
        """
        Fetch the JWKS at most once across concurrent callers.

        The ``_fetch_count`` generation check collapses a thundering herd (T4):
        the first coroutine through the lock fetches; any coroutine that was
        waiting sees the count advanced and returns without a second fetch.
        """
        gen = self._fetch_count
        async with self._lock:
            if self._fetch_count != gen:
                # Another coroutine refreshed while we waited for the lock.
                return
            await self._fetch_and_store()

    async def _fetch_and_store(self) -> None:
        # Record the attempt (success OR failure) so a failing/under-attack
        # endpoint is not hammered — the cooldown gates the NEXT attempt.
        self.jwks_refresh_attempts += 1
        self._last_refresh_attempt = self._time_fn()

        try:
            response = await self._http.get(self._jwks_url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Network error, timeout, non-2xx, or unparseable JSON body.
            self.jwks_refresh_failures += 1
            raise JwksUnavailableError(
                "Unable to retrieve signing keys.",
                detail=f"JWKS fetch failed for host "
                f"{self._safe_host()}: {type(exc).__name__}",
            ) from exc

        keys = self._parse_jwks(document)
        if not keys:
            self.jwks_refresh_failures += 1
            raise JwksUnavailableError(
                "Signing key set was empty or unparseable.",
                detail=f"no usable keys in JWKS from host {self._safe_host()}",
            )

        self._keys = keys
        self._last_fetch = self._time_fn()
        self._fetch_count += 1
        self.jwks_refresh_successes += 1
        # A rotated-in key supersedes any negative record for that kid (§3.4).
        self._purge_superseded_negatives(keys)

    def _purge_superseded_negatives(self, new_keys: Dict[str, Any]) -> None:
        for kid in list(self._negative.keys()):
            if kid in new_keys:
                del self._negative[kid]

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
