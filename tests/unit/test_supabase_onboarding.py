# -*- coding: utf-8 -*-

"""
Unit tests for the onboarding transition
(kiro/supabase_auth/onboarding.py, M8a; A3, D8).

Fake acquirer (no asyncpg, no DB). Verifies the atomic conditional transition
(real flip → transitioned=True), idempotent re-submit (zero-row UPDATE → no-op,
transitioned=False), concurrency (two submits → exactly one transition), the RLS
session context, and missing-row / absent-acquirer → ProfileUnavailableError.
"""

import asyncio

import pytest

from kiro.supabase_auth.onboarding import complete_onboarding, OnboardingResult
from kiro.supabase_auth.exceptions import ProfileUnavailableError


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _SharedRow:
    """A tiny shared cell modeling one users row's onboarding_completed."""

    def __init__(self, completed=False):
        self.completed = completed
        self.transitions = 0


class _Conn:
    """
    Models the atomic conditional UPDATE on a shared row: the first caller to find
    completed=False flips it (returns a row); subsequent callers update zero rows
    (return None) and read current state.
    """

    def __init__(self, shared: _SharedRow):
        self._shared = shared
        self.executed = []

    def transaction(self):
        return _Txn()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        if "UPDATE" in sql:
            if not self._shared.completed:
                self._shared.completed = True
                self._shared.transitions += 1
                return {"onboarding_completed": True}
            return None                      # zero rows: already true
        # READ path (idempotent no-op)
        return {"onboarding_completed": self._shared.completed}


class _CM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _Acquirer:
    def __init__(self, shared: _SharedRow):
        self._shared = shared
        self.conn = _Conn(shared)

    def acquire(self):
        return _CM(self.conn)


class _MissingAcquirer:
    """UPDATE matches nothing AND the read finds no row (row truly absent)."""

    class _C:
        def transaction(self):
            return _Txn()

        async def execute(self, sql, *args):
            return None

        async def fetchrow(self, sql, *args):
            return None

    def acquire(self):
        return _CM(self._C())


class TestCompleteOnboarding:
    @pytest.mark.asyncio
    async def test_real_transition(self):
        shared = _SharedRow(completed=False)
        res = await complete_onboarding(_Acquirer(shared), "u1")
        assert isinstance(res, OnboardingResult)
        assert res.transitioned is True and res.onboarding_completed is True
        assert shared.transitions == 1

    @pytest.mark.asyncio
    async def test_idempotent_resubmit_is_noop(self):
        shared = _SharedRow(completed=True)
        res = await complete_onboarding(_Acquirer(shared), "u1")
        assert res.transitioned is False and res.onboarding_completed is True
        assert shared.transitions == 0       # no new transition

    @pytest.mark.asyncio
    async def test_two_concurrent_submits_exactly_one_transition(self):
        # A3: both submits hit the SAME shared row; exactly one flips false→true.
        shared = _SharedRow(completed=False)
        acq = _Acquirer(shared)
        r1, r2 = await asyncio.gather(
            complete_onboarding(acq, "u1"),
            complete_onboarding(acq, "u1"),
        )
        assert shared.transitions == 1
        assert {r1.transitioned, r2.transitioned} == {True, False}
        assert r1.onboarding_completed and r2.onboarding_completed

    @pytest.mark.asyncio
    async def test_sets_rls_context(self):
        shared = _SharedRow(completed=False)
        acq = _Acquirer(shared)
        await complete_onboarding(acq, "u1")
        execs = " ".join(sql for sql, _ in acq.conn.executed)
        assert "role" in execs and "authenticated" in execs
        assert any("request.jwt.claim.sub" in sql for sql, _ in acq.conn.executed)

    @pytest.mark.asyncio
    async def test_missing_row_raises_500(self):
        with pytest.raises(ProfileUnavailableError):
            await complete_onboarding(_MissingAcquirer(), "u1")

    @pytest.mark.asyncio
    async def test_no_acquirer_raises_500(self):
        with pytest.raises(ProfileUnavailableError):
            await complete_onboarding(None, "u1")
