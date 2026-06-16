# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C audit-pool adapter
(kiro/supabase_auth/db.py, M6).

No asyncpg, no database: an injected pool_factory stands in for
asyncpg.create_pool. Verifies dormant-when-unconfigured, adapter construction,
ConnectionAcquirer surface (acquire delegation), tuning pass-through, and
best-effort close.
"""

import pytest

from kiro.supabase_auth.db import build_audit_pool, AuditConnectionPool


class FakePool:
    def __init__(self):
        self.closed = False
        self.acquire_marker = object()
        self.close_raises = False

    def acquire(self):
        # Real asyncpg returns an async-CM; we only assert delegation here.
        return self.acquire_marker

    async def close(self):
        if self.close_raises:
            raise RuntimeError("close boom")
        self.closed = True


def make_factory(pool, captured):
    async def _factory(**kwargs):
        captured.update(kwargs)
        return pool
    return _factory


class TestBuildAuditPool:
    @pytest.mark.asyncio
    async def test_returns_none_when_db_url_empty(self):
        assert await build_audit_pool("") is None
        assert await build_audit_pool(None) is None

    @pytest.mark.asyncio
    async def test_builds_adapter_with_injected_factory(self):
        pool = FakePool()
        captured = {}
        adapter = await build_audit_pool(
            "postgresql://x", pool_factory=make_factory(pool, captured)
        )
        assert isinstance(adapter, AuditConnectionPool)
        # dsn + tuning forwarded to the factory.
        assert captured["dsn"] == "postgresql://x"
        assert captured["min_size"] >= 1
        assert captured["max_size"] >= captured["min_size"]
        assert captured["command_timeout"] > 0

    @pytest.mark.asyncio
    async def test_tuning_overrides_forwarded(self):
        pool = FakePool()
        captured = {}
        await build_audit_pool(
            "postgresql://x",
            min_size=2,
            max_size=7,
            command_timeout=3.5,
            pool_factory=make_factory(pool, captured),
        )
        assert captured["min_size"] == 2
        assert captured["max_size"] == 7
        assert captured["command_timeout"] == 3.5

    @pytest.mark.asyncio
    async def test_acquire_delegates_to_pool(self):
        pool = FakePool()
        adapter = await build_audit_pool(
            "postgresql://x", pool_factory=make_factory(pool, {})
        )
        # ConnectionAcquirer surface: acquire() returns the pool's CM.
        assert adapter.acquire() is pool.acquire_marker

    @pytest.mark.asyncio
    async def test_close_delegates(self):
        pool = FakePool()
        adapter = await build_audit_pool(
            "postgresql://x", pool_factory=make_factory(pool, {})
        )
        await adapter.close()
        assert pool.closed is True

    @pytest.mark.asyncio
    async def test_close_is_best_effort(self):
        pool = FakePool()
        pool.close_raises = True
        adapter = await build_audit_pool(
            "postgresql://x", pool_factory=make_factory(pool, {})
        )
        # Must not raise despite the underlying pool erroring.
        await adapter.close()


class TestNoTopLevelAsyncpg:
    def test_module_imports_without_asyncpg(self):
        # The module is already imported at top of this test file; reaching here
        # proves importing kiro.supabase_auth.db did not require asyncpg.
        import kiro.supabase_auth.db as m
        assert hasattr(m, "build_audit_pool")
