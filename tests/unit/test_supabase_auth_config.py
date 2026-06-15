# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C Supabase user-auth config object (milestone M0).

Verifies validation, derivation, and the two security invariants M0 must lock:
  - The accepted-algorithm set is fixed by the configured scheme (S2) and cannot
    be widened by input.
  - The CORS validator rejects a wildcard origin (S5).

These tests mutate the RAW values on ``kiro.config`` (where the env reads live)
and rebuild the validated object, mirroring the reload pattern used by the
existing ``tests/unit/test_config.py``.
"""

import pytest

from kiro import config as raw
from kiro.supabase_auth import config as sa_config
from kiro.supabase_auth.config import (
    SupabaseAuthConfig,
    SupabaseAuthConfigError,
    build_config,
    get_config,
    reset_config_cache,
)


# Raw attributes the config object reads, with sane asymmetric defaults.
_DEFAULT_RAW = {
    "SUPABASE_URL": "https://abcdefghijklmno.supabase.co",
    "SUPABASE_PROJECT_REF": "abcdefghijklmno",
    "SUPABASE_JWT_ALG_SCHEME": "asymmetric",
    "SUPABASE_JWT_SECRET": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "SUPABASE_DB_URL": "",
    "SUPABASE_EXPECTED_AUD": "authenticated",
    "SUPABASE_EXPECTED_ISS": "",
    "USER_AUTH_CORS_ALLOWED_ORIGINS": "",
    "USER_AUTH_JWT_LEEWAY_SECONDS": 60,
    "USER_AUTH_JWKS_REFRESH_COOLDOWN_SECONDS": 60,
    "USER_AUTH_AUTH_FAILURE_RATE_LIMIT": 20,
}


@pytest.fixture
def set_raw(monkeypatch):
    """Apply a dict of overrides onto kiro.config raw values, then reset cache."""
    def _apply(**overrides):
        merged = {**_DEFAULT_RAW, **overrides}
        for key, value in merged.items():
            monkeypatch.setattr(raw, key, value, raising=False)
        reset_config_cache()
        return merged
    yield _apply
    reset_config_cache()


class TestAsymmetricDefaults:
    """Asymmetric (D1-confirmed) scheme produces a coherent config."""

    def test_builds_with_minimal_asymmetric_config(self, set_raw):
        set_raw()
        cfg = build_config()
        assert isinstance(cfg, SupabaseAuthConfig)
        assert cfg.scheme == "asymmetric"
        assert cfg.jwt_secret == ""

    def test_jwks_url_derived_from_supabase_url_only(self, set_raw):
        """S2: JWKS URL comes from SUPABASE_URL, never from a token."""
        set_raw(SUPABASE_URL="https://proj.supabase.co/")  # trailing slash stripped
        cfg = build_config()
        assert cfg.jwks_url == "https://proj.supabase.co/auth/v1/.well-known/jwks.json"

    def test_issuer_derived_when_not_overridden(self, set_raw):
        set_raw(SUPABASE_URL="https://proj.supabase.co", SUPABASE_EXPECTED_ISS="")
        cfg = build_config()
        assert cfg.expected_iss == "https://proj.supabase.co/auth/v1"

    def test_explicit_issuer_override_respected(self, set_raw):
        set_raw(SUPABASE_EXPECTED_ISS="https://custom.example/auth/v1")
        cfg = build_config()
        assert cfg.expected_iss == "https://custom.example/auth/v1"


class TestAlgorithmSetIsFixed:
    """S2: the accepted-alg set is fixed by scheme and cannot be widened."""

    def test_asymmetric_alg_set(self, set_raw):
        set_raw(SUPABASE_JWT_ALG_SCHEME="asymmetric")
        cfg = build_config()
        assert cfg.accepted_algorithms == frozenset({"ES256", "RS256"})

    def test_symmetric_alg_set(self, set_raw):
        set_raw(SUPABASE_JWT_ALG_SCHEME="symmetric", SUPABASE_JWT_SECRET="shh")
        cfg = build_config()
        assert cfg.accepted_algorithms == frozenset({"HS256"})

    def test_alg_set_is_immutable_frozenset(self, set_raw):
        set_raw()
        cfg = build_config()
        assert isinstance(cfg.accepted_algorithms, frozenset)
        with pytest.raises(AttributeError):
            cfg.accepted_algorithms.add("none")  # type: ignore[attr-defined]

    def test_none_algorithm_never_present(self, set_raw):
        for scheme, secret in (("asymmetric", ""), ("symmetric", "shh")):
            set_raw(SUPABASE_JWT_ALG_SCHEME=scheme, SUPABASE_JWT_SECRET=secret)
            cfg = build_config()
            assert "none" not in cfg.accepted_algorithms
            assert "HS256" not in cfg.accepted_algorithms or scheme == "symmetric"


class TestCorsRejectsWildcard:
    """S5: a wildcard origin is rejected for the credentialed user surface."""

    def test_wildcard_rejected(self, set_raw):
        set_raw(USER_AUTH_CORS_ALLOWED_ORIGINS="*")
        with pytest.raises(SupabaseAuthConfigError, match="wildcard"):
            build_config()

    def test_wildcard_among_others_rejected(self, set_raw):
        set_raw(USER_AUTH_CORS_ALLOWED_ORIGINS="https://app.example.com, *")
        with pytest.raises(SupabaseAuthConfigError, match="wildcard"):
            build_config()

    def test_exact_origins_parsed_and_deduped(self, set_raw):
        set_raw(
            USER_AUTH_CORS_ALLOWED_ORIGINS=(
                "http://localhost:4321, https://app.example.com, http://localhost:4321"
            )
        )
        cfg = build_config()
        assert cfg.cors_allowed_origins == (
            "http://localhost:4321",
            "https://app.example.com",
        )

    def test_empty_origins_allowed(self, set_raw):
        set_raw(USER_AUTH_CORS_ALLOWED_ORIGINS="")
        cfg = build_config()
        assert cfg.cors_allowed_origins == ()


class TestRequiredAndInvalidValues:
    """Missing/invalid required values fail fast with a clear error."""

    def test_missing_supabase_url(self, set_raw):
        set_raw(SUPABASE_URL="")
        with pytest.raises(SupabaseAuthConfigError, match="SUPABASE_URL"):
            build_config()

    def test_symmetric_without_secret(self, set_raw):
        set_raw(SUPABASE_JWT_ALG_SCHEME="symmetric", SUPABASE_JWT_SECRET="")
        with pytest.raises(SupabaseAuthConfigError, match="SUPABASE_JWT_SECRET"):
            build_config()

    def test_invalid_scheme(self, set_raw):
        set_raw(SUPABASE_JWT_ALG_SCHEME="rsa-magic")
        with pytest.raises(SupabaseAuthConfigError, match="SUPABASE_JWT_ALG_SCHEME"):
            build_config()

    def test_negative_leeway(self, set_raw):
        set_raw(USER_AUTH_JWT_LEEWAY_SECONDS=-1)
        with pytest.raises(SupabaseAuthConfigError, match="LEEWAY"):
            build_config()


class TestLazyCaching:
    """get_config() is a lazy, cacheable singleton; reset clears it."""

    def test_get_config_caches(self, set_raw):
        set_raw()
        first = get_config()
        second = get_config()
        assert first is second

    def test_reset_rebuilds(self, set_raw):
        set_raw(SUPABASE_URL="https://one.supabase.co")
        first = get_config()
        set_raw(SUPABASE_URL="https://two.supabase.co")
        second = get_config()
        assert first is not second
        assert second.supabase_url == "https://two.supabase.co"


def test_importing_package_does_not_build_config(monkeypatch):
    """
    Importing the package/module must not read or validate env (lazy by design).
    A broken/empty SUPABASE_URL must not raise merely on import.
    """
    monkeypatch.setattr(raw, "SUPABASE_URL", "", raising=False)
    reset_config_cache()
    # Re-import is a no-op (already imported), but referencing the module's
    # public symbols must not have triggered build_config at import time.
    import importlib

    mod = importlib.import_module("kiro.supabase_auth.config")
    assert hasattr(mod, "get_config")
    # Building explicitly with empty URL is what raises — not the import.
    with pytest.raises(SupabaseAuthConfigError):
        mod.build_config()
    reset_config_cache()
