# -*- coding: utf-8 -*-

"""
Unit tests for the authoritative user-state reader
(kiro/supabase_auth/state_read.py, M8a READ 1).

Fake acquirer (no asyncpg, no DB). Verifies the reader distinguishes the four
cases the user-scoped path cannot — active / banned / deleted / missing — and
fails closed (UserStateUnavailableError) on a DB error or absent acquirer.
"""

from datetime import datetime, timezone, timedelta

import pytest

from kiro.supabase_auth.state_read import StateReader
from kiro.supabase_auth.exceptions import UserStateUnavailableError

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Conn:
    def __init__(self, row, raises=False):
        self._row = row
        self._raises = raises
        self.queries = []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if self._raises:
            raise RuntimeError("db down")
        return self._row


class _CM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _Acquirer:
    def __init__(self, row, raises=False):
        self.conn = _Conn(row, raises)

    def acquire(self):
        return _CM(self.conn)


class TestReadAuthState:
    @pytest.mark.asyncio
    async def test_active_row(self):
        acq = _Acquirer({"deleted_at": None, "banned_until": None})
        s = await StateReader(acq).read_auth_state("u1")
        assert s.row_exists is True
        assert s.deleted_at is None and s.banned_until is None
        assert s.user_id == "u1"

    @pytest.mark.asyncio
    async def test_deleted_row(self):
        acq = _Acquirer({"deleted_at": _NOW, "banned_until": None})
        s = await StateReader(acq).read_auth_state("u1")
        assert s.row_exists is True and s.deleted_at == _NOW

    @pytest.mark.asyncio
    async def test_banned_row(self):
        until = _NOW + timedelta(hours=1)
        acq = _Acquirer({"deleted_at": None, "banned_until": until})
        s = await StateReader(acq).read_auth_state("u1")
        assert s.row_exists is True and s.banned_until == until

    @pytest.mark.asyncio
    async def test_missing_row_reports_not_exists(self):
        # 0 rows → row_exists False (NOT an error; D4 caller handles it).
        acq = _Acquirer(None)
        s = await StateReader(acq).read_auth_state("u1")
        assert s.row_exists is False

    @pytest.mark.asyncio
    async def test_query_is_parameterized_and_joins_auth_users(self):
        acq = _Acquirer({"deleted_at": None, "banned_until": None})
        await StateReader(acq).read_auth_state("u1")
        sql, args = acq.conn.queries[0]
        assert "$1" in sql and "public.users" in sql and "auth.users" in sql
        assert args == ("u1",)               # user_id bound, never interpolated

    @pytest.mark.asyncio
    async def test_db_error_fails_closed(self):
        acq = _Acquirer({}, raises=True)
        with pytest.raises(UserStateUnavailableError):
            await StateReader(acq).read_auth_state("u1")

    @pytest.mark.asyncio
    async def test_no_acquirer_fails_closed(self):
        with pytest.raises(UserStateUnavailableError):
            await StateReader(None).read_auth_state("u1")


class TestNoTopLevelAsyncpg:
    def test_module_imports_without_asyncpg(self):
        import kiro.supabase_auth.state_read as m
        assert hasattr(m, "StateReader")
        assert not hasattr(m, "asyncpg")
