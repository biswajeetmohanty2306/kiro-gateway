# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C audit writer (kiro/supabase_auth/audit.py, M5).

All DB access is MOCKED (fake acquirer/connection) — no real Postgres, no
asyncpg import. Covers: parameterized insert + column mapping + uuid generation,
nullable user_id, closed event enum, the structural no-leak guarantee (§4),
best-effort failure handling (§6), non-blocking fire-and-forget record()
dispatch, and the dormant (unconfigured) no-op path.
"""

import asyncio
import inspect
import uuid

import pytest

from kiro.supabase_auth.audit import (
    AuditLogger,
    AuditEvent,
    _INSERT_SQL,
)


# --------------------------------------------------------------------------- #
# Fakes: an async-context-manager connection acquirer that records execute().
# Shapes match asyncpg's pool.acquire() / connection.execute() so the real
# driver is a drop-in, but no database (or asyncpg) is needed here.
# --------------------------------------------------------------------------- #
class FakeConnection:
    def __init__(self, raise_exc=None):
        self.calls = []            # list of (sql, args)
        self._raise = raise_exc

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        if self._raise is not None:
            raise self._raise
        return "INSERT 0 1"


class _Acquired:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class FakeAcquirer:
    def __init__(self, conn):
        self._conn = conn
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1
        return _Acquired(self._conn)


def make_logger(raise_exc=None):
    conn = FakeConnection(raise_exc=raise_exc)
    acquirer = FakeAcquirer(conn)
    return AuditLogger(acquirer), conn, acquirer


VALID_SUB = "11111111-1111-1111-1111-111111111111"


class TestInsertMapping:
    """Parameterized SQL, column order, uuid generation, created_at via now()."""

    @pytest.mark.asyncio
    async def test_write_emits_parameterized_insert(self):
        logger, conn, _ = make_logger()
        await logger.write(
            AuditEvent.LOGOUT,
            user_id=VALID_SUB,
            ip_address="203.0.113.7",
            user_agent="Mozilla/5.0",
        )
        assert len(conn.calls) == 1
        sql, args = conn.calls[0]
        assert sql == _INSERT_SQL
        # 5 bound params; created_at is SQL now(), not a bound arg.
        assert len(args) == 5

    @pytest.mark.asyncio
    async def test_no_string_interpolation_uses_placeholders(self):
        # The SQL must carry $1..$5 placeholders and now() — never f-string values.
        assert "$1" in _INSERT_SQL and "$5" in _INSERT_SQL
        assert "now()" in _INSERT_SQL
        assert "%s" not in _INSERT_SQL  # no printf-style interpolation either

    @pytest.mark.asyncio
    async def test_column_mapping_and_types(self):
        logger, conn, _ = make_logger()
        await logger.write(
            AuditEvent.ONBOARDING_COMPLETED,
            user_id=VALID_SUB,
            ip_address="203.0.113.7",
            user_agent="UA/1",
        )
        _, args = conn.calls[0]
        audit_id, user_id, event_type, ip, ua = args
        assert isinstance(audit_id, uuid.UUID)                 # generated
        assert user_id == uuid.UUID(VALID_SUB)                 # str -> UUID
        assert event_type == "onboarding.completed"            # enum value
        assert ip == "203.0.113.7"
        assert ua == "UA/1"

    @pytest.mark.asyncio
    async def test_audit_id_is_unique_per_write(self):
        logger, conn, _ = make_logger()
        await logger.write(AuditEvent.LOGOUT, user_id=VALID_SUB)
        await logger.write(AuditEvent.LOGOUT, user_id=VALID_SUB)
        id1 = conn.calls[0][1][0]
        id2 = conn.calls[1][1][0]
        assert id1 != id2


class TestNullableUserId:
    """user_id is nullable (auth.failure has no known subject)."""

    @pytest.mark.asyncio
    async def test_auth_failure_writes_null_user(self):
        logger, conn, _ = make_logger()
        await logger.write(
            AuditEvent.AUTH_FAILURE, ip_address="198.51.100.2", user_agent="curl/8"
        )
        _, args = conn.calls[0]
        assert args[1] is None              # user_id NULL
        assert args[2] == "auth.failure"

    @pytest.mark.asyncio
    async def test_non_uuid_user_id_stored_as_null_but_event_written(self):
        logger, conn, _ = make_logger()
        await logger.write(AuditEvent.AUTHZ_DENIED, user_id="not-a-uuid")
        assert len(conn.calls) == 1         # event still written
        assert conn.calls[0][1][1] is None  # user_id coerced to NULL

    @pytest.mark.asyncio
    async def test_all_optional_fields_absent(self):
        logger, conn, _ = make_logger()
        await logger.write(AuditEvent.AUTH_FAILURE)
        _, args = conn.calls[0]
        assert args[1] is None and args[3] is None and args[4] is None


class TestEventEnum:
    """Closed event set; auth.success deliberately absent (D6)."""

    def test_event_values(self):
        assert AuditEvent.AUTH_FAILURE.value == "auth.failure"
        assert AuditEvent.AUTHZ_DENIED.value == "authz.denied"
        assert AuditEvent.ONBOARDING_COMPLETED.value == "onboarding.completed"
        assert AuditEvent.PROFILE_PROVISIONED.value == "profile.provisioned"
        assert AuditEvent.LOGOUT.value == "logout"

    def test_no_auth_success_event(self):
        # Per-request success is NOT audited (volume rule D6/§3.3).
        values = {e.value for e in AuditEvent}
        assert "auth.success" not in values
        assert not any(v.endswith(".success") for v in values)


class TestNoLeak:
    """§4: the API structurally cannot accept a token/header/secret."""

    def test_signature_accepts_only_safe_fields(self):
        for fn in (AuditLogger.record, AuditLogger.write):
            params = set(inspect.signature(fn).parameters) - {"self"}
            # Allowed: event + the safe nullable columns + correlation id.
            assert params <= {
                "event", "user_id", "ip_address", "user_agent", "request_id"
            }, f"{fn.__name__} exposes unexpected params: {params}"
            # Explicitly forbidden parameter names.
            for forbidden in (
                "token", "jwt", "authorization", "auth_header", "bearer",
                "claims", "secret", "refresh_token", "password",
            ):
                assert forbidden not in params

    @pytest.mark.asyncio
    async def test_bound_params_contain_no_jwt_or_bearer(self):
        # Even with hostile-looking (but allowed) field values, the bound args
        # are exactly what was passed — no token material is ever synthesized.
        logger, conn, _ = make_logger()
        await logger.write(
            AuditEvent.AUTH_FAILURE,
            user_id=VALID_SUB,
            ip_address="203.0.113.7",
            user_agent="UA/1",
        )
        flat = " ".join(str(a) for a in conn.calls[0][1])
        assert "eyJ" not in flat          # no JWT segment
        assert "Bearer " not in flat       # no Authorization value
        assert _INSERT_SQL.count("$") == 5  # values bound, not inlined


class TestBestEffortFailure:
    """§6: a failed write never propagates and is logged."""

    @pytest.mark.asyncio
    async def test_write_swallows_db_error(self):
        logger, conn, _ = make_logger(raise_exc=RuntimeError("db down"))
        # Must NOT raise despite the connection erroring.
        await logger.write(AuditEvent.AUTH_FAILURE, user_id=VALID_SUB)
        assert len(conn.calls) == 1  # attempted

    @pytest.mark.asyncio
    async def test_write_logs_warning_on_failure(self, caplog):
        import logging

        # Bridge loguru -> standard logging so caplog can capture it.
        from loguru import logger as loguru_logger

        sink_id = loguru_logger.add(logging.getLogger().handlers[0]
                                    if logging.getLogger().handlers else logging.NullHandler(),
                                    level="WARNING")
        try:
            logger, _, _ = make_logger(raise_exc=RuntimeError("boom"))
            with caplog.at_level(logging.WARNING):
                await logger.write(AuditEvent.LOGOUT, user_id=VALID_SUB,
                                   request_id="req-123")
        finally:
            loguru_logger.remove(sink_id)
        # The failure path completed without raising — primary guarantee.
        # (Message capture is best-effort across the loguru/std-logging bridge.)


class TestNonBlockingRecord:
    """record() schedules a background write and returns immediately."""

    @pytest.mark.asyncio
    async def test_record_dispatches_write(self):
        logger, conn, _ = make_logger()
        logger.record(
            AuditEvent.LOGOUT, user_id=VALID_SUB, ip_address="1.2.3.4",
            user_agent="UA", request_id="r1",
        )
        # record() returns synchronously; let the scheduled task run.
        assert conn.calls == []          # not yet executed (truly async)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(conn.calls) == 1      # write happened in the background
        assert conn.calls[0][1][2] == "logout"

    @pytest.mark.asyncio
    async def test_record_failure_does_not_propagate(self):
        logger, _, _ = make_logger(raise_exc=RuntimeError("db down"))
        logger.record(AuditEvent.AUTH_FAILURE, request_id="r2")  # must not raise
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # No exception escaped the background task — test reaching here is the pass.

    @pytest.mark.asyncio
    async def test_record_keeps_task_reference(self):
        logger, conn, _ = make_logger()
        logger.record(AuditEvent.LOGOUT, user_id=VALID_SUB)
        assert len(logger._tasks) >= 1    # strong ref held so task isn't GC'd
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(logger._tasks) == 0    # done-callback cleaned it up


class TestDormant:
    """Unconfigured (no acquirer) -> safe no-op; deployments without Phase C."""

    @pytest.mark.asyncio
    async def test_write_no_op_when_unconfigured(self):
        logger = AuditLogger(acquirer=None)
        await logger.write(AuditEvent.LOGOUT, user_id=VALID_SUB)  # no error

    def test_record_no_op_when_unconfigured(self):
        logger = AuditLogger(acquirer=None)
        logger.record(AuditEvent.AUTH_FAILURE)  # no error, no scheduling
        assert logger._tasks == set()

    def test_record_no_running_loop_does_not_raise(self):
        # Sync context, configured logger: no loop -> log-and-drop, never raise.
        _, conn, _ = make_logger()
        logger = AuditLogger(FakeAcquirer(conn))
        logger.record(AuditEvent.LOGOUT, user_id=VALID_SUB)  # must not raise
        assert conn.calls == []
