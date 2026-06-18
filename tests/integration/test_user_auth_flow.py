# -*- coding: utf-8 -*-

"""
Integration tests for the Phase C M8a authorization flow.

Builds a standalone FastAPI app with the real user-auth router, the real
SupabaseAuthError handler, and the real M8a dependencies/readers — wired to a
single in-memory fake DB connection (no asyncpg, no network). Only the JWT
verifier, rate limiter, and audit logger are faked; the authorization path
(state read → enforce_active → profile body → onboarding) runs the real code.

Covers the S1 acceptance tests (M8AuthorizationPlanV3 §13/§15):
  - banned user + valid JWT  → 403 ACCOUNT_DISABLED
  - deleted user + valid JWT → 403 ACCOUNT_DISABLED
  - missing profile          → 500 INTERNAL (distinct from deleted)
  - active user              → 200 profile body
  - onboarding flow          → submit flips false→true; idempotent re-submit
  - require_onboarded gate    → 403 ONBOARDING_REQUIRED (via a test-only route)
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace, MappingProxyType

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kiro.routes_user import router as user_router
from kiro.supabase_auth.http import register_exception_handlers
from kiro.supabase_auth.dependencies import require_onboarded
from kiro.supabase_auth.state_read import StateReader
from kiro.supabase_auth.profile import ProfileReader
from kiro.supabase_auth.verifier import VerifiedClaims

_SUB = "11111111-1111-1111-1111-111111111111"
_FUTURE = datetime.now(timezone.utc) + timedelta(hours=1)


# --------------------------------------------------------------------------- #
# Fake DB: one user row, driving the REAL readers + onboarding transition.
# --------------------------------------------------------------------------- #
class FakeUserRow:
    def __init__(self, *, exists=True, deleted_at=None, banned_until=None,
                 onboarding_completed=False):
        self.exists = exists
        self.deleted_at = deleted_at
        self.banned_until = banned_until
        self.onboarding_completed = onboarding_completed
        self.transitions = 0


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConn:
    """Dispatches the real SQL the readers/onboarding emit against one row."""

    def __init__(self, row: FakeUserRow):
        self._row = row

    def transaction(self):
        return _Txn()

    async def execute(self, sql, *args):
        return None  # SET LOCAL role / set_config — no-ops in the fake

    async def fetchrow(self, sql, *args):
        row = self._row
        if "UPDATE" in sql:                       # onboarding conditional transition
            if row.exists and not row.onboarding_completed:
                row.onboarding_completed = True
                row.transitions += 1
                return {"onboarding_completed": True}
            return None
        if "LEFT JOIN auth.users" in sql:         # state read (READ 1)
            if not row.exists:
                return None
            return {"deleted_at": row.deleted_at, "banned_until": row.banned_until}
        if "email" in sql:                        # profile body (READ 2)
            if not row.exists:
                return None
            return {
                "user_id": _SUB, "email": "u@example.com", "name": "Test",
                "gender": "x", "birth_date": None, "country": "US",
                "onboarding_completed": row.onboarding_completed,
            }
        if "onboarding_completed" in sql:         # onboarding idempotent read
            if not row.exists:
                return None
            return {"onboarding_completed": row.onboarding_completed}
        raise AssertionError(f"unexpected SQL: {sql}")


class _CM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class FakeAcquirer:
    def __init__(self, row: FakeUserRow):
        self.conn = FakeConn(row)

    def acquire(self):
        return _CM(self.conn)


class FakeVerifier:
    async def verify(self, token):
        return VerifiedClaims(
            sub=_SUB, aud="authenticated", iss="https://proj.supabase.co/auth/v1",
            iat=1_700_000_000, exp=1_700_003_600, email="u@example.com",
            app_metadata=MappingProxyType({"provider": "google"}),
            user_metadata=MappingProxyType({"name": "Test"}),
        )


class FakeLimiter:
    def allow(self, key):
        return True

    def reset(self, key):
        pass


class FakeAudit:
    def __init__(self):
        self.records = []

    def record(self, event, **kw):
        self.records.append({"event": event, **kw})


def _build_app(row: FakeUserRow):
    acq = FakeAcquirer(row)
    audit = FakeAudit()
    bundle = SimpleNamespace(
        verifier=FakeVerifier(),
        rate_limiter=FakeLimiter(),
        audit_logger=audit,
        state_reader=StateReader(acq),
        profile_reader=ProfileReader(acq),
        _audit_pool=acq,
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(user_router)

    # Test-only route exercising the require_onboarded gate (no shipped route
    # uses it in M8a, but the dependency must enforce ONBOARDING_REQUIRED).
    @app.get("/test/onboarded-only")
    async def _gated(profile=Depends(require_onboarded)):
        return {"ok": True}

    app.state.supabase_auth = bundle
    app.state._audit = audit  # test handle
    return app


def _client(row: FakeUserRow):
    return TestClient(_build_app(row))


_AUTH = {"Authorization": "Bearer valid.jwt.token"}


# --------------------------------------------------------------------------- #
# S1 acceptance: banned / deleted → 403; missing → 500; active → 200
# --------------------------------------------------------------------------- #
class TestStateEnforcement:
    def test_active_user_gets_profile(self):
        c = _client(FakeUserRow(onboarding_completed=True))
        r = c.get("/auth/profile", headers=_AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == _SUB and body["onboarding_completed"] is True
        assert body["email"] == "u@example.com"

    def test_banned_user_with_valid_jwt_is_403(self):
        # S1: valid token, but DB says banned → 403 ACCOUNT_DISABLED.
        c = _client(FakeUserRow(banned_until=_FUTURE))
        r = c.get("/auth/profile", headers=_AUTH)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"
        assert "WWW-Authenticate" not in r.headers

    def test_deleted_user_with_valid_jwt_is_403(self):
        # S1: valid token, but DB says soft-deleted → 403 ACCOUNT_DISABLED.
        c = _client(FakeUserRow(deleted_at=datetime.now(timezone.utc)))
        r = c.get("/auth/profile", headers=_AUTH)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"

    def test_banned_and_deleted_collapse_to_same_code(self):
        banned = _client(FakeUserRow(banned_until=_FUTURE)).get("/auth/profile", headers=_AUTH)
        deleted = _client(FakeUserRow(deleted_at=datetime.now(timezone.utc))).get("/auth/profile", headers=_AUTH)
        # Disclosure: client cannot tell banned from deleted.
        assert banned.json()["error"]["code"] == deleted.json()["error"]["code"]
        assert banned.json()["error"]["message"] == deleted.json()["error"]["message"]

    def test_missing_profile_is_500_not_403(self):
        # Distinct from deleted: a valid JWT with no row → server fault → 500.
        c = _client(FakeUserRow(exists=False))
        r = c.get("/auth/profile", headers=_AUTH)
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL"

    def test_denial_emits_authz_denied_audit(self):
        app = _build_app(FakeUserRow(banned_until=_FUTURE))
        client = TestClient(app)
        client.get("/auth/profile", headers=_AUTH)
        events = [r["event"].value for r in app.state._audit.records]
        assert "authz.denied" in events


# --------------------------------------------------------------------------- #
# Onboarding flow
# --------------------------------------------------------------------------- #
class TestOnboardingFlow:
    def test_submit_transitions_and_audits(self):
        row = FakeUserRow(onboarding_completed=False)
        app = _build_app(row)
        client = TestClient(app)
        r = client.post("/auth/onboarding", headers=_AUTH)
        assert r.status_code == 200
        assert r.json()["onboarding_completed"] is True
        assert row.transitions == 1
        events = [rec["event"].value for rec in app.state._audit.records]
        assert "onboarding.completed" in events

    def test_resubmit_is_idempotent_no_second_audit(self):
        row = FakeUserRow(onboarding_completed=True)
        app = _build_app(row)
        client = TestClient(app)
        r = client.post("/auth/onboarding", headers=_AUTH)
        assert r.status_code == 200
        assert r.json()["onboarding_completed"] is True
        assert row.transitions == 0  # no new transition
        events = [rec["event"].value for rec in app.state._audit.records]
        assert "onboarding.completed" not in events  # no audit on a no-op

    def test_require_onboarded_blocks_then_passes(self):
        row = FakeUserRow(onboarding_completed=False)
        app = _build_app(row)
        client = TestClient(app)
        # Un-onboarded → 403 ONBOARDING_REQUIRED on the gated route.
        r1 = client.get("/test/onboarded-only", headers=_AUTH)
        assert r1.status_code == 403
        assert r1.json()["error"]["code"] == "ONBOARDING_REQUIRED"
        # Submit onboarding, then the gated route passes.
        client.post("/auth/onboarding", headers=_AUTH)
        r2 = client.get("/test/onboarded-only", headers=_AUTH)
        assert r2.status_code == 200

    def test_onboarding_requires_active_user(self):
        # A banned user cannot onboard — get_auth_state rejects first.
        c = _client(FakeUserRow(banned_until=_FUTURE))
        r = c.post("/auth/onboarding", headers=_AUTH)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"


# --------------------------------------------------------------------------- #
# Correlation + no-leak on the wire
# --------------------------------------------------------------------------- #
class TestResponseShape:
    def test_403_has_request_envelope(self):
        c = _client(FakeUserRow(banned_until=_FUTURE))
        r = c.get("/auth/profile", headers=_AUTH)
        assert set(r.json()["error"].keys()) <= {"code", "message", "request_id"}
        assert r.json()["error"]["message"]  # non-empty generic message

    def test_no_internal_detail_leaks(self):
        c = _client(FakeUserRow(deleted_at=datetime.now(timezone.utc)))
        r = c.get("/auth/profile", headers=_AUTH)
        # The server-only detail ("deleted_at set") must not reach the client.
        assert "deleted_at" not in r.text
