# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C JWKS cache (kiro/supabase_auth/jwks_cache.py).

M2 coverage: rotation refresh on unknown kid, single-flight under concurrency,
zero-network steady state, TTL-driven proactive refetch, unknown-kid handling,
transient fetch-failure isolation (JwksUnavailableError).

M3 coverage: negative cache (no refetch for repeated bad kid; TTL expiry; LRU
bound; rotation invalidation), global refresh cooldown (distinct-kid flood
bounded; failing endpoint not hammered; single-flight preserved), the outage/503
resolution matrix, and the observability counters.

The test helper defaults cooldown to 0 (no gating) so M2-style tests are
unaffected; cooldown-specific tests set it explicitly with an injected clock.
"""

import asyncio

import pytest

from kiro.supabase_auth.jwks_cache import JwksCache
from kiro.supabase_auth.exceptions import InvalidTokenError, JwksUnavailableError

from _supabase_jwt_helpers import ECKey, FakeHttpClient, JWKS_URL


def make_cache(
    client,
    *,
    ttl=600,
    cooldown=0,
    negative_ttl=300,
    negative_max_size=1024,
    stale_grace=3600,
    time_fn=None,
):
    kwargs = {
        "ttl_seconds": ttl,
        "cooldown_seconds": cooldown,
        "negative_ttl_seconds": negative_ttl,
        "negative_max_size": negative_max_size,
        "stale_grace_seconds": stale_grace,
    }
    if time_fn is not None:
        kwargs["time_fn"] = time_fn
    return JwksCache(JWKS_URL, client, **kwargs)


class TestRotationAndLookup:
    @pytest.mark.asyncio
    async def test_first_lookup_fetches_once(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        key = await cache.get_key("kid-1")
        assert key is not None
        assert client.fetch_count == 1

    @pytest.mark.asyncio
    async def test_steady_state_zero_network(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        await cache.get_key("kid-1")
        await cache.get_key("kid-1")
        await cache.get_key("kid-1")
        assert client.fetch_count == 1  # only the first lookup hit the network

    @pytest.mark.asyncio
    async def test_unknown_kid_triggers_refresh_then_resolves(self):
        """Rotation: a newly added kid is picked up by the refresh (no cooldown)."""
        k1 = ECKey("kid-1")
        k2 = ECKey("kid-2")
        client = FakeHttpClient()
        client.set_keys(k1)
        cache = make_cache(client)  # cooldown=0 → rotation refetch is immediate

        await cache.get_key("kid-1")
        assert client.fetch_count == 1

        client.set_keys(k1, k2)  # key rotated in
        key2 = await cache.get_key("kid-2")
        assert key2 is not None
        assert client.fetch_count == 2

    @pytest.mark.asyncio
    async def test_fetch_url_is_config_derived(self):
        """S2: the cache only ever fetches the configured JWKS URL."""
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        await cache.get_key("kid-1")
        assert client.last_url == JWKS_URL


class TestSingleFlight:
    @pytest.mark.asyncio
    async def test_concurrent_misses_fetch_once(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        results = await asyncio.gather(*[cache.get_key("kid-1") for _ in range(10)])
        assert all(r is not None for r in results)
        assert client.fetch_count == 1  # single-flight collapsed the herd


class TestTtl:
    @pytest.mark.asyncio
    async def test_ttl_triggers_proactive_refetch(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)

        clock = {"t": 1000.0}
        cache = make_cache(client, ttl=600, time_fn=lambda: clock["t"])

        await cache.get_key("kid-1")
        assert client.fetch_count == 1

        clock["t"] += 100  # within TTL
        await cache.get_key("kid-1")
        assert client.fetch_count == 1

        clock["t"] += 600  # now beyond TTL (700 > 600)
        await cache.get_key("kid-1")
        assert client.fetch_count == 2


class TestUnknownAndFailures:
    @pytest.mark.asyncio
    async def test_unknown_kid_after_refresh_is_invalid_token(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        with pytest.raises(InvalidTokenError):
            await cache.get_key("does-not-exist")

    @pytest.mark.asyncio
    async def test_m3_repeated_unknown_kid_is_negative_cached(self):
        """
        M3 (inverts the old M2 limitation): after the first authoritative miss,
        repeated lookups of the same unknown kid are rejected from the negative
        cache with NO further network calls.
        """
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)  # cooldown=0; negative cache still applies

        for _ in range(5):
            with pytest.raises(InvalidTokenError):
                await cache.get_key("nope")
        assert client.fetch_count == 1          # only the first miss fetched
        assert cache.negative_cache_hits == 4   # the subsequent 4 were cached

    @pytest.mark.asyncio
    async def test_network_error_is_jwks_unavailable(self):
        import httpx
        client = FakeHttpClient()
        client.set_error(httpx.ConnectError("boom"))
        cache = make_cache(client)

        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_non_200_is_jwks_unavailable(self):
        client = FakeHttpClient()
        client.set_status(503)
        cache = make_cache(client)

        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_empty_jwks_is_unavailable(self):
        client = FakeHttpClient()
        client.set_raw_document({"keys": []})
        cache = make_cache(client)

        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_malformed_document_is_unavailable(self):
        client = FakeHttpClient()
        client.set_raw_document({"not_keys": "garbage"})
        cache = make_cache(client)

        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_stale_refresh_failure_serves_cached_key(self):
        """If a TTL refresh fails transiently but we hold the kid, serve it."""
        import httpx
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        cache = make_cache(client, ttl=100, time_fn=lambda: clock["t"])

        await cache.get_key("kid-1")
        assert client.fetch_count == 1

        client.set_error(httpx.ConnectError("down"))
        clock["t"] += 200  # force staleness

        key = await cache.get_key("kid-1")  # refresh fails, cached key still usable
        assert key is not None


class TestNegativeCache:
    @pytest.mark.asyncio
    async def test_negative_entry_expires_then_rechecks(self):
        """After the negative TTL, an unknown kid is re-checked (one new fetch)."""
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        # cooldown small so the re-check is not cooldown-blocked after TTL.
        cache = make_cache(
            client, cooldown=60, negative_ttl=300, time_fn=lambda: clock["t"]
        )

        with pytest.raises(InvalidTokenError):
            await cache.get_key("nope")
        assert client.fetch_count == 1

        # Within negative TTL → served from negative cache, no fetch.
        with pytest.raises(InvalidTokenError):
            await cache.get_key("nope")
        assert client.fetch_count == 1

        clock["t"] += 301  # negative entry expired (and cooldown long elapsed)
        with pytest.raises(InvalidTokenError):
            await cache.get_key("nope")
        assert client.fetch_count == 2  # re-checked

    @pytest.mark.asyncio
    async def test_negative_cache_lru_bounded(self):
        """The negative cache never exceeds its max size (T3)."""
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client, negative_max_size=3)

        for i in range(10):
            with pytest.raises(InvalidTokenError):
                await cache.get_key(f"bad-{i}")
        assert len(cache._negative) == 3  # bounded by LRU eviction

    @pytest.mark.asyncio
    async def test_rotation_invalidates_negative_entry(self):
        """A kid that was negative-cached, then rotated in, resolves to a key."""
        k1 = ECKey("kid-1")
        k2 = ECKey("kid-2")
        client = FakeHttpClient()
        client.set_keys(k1)
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        await cache.get_key("kid-1")
        with pytest.raises(InvalidTokenError):
            await cache.get_key("kid-2")  # negative-cached now

        client.set_keys(k1, k2)  # rotated in
        clock["t"] += 61         # clear cooldown so a refresh is allowed
        key2 = await cache.get_key("kid-2")
        assert key2 is not None
        assert "kid-2" not in cache._negative  # negative entry purged


class TestCooldown:
    @pytest.mark.asyncio
    async def test_distinct_kid_flood_is_network_bounded(self):
        """A flood of DISTINCT unknown kids triggers at most one refresh/window."""
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        for i in range(50):
            with pytest.raises(InvalidTokenError):
                await cache.get_key(f"flood-{i}")
        assert client.fetch_count == 1                  # cooldown bounded it
        assert cache.cooldown_blocked_refreshes == 49

    @pytest.mark.asyncio
    async def test_cooldown_elapses_allows_one_more_refresh(self):
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        with pytest.raises(InvalidTokenError):
            await cache.get_key("a")
        assert client.fetch_count == 1

        clock["t"] += 61
        with pytest.raises(InvalidTokenError):
            await cache.get_key("b")
        assert client.fetch_count == 2

    @pytest.mark.asyncio
    async def test_failing_endpoint_not_hammered(self):
        import httpx
        client = FakeHttpClient()
        client.set_error(httpx.ConnectError("down"))
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        # Cold cache + outage → 503; cooldown then suppresses further attempts.
        for _ in range(10):
            with pytest.raises(JwksUnavailableError):
                await cache.get_key("kid-1")
        assert client.fetch_count == 1

    @pytest.mark.asyncio
    async def test_single_flight_preserved_with_cooldown(self):
        """T4 still holds with the cooldown gate in front of the lock."""
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client, cooldown=60)

        results = await asyncio.gather(*[cache.get_key("kid-1") for _ in range(10)])
        assert all(r is not None for r in results)
        assert client.fetch_count == 1

    @pytest.mark.asyncio
    async def test_warm_cache_unknown_kid_cooldown_blocked_is_invalid_token(self):
        """
        M3-D6: warm cache (recent success) + unknown kid + cooldown active →
        InvalidTokenError (401), NOT 503, and NOT negative-cached (so a just-
        rotated key recovers once the cooldown clears).
        """
        k1 = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k1)
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        await cache.get_key("kid-1")  # warm + sets last_refresh_attempt
        assert client.fetch_count == 1

        with pytest.raises(InvalidTokenError):
            await cache.get_key("kid-2")  # cooldown active → blocked
        assert client.fetch_count == 1
        assert cache.cooldown_blocked_refreshes == 1
        assert "kid-2" not in cache._negative  # NOT negative-cached (M3-D6)


class TestOutageMatrix:
    @pytest.mark.asyncio
    async def test_cold_outage_is_503(self):
        import httpx
        client = FakeHttpClient()
        client.set_error(httpx.ConnectError("down"))
        cache = make_cache(client)

        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_warm_known_kid_served_within_grace_then_503(self):
        import httpx
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        cache = make_cache(
            client, ttl=100, cooldown=0, stale_grace=1000, time_fn=lambda: clock["t"]
        )

        await cache.get_key("kid-1")
        client.set_error(httpx.ConnectError("down"))

        clock["t"] += 200  # stale (>100) but within grace (<1000)
        assert await cache.get_key("kid-1") is not None

        clock["t"] += 1000  # now beyond grace
        with pytest.raises(JwksUnavailableError):
            await cache.get_key("kid-1")


class TestCounters:
    @pytest.mark.asyncio
    async def test_counter_invariant_and_values(self):
        import httpx
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        clock = {"t": 0.0}
        cache = make_cache(client, cooldown=60, time_fn=lambda: clock["t"])

        await cache.get_key("kid-1")                 # 1 attempt, 1 success
        with pytest.raises(InvalidTokenError):
            await cache.get_key("kid-1-bad")         # cooldown-blocked
        clock["t"] += 61
        client.set_error(httpx.ConnectError("down"))
        with pytest.raises(InvalidTokenError):
            await cache.get_key("kid-2")             # attempt fails, warm → 401

        assert cache.jwks_refresh_attempts == 2
        assert cache.jwks_refresh_successes == 1
        assert cache.jwks_refresh_failures == 1
        assert cache.cooldown_blocked_refreshes == 1
        # invariant
        assert (
            cache.jwks_refresh_attempts
            == cache.jwks_refresh_successes + cache.jwks_refresh_failures
        )
