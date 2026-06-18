# -*- coding: utf-8 -*-

"""
Unit tests for the profile-body reader
(kiro/supabase_auth/profile.py, M8a READ 2).

Fake acquirer (no asyncpg, no DB). Verifies the body mapping keyed on user_id,
the RLS session context (role + sub bound before the SELECT), user_id-mismatch
rejection, and missing/absent-acquirer → ProfileUnavailableError (500).
"""

import pytest

from kiro.supabase_auth.profile import (
    ProfileReader,
    UserProfile,
    build_user_profile,
)
from kiro.supabase_auth.exceptions import ProfileUnavailableError


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Conn:
    def __init__(self, row):
        self._row = row
        self.executed = []
        self.fetched = []

    def transaction(self):
        return _Txn()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        self.fetched.append((sql, args))
        return self._row


class _CM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _Acquirer:
    def __init__(self, row):
        self.conn = _Conn(row)

    def acquire(self):
        return _CM(self.conn)


_ROW = {
    "user_id": "u1",
    "email": "u@example.com",
    "name": "Test",
    "gender": "x",
    "birth_date": None,
    "country": "US",
    "onboarding_completed": True,
}


class TestBuildUserProfile:
    def test_maps_fields(self):
        p = build_user_profile(_ROW, expected_user_id="u1")
        assert isinstance(p, UserProfile)
        assert p.user_id == "u1" and p.email == "u@example.com"
        assert p.country == "US" and p.onboarding_completed is True

    def test_user_id_mismatch_raises(self):
        with pytest.raises(ProfileUnavailableError):
            build_user_profile({"user_id": "other"}, expected_user_id="u1")


class TestFetchProfile:
    @pytest.mark.asyncio
    async def test_returns_profile(self):
        acq = _Acquirer(_ROW)
        p = await ProfileReader(acq).fetch_profile("u1")
        assert p.user_id == "u1" and p.onboarding_completed is True

    @pytest.mark.asyncio
    async def test_sets_rls_context_before_select(self):
        acq = _Acquirer(_ROW)
        await ProfileReader(acq).fetch_profile("u1")
        execs = " ".join(sql for sql, _ in acq.conn.executed)
        assert "role" in execs and "authenticated" in execs
        assert any("request.jwt.claim.sub" in sql for sql, _ in acq.conn.executed)
        # Body SELECT is parameterized on user_id and excludes auth-state columns.
        sel_sql, sel_args = acq.conn.fetched[0]
        assert "WHERE user_id = $1" in sel_sql and sel_args == ("u1",)
        assert "deleted_at" not in sel_sql and "banned_until" not in sel_sql

    @pytest.mark.asyncio
    async def test_missing_row_raises_500(self):
        with pytest.raises(ProfileUnavailableError):
            await ProfileReader(_Acquirer(None)).fetch_profile("u1")

    @pytest.mark.asyncio
    async def test_no_acquirer_raises_500(self):
        with pytest.raises(ProfileUnavailableError):
            await ProfileReader(None).fetch_profile("u1")


class TestNoTopLevelAsyncpg:
    def test_module_imports_without_asyncpg(self):
        import kiro.supabase_auth.profile as m
        assert hasattr(m, "ProfileReader")
        assert not hasattr(m, "asyncpg")
