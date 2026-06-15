# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C JWKS cache (kiro/supabase_auth/jwks_cache.py, M2).

Covers: rotation refresh on unknown kid, single-flight under concurrency,
zero-network steady state, TTL-driven proactive refetch, unknown-kid-after-
refresh, and transient fetch-failure isolation (JwksUnavailableError).

M2 does NOT implement negative-cache / cooldown (M3) — a test documents that a
repeated unknown kid DOES refetch in M2 (the opposite is asserted at M3).
"""

import asyncio

import pytest

from kiro.supabase_auth.jwks_cache import JwksCache
from kiro.supabase_auth.exceptions import InvalidTokenError, JwksUnavailableError

from _supabase_jwt_helpers import ECKey, FakeHttpClient, JWKS_URL


def make_cache(client, *, ttl=600, time_fn=None):
    kwargs = {"ttl_seconds": ttl}
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
        """Rotation: a newly added kid is picked up by the refresh."""
        k1 = ECKey("kid-1")
        k2 = ECKey("kid-2")
        client = FakeHttpClient()
        client.set_keys(k1)
        cache = make_cache(client)

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
    async def test_m2_repeated_unknown_kid_refetches(self):
        """
        Documents the M2 limitation: with no negative-cache (M3), each unknown
        kid lookup triggers another fetch. M3 will assert the opposite.
        """
        k = ECKey("kid-1")
        client = FakeHttpClient()
        client.set_keys(k)
        cache = make_cache(client)

        for _ in range(3):
            with pytest.raises(InvalidTokenError):
                await cache.get_key("nope")
        assert client.fetch_count == 3

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
