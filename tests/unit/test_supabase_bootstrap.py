# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C bundle builder
(kiro/supabase_auth/bootstrap.py, M6).

Everything is injected (config loader, JWKS httpx client, audit-pool builder) so
no network, no DB, no asyncpg. Verifies: dormant when unconfigured, dormant for
the symmetric/no-JWKS scheme, eager bundle when configured, audit dormant vs
db-backed by db_url, fail-fast with client cleanup on construction error, and
teardown.
"""

import httpx
import pytest

from kiro.supabase_auth import bootstrap
from kiro.supabase_auth.bootstrap import (
    build_supabase_auth,
    SupabaseAuthBundle,
    AUTH_FAILURE_WINDOW_SECONDS,
)
from kiro.supabase_auth.config import SupabaseAuthConfigError
from kiro.supabase_auth.verifier import JwtVerifier
from kiro.supabase_auth.jwks_cache import JwksCache
from kiro.supabase_auth.ratelimit import FixedWindowRateLimiter
from kiro.supabase_auth.audit import AuditLogger


class FakeConfig:
    """Stand-in for SupabaseAuthConfig with the fields bootstrap reads."""

    def __init__(self, *, jwks_url="https://proj.supabase.co/auth/v1/.well-known/jwks.json",
                 db_url="", scheme="asymmetric"):
        self.scheme = scheme
        self.jwks_url = jwks_url
        self.db_url = db_url
        self.accepted_algorithms = frozenset({"ES256", "RS256"})
        self.expected_aud = "authenticated"
        self.expected_iss = "https://proj.supabase.co/auth/v1"
        self.jwt_leeway_seconds = 60
        self.auth_failure_rate_limit = 20
        # JWKS cache tuning consumed by from_config:
        self.jwks_cache_ttl_seconds = 600
        self.jwks_refresh_cooldown_seconds = 60
        self.jwks_negative_ttl_seconds = 300
        self.jwks_negative_cache_max_size = 1024
        self.jwks_stale_grace_seconds = 3600


def loader(cfg):
    return lambda: cfg


def raising_loader(exc):
    def _l():
        raise exc
    return _l


async def fake_pool_builder_none(db_url, **kw):
    return None


def make_fake_pool_builder(marker):
    async def _b(db_url, **kw):
        marker["db_url"] = db_url
        if not db_url:
            return None

        class _Pool:
            async def close(self):
                marker["closed"] = True
        return _Pool()
    return _b


@pytest.fixture
def fake_client():
    # A real AsyncClient is fine (no request is made during build); inject it so
    # the builder does not create its own and we control teardown.
    c = httpx.AsyncClient()
    yield c
    # closed by tests via aclose() or here as safety.


class TestDormant:
    @pytest.mark.asyncio
    async def test_none_when_config_missing(self, fake_client):
        bundle = await build_supabase_auth(
            config_loader=raising_loader(SupabaseAuthConfigError("not set")),
            jwks_client=fake_client,
        )
        assert bundle is None
        await fake_client.aclose()

    @pytest.mark.asyncio
    async def test_none_when_symmetric_no_jwks_url(self, fake_client):
        cfg = FakeConfig(jwks_url=None, scheme="symmetric")
        bundle = await build_supabase_auth(
            config_loader=loader(cfg), jwks_client=fake_client,
        )
        assert bundle is None
        await fake_client.aclose()


class TestConfiguredBundle:
    @pytest.mark.asyncio
    async def test_builds_full_bundle(self, fake_client):
        cfg = FakeConfig(db_url="")
        bundle = await build_supabase_auth(
            config_loader=loader(cfg),
            jwks_client=fake_client,
            audit_pool_builder=fake_pool_builder_none,
        )
        assert isinstance(bundle, SupabaseAuthBundle)
        assert bundle.config is cfg
        assert isinstance(bundle.jwks_cache, JwksCache)
        assert isinstance(bundle.verifier, JwtVerifier)
        assert isinstance(bundle.rate_limiter, FixedWindowRateLimiter)
        assert isinstance(bundle.audit_logger, AuditLogger)
        await bundle.aclose()

    @pytest.mark.asyncio
    async def test_rate_limiter_uses_config_limit_and_window(self, fake_client):
        cfg = FakeConfig()
        cfg.auth_failure_rate_limit = 7
        bundle = await build_supabase_auth(
            config_loader=loader(cfg),
            jwks_client=fake_client,
            audit_pool_builder=fake_pool_builder_none,
        )
        # Limiter built with the config count and the wiring window constant.
        assert bundle.rate_limiter._limit == 7
        assert bundle.rate_limiter._window == AUTH_FAILURE_WINDOW_SECONDS
        await bundle.aclose()

    @pytest.mark.asyncio
    async def test_audit_dormant_when_no_db_url(self, fake_client):
        cfg = FakeConfig(db_url="")
        marker = {}
        bundle = await build_supabase_auth(
            config_loader=loader(cfg),
            jwks_client=fake_client,
            audit_pool_builder=make_fake_pool_builder(marker),
        )
        # AuditLogger built with acquirer=None -> dormant.
        assert bundle.audit_logger._acquirer is None
        assert bundle._audit_pool is None
        await bundle.aclose()

    @pytest.mark.asyncio
    async def test_audit_db_backed_when_db_url_set(self, fake_client):
        cfg = FakeConfig(db_url="postgresql://x")
        marker = {}
        bundle = await build_supabase_auth(
            config_loader=loader(cfg),
            jwks_client=fake_client,
            audit_pool_builder=make_fake_pool_builder(marker),
        )
        assert marker["db_url"] == "postgresql://x"
        assert bundle.audit_logger._acquirer is not None
        assert bundle._audit_pool is not None
        await bundle.aclose()
        assert marker.get("closed") is True  # teardown closed the pool


class TestFailFast:
    @pytest.mark.asyncio
    async def test_construction_error_propagates_and_closes_owned_client(self, monkeypatch):
        # No injected client -> builder owns it. Replace bootstrap's
        # httpx.AsyncClient with a fake that records aclose(), force the audit
        # pool builder to raise (simulating a DB connect failure), and assert the
        # owned client is closed before the error propagates (no leaked
        # connection on a failed boot).
        cfg = FakeConfig(db_url="postgresql://x")
        created = {"closed": False}

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def aclose(self):
                created["closed"] = True

        monkeypatch.setattr(bootstrap.httpx, "AsyncClient", FakeClient)

        async def boom_builder(db_url, **kw):
            raise RuntimeError("db connect failed")

        with pytest.raises(RuntimeError, match="db connect failed"):
            await build_supabase_auth(
                config_loader=loader(cfg),
                jwks_client=None,            # builder creates & owns the client
                audit_pool_builder=boom_builder,
            )
        assert created["closed"] is True


class TestTeardown:
    @pytest.mark.asyncio
    async def test_aclose_is_best_effort(self, fake_client):
        cfg = FakeConfig(db_url="")
        bundle = await build_supabase_auth(
            config_loader=loader(cfg),
            jwks_client=fake_client,
            audit_pool_builder=fake_pool_builder_none,
        )
        await bundle.aclose()
        # Second close must not raise (client already closed).
        await bundle.aclose()
