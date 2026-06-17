# -*- coding: utf-8 -*-

"""
Unit + integration tests for the M7 HTTP exception mapping
(kiro/supabase_auth/http.py).

Three layers:
  1. _resolve(): each typed exception → correct (status, code, headers) on TYPE
     alone — the decision matrix (plan §2/§3).
  2. build_error_body(): the structured envelope (UD-4), request_id inclusion/
     omission, and the no-exc-in contract.
  3. End-to-end through the real handler on a minimal app (headers + body on the
     wire), plus the dormant /auth/me path on main.app (proves the wiring).

Disclosure: a no-leak test proves exc.detail never reaches the client body.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
from kiro.supabase_auth.http import (
    build_error_body,
    register_exception_handlers,
    supabase_auth_exception_handler,
    _resolve,
    CODE_TOKEN_EXPIRED,
    CODE_INVALID_TOKEN,
    CODE_RATE_LIMITED,
    CODE_AUTH_BACKEND_UNAVAILABLE,
)
from kiro.supabase_auth.exceptions import (
    AuthRateLimitedError,
    InvalidTokenError,
    JwksUnavailableError,
    SupabaseAuthError,
    TokenExpiredError,
)
from kiro.supabase_auth.user import InvalidIdentityError


# --------------------------------------------------------------------------- #
# 1. _resolve(): decision matrix
# --------------------------------------------------------------------------- #
class TestResolveMatrix:
    def test_token_expired(self):
        m = _resolve(TokenExpiredError("e", detail="exp in past"))
        assert m.status == 401
        assert m.code == CODE_TOKEN_EXPIRED
        assert m.headers.get("WWW-Authenticate") == 'Bearer error="invalid_token"'
        assert "Retry-After" not in m.headers

    def test_invalid_token(self):
        m = _resolve(InvalidTokenError("e", detail="bad sig"))
        assert m.status == 401
        assert m.code == CODE_INVALID_TOKEN
        assert "WWW-Authenticate" in m.headers

    def test_invalid_identity_falls_back_to_invalid_token(self):
        # InvalidIdentityError is a SupabaseAuthError (NOT an InvalidTokenError);
        # the base fallback must still map it to 401 INVALID_TOKEN.
        m = _resolve(InvalidIdentityError("e", detail="empty sub"))
        assert m.status == 401
        assert m.code == CODE_INVALID_TOKEN

    def test_rate_limited(self):
        m = _resolve(AuthRateLimitedError("e", detail="rate"))
        assert m.status == 429
        assert m.code == CODE_RATE_LIMITED
        assert m.headers.get("Retry-After") == "60"
        # 429 is NOT a credential challenge → no WWW-Authenticate.
        assert "WWW-Authenticate" not in m.headers

    def test_jwks_unavailable(self):
        m = _resolve(JwksUnavailableError("e", detail="down"))
        assert m.status == 503
        assert m.code == CODE_AUTH_BACKEND_UNAVAILABLE
        assert "Retry-After" in m.headers
        assert "WWW-Authenticate" not in m.headers

    def test_base_class_fallback(self):
        m = _resolve(SupabaseAuthError("e", detail="x"))
        assert m.status == 401
        assert m.code == CODE_INVALID_TOKEN


# --------------------------------------------------------------------------- #
# 2. build_error_body(): structured envelope (UD-4)
# --------------------------------------------------------------------------- #
class TestErrorBody:
    def test_shape_with_request_id(self):
        body = build_error_body("INVALID_TOKEN", "Authentication failed.", "rid-1")
        assert body == {
            "error": {
                "code": "INVALID_TOKEN",
                "message": "Authentication failed.",
                "request_id": "rid-1",
            }
        }

    def test_request_id_omitted_when_absent(self):
        body = build_error_body("INVALID_TOKEN", "Authentication failed.", None)
        assert body == {
            "error": {"code": "INVALID_TOKEN", "message": "Authentication failed."}
        }
        # Never a null field.
        assert "request_id" not in body["error"]

    def test_empty_request_id_omitted(self):
        body = build_error_body("X", "Y", "")
        assert "request_id" not in body["error"]


# --------------------------------------------------------------------------- #
# 3. End-to-end through the real handler (minimal app)
# --------------------------------------------------------------------------- #
def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    _exc = {
        "expired": TokenExpiredError("e", detail="exp in past"),
        "invalid": InvalidTokenError("e", detail="bad signature reason"),
        "identity": InvalidIdentityError("e", detail="empty sub"),
        "throttle": AuthRateLimitedError("e", detail="rate exceeded"),
        "jwks": JwksUnavailableError("e", detail="jwks endpoint down"),
        "base": SupabaseAuthError("e", detail="x"),
    }

    @app.get("/raise/{which}")
    async def _raise(which: str):
        raise _exc[which]

    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


class TestEndToEnd:
    @pytest.mark.parametrize("which,status,code", [
        ("expired", 401, "TOKEN_EXPIRED"),
        ("invalid", 401, "INVALID_TOKEN"),
        ("identity", 401, "INVALID_TOKEN"),
        ("throttle", 429, "RATE_LIMITED"),
        ("jwks", 503, "AUTH_BACKEND_UNAVAILABLE"),
        ("base", 401, "INVALID_TOKEN"),
    ])
    def test_status_and_code(self, client, which, status, code):
        r = client.get(f"/raise/{which}")
        assert r.status_code == status
        assert r.json()["error"]["code"] == code

    def test_401_has_www_authenticate(self, client):
        r = client.get("/raise/invalid")
        assert r.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'

    def test_429_has_retry_after_and_no_challenge(self, client):
        r = client.get("/raise/throttle")
        assert r.headers["Retry-After"] == "60"
        assert "WWW-Authenticate" not in r.headers

    def test_503_has_retry_after_and_no_challenge(self, client):
        r = client.get("/raise/jwks")
        assert "Retry-After" in r.headers
        assert "WWW-Authenticate" not in r.headers

    @pytest.mark.parametrize("which,leaked", [
        ("invalid", "bad signature reason"),
        ("jwks", "jwks endpoint down"),
        ("identity", "empty sub"),
    ])
    def test_detail_never_leaks_into_body(self, client, which, leaked):
        # exc.detail is server-log-only; it must appear nowhere in the response.
        r = client.get(f"/raise/{which}")
        assert leaked not in r.text

    def test_invalid_and_expired_messages_differ_only_for_expiry(self, client):
        # Disclosure rule: all non-expiry causes share one generic message; only
        # TOKEN_EXPIRED is distinguished.
        invalid = client.get("/raise/invalid").json()["error"]["message"]
        identity = client.get("/raise/identity").json()["error"]["message"]
        expired = client.get("/raise/expired").json()["error"]["message"]
        assert invalid == identity            # generic collapse
        assert expired != invalid             # the one safe distinction


# --------------------------------------------------------------------------- #
# 4. Real-app wiring: dormant /auth/me → 503 (no lifespan = Phase C dormant)
# --------------------------------------------------------------------------- #
class TestRealAppDormant:
    def test_auth_me_dormant_returns_503(self):
        # No `with` => lifespan does not run => app.state.supabase_auth is unset
        # => require_supabase_user pre-empts with JwksUnavailableError => 503.
        client = TestClient(main.app)
        r = client.get("/auth/me", headers={"Authorization": "Bearer x.y.z"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "AUTH_BACKEND_UNAVAILABLE"
        # Correlation header is echoed even on the failure response (M6 middleware).
        assert "X-Request-Id" in r.headers

    def test_auth_logout_dormant_returns_503(self):
        client = TestClient(main.app)
        r = client.post("/auth/logout", headers={"Authorization": "Bearer x.y.z"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "AUTH_BACKEND_UNAVAILABLE"
