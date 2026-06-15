# -*- coding: utf-8 -*-

"""
Unit + app-level tests for the M1 CORS hardening (S5).

Covers:
  - The standalone CORS policy resolver (get_cors_policy) — pure, no app.
  - App-level header behavior via TestClient on a minimal app that applies the
    resolver exactly as main.py does (kept minimal so it does not trigger the
    real app's lifespan / account initialization).
  - The dual-path / no-SUPABASE_URL boot guarantee.

Decisions locked for M1:
  - M1-D1 = NO  -> allow_credentials is always False.
  - M1-D2       -> reuse SupabaseAuthConfigError.
  - M1-D3       -> empty allowlist is valid (credentials disabled).
  - M1-D4       -> no USER_AUTH_CORS_ALLOW_CREDENTIALS env var.
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from kiro import config as raw
from kiro.supabase_auth.config import (
    CORS_ALLOW_CREDENTIALS,
    CorsPolicy,
    SupabaseAuthConfigError,
    get_cors_policy,
)


@pytest.fixture
def set_origins(monkeypatch):
    """Override USER_AUTH_CORS_ALLOWED_ORIGINS on kiro.config raw values."""
    def _apply(value: str):
        monkeypatch.setattr(
            raw, "USER_AUTH_CORS_ALLOWED_ORIGINS", value, raising=False
        )
    return _apply


def _make_app(policy: CorsPolicy) -> FastAPI:
    """Minimal app wired with the resolved CORS policy, like main.py."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(policy.allow_origins),
        allow_credentials=policy.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


# =============================================================================
# Resolver unit tests (pure, no app)
# =============================================================================

class TestCorsResolver:
    """get_cors_policy() parsing and validation."""

    def test_empty_is_valid_with_no_credentials(self, set_origins):
        """M1-D3: empty allowlist is valid because credentials are disabled."""
        set_origins("")
        policy = get_cors_policy()
        assert policy.allow_origins == ()
        assert policy.allow_credentials is False

    def test_credentials_always_false(self, set_origins):
        """M1-D1: allow_credentials is locked False regardless of origins."""
        set_origins("https://app.example.com")
        assert get_cors_policy().allow_credentials is False
        assert CORS_ALLOW_CREDENTIALS is False

    def test_single_origin(self, set_origins):
        set_origins("https://app.example.com")
        assert get_cors_policy().allow_origins == ("https://app.example.com",)

    def test_multiple_origins_order_preserved(self, set_origins):
        set_origins("http://localhost:4321,https://app.example.com")
        assert get_cors_policy().allow_origins == (
            "http://localhost:4321",
            "https://app.example.com",
        )

    def test_duplicates_deduped(self, set_origins):
        """R3: duplicates removed silently, order preserved."""
        set_origins("https://a.example.com, https://a.example.com")
        assert get_cors_policy().allow_origins == ("https://a.example.com",)

    def test_whitespace_trimmed_between_entries(self, set_origins):
        set_origins("  http://localhost:4321 , https://app.example.com  ")
        assert get_cors_policy().allow_origins == (
            "http://localhost:4321",
            "https://app.example.com",
        )

    def test_wildcard_rejected(self, set_origins):
        """R1: '*' is forbidden — the S5 exposure must be unconfigurable."""
        set_origins("*")
        with pytest.raises(SupabaseAuthConfigError, match="wildcard"):
            get_cors_policy()

    def test_wildcard_mixed_rejected(self, set_origins):
        set_origins("https://app.example.com,*")
        with pytest.raises(SupabaseAuthConfigError, match="wildcard"):
            get_cors_policy()

    @pytest.mark.parametrize(
        "bad",
        [
            "https://app.example.com/",          # trailing slash
            "https://app.example.com/path",      # path
            "ftp://app.example.com",             # bad scheme
            "app.example.com",                   # no scheme
            "https://app.example.com?x=1",       # query
            "https://app.example.com#frag",      # fragment
        ],
    )
    def test_malformed_origin_rejected(self, set_origins, bad):
        """R2: each origin must be a clean scheme://host[:port]."""
        set_origins(bad)
        with pytest.raises(SupabaseAuthConfigError):
            get_cors_policy()

    def test_host_with_port_allowed(self, set_origins):
        set_origins("http://localhost:8000")
        assert get_cors_policy().allow_origins == ("http://localhost:8000",)


# =============================================================================
# App-level header behavior (TestClient)
# =============================================================================

class TestCorsHeaders:
    """Observable CORS response headers for the resolved policy."""

    def test_listed_origin_is_allowed(self, set_origins):
        set_origins("https://app.example.com")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.get("/ping", headers={"Origin": "https://app.example.com"})
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin")
            == "https://app.example.com"
        )

    def test_unlisted_origin_is_denied(self, set_origins):
        set_origins("https://app.example.com")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.get("/ping", headers={"Origin": "https://evil.example.com"})
        # Request still succeeds server-side, but no ACAO header is granted.
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") is None

    def test_no_credentialed_wildcard_regression(self, set_origins):
        """
        The S5 lock: the response must never pair ACAO '*' with
        Access-Control-Allow-Credentials: true.
        """
        set_origins("https://app.example.com")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.get("/ping", headers={"Origin": "https://app.example.com"})
        acao = resp.headers.get("access-control-allow-origin")
        acac = resp.headers.get("access-control-allow-credentials")
        assert not (acao == "*" and acac == "true")
        # Credentials disabled -> the credentials header is not affirmatively set.
        assert acac != "true"

    def test_preflight_listed_origin_granted(self, set_origins):
        set_origins("https://app.example.com")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.options(
            "/ping",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)
        assert (
            resp.headers.get("access-control-allow-origin")
            == "https://app.example.com"
        )

    def test_preflight_unlisted_origin_not_granted(self, set_origins):
        set_origins("https://app.example.com")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.options(
            "/ping",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") is None

    def test_request_without_origin_unaffected(self, set_origins):
        """Non-browser clients (no Origin header) are unaffected (proxy surface)."""
        set_origins("")
        client = TestClient(_make_app(get_cors_policy()))
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# =============================================================================
# Dual-path / boot guarantees
# =============================================================================

class TestBootGuarantees:
    """CORS hardening must not require SUPABASE_URL and must fail fast on '*'."""

    def test_resolver_does_not_require_supabase_url(self, monkeypatch, set_origins):
        """
        Acceptance #3: a non-Supabase deployment still boots. The resolver must
        work with SUPABASE_URL unset.
        """
        monkeypatch.setattr(raw, "SUPABASE_URL", "", raising=False)
        set_origins("https://app.example.com")
        policy = get_cors_policy()  # must NOT raise about SUPABASE_URL
        assert policy.allow_origins == ("https://app.example.com",)

    def test_wildcard_fails_fast_at_resolution(self, set_origins):
        """
        Acceptance #2: '*' is rejected when the policy is resolved — which
        main.py does at app-construction time (covered on both launch paths).
        """
        set_origins("*")
        with pytest.raises(SupabaseAuthConfigError):
            get_cors_policy()
