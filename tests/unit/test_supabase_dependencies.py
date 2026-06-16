# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C auth dependency
(kiro/supabase_auth/dependencies.py, M6).

Injected fakes only — no FastAPI app, no network, no DB. Verifies the §3 flow:
header extraction, rate-limit pre-check (and no-audit throttle path), JWT verify,
identity construction, best-effort audit on each failure branch, no audit on
success, success resets the IP budget and sets request.state.user, and dormant
bundle behavior. Asserts the dependency raises ONLY existing typed exceptions
and performs no HTTP mapping.
"""

from types import SimpleNamespace, MappingProxyType

import pytest

from kiro.supabase_auth.dependencies import get_current_user
from kiro.supabase_auth.audit import AuditEvent
from kiro.supabase_auth.exceptions import (
    InvalidTokenError,
    TokenExpiredError,
    JwksUnavailableError,
    SupabaseAuthError,
)
from kiro.supabase_auth.user import AuthenticatedUser, InvalidIdentityError
from kiro.supabase_auth.verifier import VerifiedClaims


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeLimiter:
    def __init__(self, allow=True):
        self._allow = allow
        self.allow_calls = []
        self.reset_calls = []

    def allow(self, key):
        self.allow_calls.append(key)
        return self._allow

    def reset(self, key):
        self.reset_calls.append(key)


class FakeVerifier:
    def __init__(self, claims=None, raise_exc=None):
        self._claims = claims
        self._raise = raise_exc
        self.verify_calls = []

    async def verify(self, token):
        self.verify_calls.append(token)
        if self._raise is not None:
            raise self._raise
        return self._claims


class FakeAudit:
    def __init__(self):
        self.records = []

    def record(self, event, *, user_id=None, ip_address=None, user_agent=None,
               request_id=None):
        self.records.append(
            dict(event=event, user_id=user_id, ip_address=ip_address,
                 user_agent=user_agent, request_id=request_id)
        )


class FakeHeaders:
    def __init__(self, mapping):
        # case-insensitive like Starlette Headers
        self._m = {k.lower(): v for k, v in mapping.items()}

    def get(self, key, default=None):
        return self._m.get(key.lower(), default)


class FakeRequest:
    def __init__(self, *, bundle, headers=None, client_host="203.0.113.9"):
        self.app = SimpleNamespace(state=SimpleNamespace(supabase_auth=bundle))
        self.headers = FakeHeaders(headers or {})
        self.client = SimpleNamespace(host=client_host) if client_host else None
        self.state = SimpleNamespace()


def make_claims(sub="11111111-1111-1111-1111-111111111111"):
    return VerifiedClaims(
        sub=sub, aud="authenticated", iss="https://proj.supabase.co/auth/v1",
        iat=1_700_000_000, exp=1_700_003_600, email="user@example.com",
        app_metadata=MappingProxyType({"provider": "google"}),
        user_metadata=MappingProxyType({"name": "Test"}),
    )


def make_bundle(*, verifier=None, limiter=None, audit=None):
    return SimpleNamespace(
        verifier=verifier or FakeVerifier(claims=make_claims()),
        rate_limiter=limiter or FakeLimiter(allow=True),
        audit_logger=audit or FakeAudit(),
    )


VALID_AUTH = {"authorization": "Bearer good.token.here", "user-agent": "UA/1"}


# --------------------------------------------------------------------------- #
class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_returns_user_and_sets_state(self):
        audit = FakeAudit()
        limiter = FakeLimiter(allow=True)
        bundle = make_bundle(audit=audit, limiter=limiter)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)

        user = await get_current_user(req)
        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "11111111-1111-1111-1111-111111111111"
        assert req.state.user is user

    @pytest.mark.asyncio
    async def test_success_emits_no_audit(self):
        audit = FakeAudit()
        bundle = make_bundle(audit=audit)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)
        await get_current_user(req)
        assert audit.records == []          # D6: no per-request success row

    @pytest.mark.asyncio
    async def test_success_resets_ip_budget(self):
        limiter = FakeLimiter(allow=True)
        bundle = make_bundle(limiter=limiter)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH, client_host="1.2.3.4")
        await get_current_user(req)
        assert limiter.reset_calls == ["1.2.3.4"]


class TestBearerExtraction:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("headers", [
        {},                                              # no header
        {"authorization": "good.token"},                # no scheme
        {"authorization": "Basic abc"},                 # wrong scheme
        {"authorization": "Bearer"},                     # no token part
        {"authorization": "Bearer "},                    # empty token
    ])
    async def test_missing_or_malformed_header_raises_invalid_token(self, headers):
        audit = FakeAudit()
        bundle = make_bundle(audit=audit)
        req = FakeRequest(bundle=bundle, headers=headers)
        with pytest.raises(InvalidTokenError):
            await get_current_user(req)
        # Failure is audited best-effort.
        assert len(audit.records) == 1
        assert audit.records[0]["event"] is AuditEvent.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_bearer_is_case_insensitive(self):
        bundle = make_bundle()
        req = FakeRequest(bundle=bundle,
                          headers={"authorization": "bearer good.token"})
        user = await get_current_user(req)
        assert isinstance(user, AuthenticatedUser)


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_throttled_raises_and_does_not_audit(self):
        # Throttle path must NOT emit an audit row (avoid amplifying abuse).
        audit = FakeAudit()
        limiter = FakeLimiter(allow=False)
        bundle = make_bundle(audit=audit, limiter=limiter)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)
        with pytest.raises(InvalidTokenError):
            await get_current_user(req)
        assert audit.records == []

    @pytest.mark.asyncio
    async def test_throttle_checked_before_token_extraction(self):
        # Even with NO Authorization header, a throttled IP is rejected — proving
        # the limiter runs before extraction (header-less floods are throttled).
        limiter = FakeLimiter(allow=False)
        verifier = FakeVerifier(claims=make_claims())
        bundle = make_bundle(limiter=limiter, verifier=verifier)
        req = FakeRequest(bundle=bundle, headers={})
        with pytest.raises(InvalidTokenError):
            await get_current_user(req)
        assert verifier.verify_calls == []       # never reached verify
        assert limiter.allow_calls == ["203.0.113.9"]


class TestVerificationErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc_type", [
        TokenExpiredError, InvalidTokenError, JwksUnavailableError,
    ])
    async def test_verify_errors_propagate_unchanged_and_audit(self, exc_type):
        audit = FakeAudit()
        verifier = FakeVerifier(raise_exc=exc_type("boom", detail="x"))
        bundle = make_bundle(audit=audit, verifier=verifier)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)
        with pytest.raises(exc_type):            # SAME typed exception, no mapping
            await get_current_user(req)
        assert len(audit.records) == 1
        assert audit.records[0]["event"] is AuditEvent.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_invalid_identity_propagates_and_audits(self):
        # Verifier returns claims with empty sub -> build_authenticated_user raises.
        audit = FakeAudit()
        verifier = FakeVerifier(claims=make_claims(sub=""))
        bundle = make_bundle(audit=audit, verifier=verifier)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)
        with pytest.raises(InvalidIdentityError):
            await get_current_user(req)
        assert len(audit.records) == 1


class TestAuditFields:
    @pytest.mark.asyncio
    async def test_failure_audit_carries_ip_and_ua_not_token(self):
        audit = FakeAudit()
        verifier = FakeVerifier(raise_exc=InvalidTokenError("bad"))
        bundle = make_bundle(audit=audit, verifier=verifier)
        req = FakeRequest(bundle=bundle,
                          headers={"authorization": "Bearer secret.jwt.value",
                                   "user-agent": "UA/9"},
                          client_host="198.51.100.7")
        with pytest.raises(InvalidTokenError):
            await get_current_user(req)
        rec = audit.records[0]
        assert rec["ip_address"] == "198.51.100.7"
        assert rec["user_agent"] == "UA/9"
        assert rec["user_id"] is None             # subject unknown on failure
        # The token never appears in any audit field.
        flat = " ".join(str(v) for v in rec.values())
        assert "secret.jwt.value" not in flat


class TestDormant:
    @pytest.mark.asyncio
    async def test_dormant_bundle_raises_invalid_token(self):
        req = FakeRequest(bundle=None, headers=VALID_AUTH)
        with pytest.raises(InvalidTokenError):
            await get_current_user(req)


class TestNoHttpMapping:
    @pytest.mark.asyncio
    async def test_raises_only_supabase_auth_errors(self):
        # Sweep failure modes; every raised error is a SupabaseAuthError subtype
        # (never an HTTPException / status code — that is M7's concern).
        verifier = FakeVerifier(raise_exc=InvalidTokenError("x"))
        bundle = make_bundle(verifier=verifier)
        req = FakeRequest(bundle=bundle, headers=VALID_AUTH)
        with pytest.raises(SupabaseAuthError):
            await get_current_user(req)

    def test_module_imports_no_http_status(self):
        import kiro.supabase_auth.dependencies as m
        # The dependency must not reach for HTTPException / status codes.
        assert not hasattr(m, "HTTPException")
        assert not hasattr(m, "status")
