# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C AuthenticatedUser identity object
(kiro/supabase_auth/user.py, M4).

Pure-unit-only (design §8): no network, no DB, no fakes beyond VerifiedClaims
fixtures. Covers the mapping rules (CM-1…CM-5), the opaque-metadata / trust
boundary (CM-4 / TB-1), invalid identity (CM-1), immutability, no-leak,
determinism/purity, and the negative "no authz surface" assertion that proves
M4 introduced no roles, no user-state, and no authorization gate.
"""

from types import MappingProxyType

import pytest

from kiro.supabase_auth.user import (
    AuthenticatedUser,
    build_authenticated_user,
    InvalidIdentityError,
)
from kiro.supabase_auth.verifier import VerifiedClaims
from kiro.supabase_auth.exceptions import SupabaseAuthError


def make_claims(**overrides) -> VerifiedClaims:
    """Build a VerifiedClaims with sane defaults; override any field."""
    base = dict(
        sub="11111111-1111-1111-1111-111111111111",
        aud="authenticated",
        iss="https://proj.supabase.co/auth/v1",
        iat=1_700_000_000,
        exp=1_700_003_600,
        email="user@example.com",
        app_metadata=MappingProxyType({"provider": "google"}),
        user_metadata=MappingProxyType({"name": "Test"}),
    )
    base.update(overrides)
    return VerifiedClaims(**base)


class TestMapping:
    """CM-1…CM-3: the core field mapping."""

    def test_maps_all_identity_fields(self):
        user = build_authenticated_user(make_claims())
        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "11111111-1111-1111-1111-111111111111"  # CM-1
        assert user.email == "user@example.com"                        # CM-2
        assert user.claims_issued_at == 1_700_000_000                  # CM-3
        assert user.claims_expires_at == 1_700_003_600                 # CM-3

    def test_user_id_is_sub(self):
        user = build_authenticated_user(make_claims(sub="abc-123"))
        assert user.user_id == "abc-123"

    def test_iat_exp_coerced_to_int(self):
        # VerifiedClaims types them as int already; assert the mapper keeps int.
        user = build_authenticated_user(make_claims(iat=1700, exp=9999))
        assert user.claims_issued_at == 1700
        assert user.claims_expires_at == 9999
        assert isinstance(user.claims_issued_at, int)
        assert isinstance(user.claims_expires_at, int)


class TestEmailHandling:
    """CM-2: email is informational, optional, never a key."""

    def test_email_present(self):
        user = build_authenticated_user(make_claims(email="a@b.com"))
        assert user.email == "a@b.com"

    def test_email_absent_is_none(self):
        # VerifiedClaims allows email=None (optional claim).
        user = build_authenticated_user(make_claims(email=None))
        assert user.email is None

    def test_email_non_str_becomes_none(self):
        # Defensive: a non-str slipping through maps to None, never raises.
        user = build_authenticated_user(make_claims(email=12345))
        assert user.email is None

    def test_email_is_not_the_identity_key(self):
        # TB-2: identity is sub, never email — even if email looks privileged.
        user = build_authenticated_user(
            make_claims(sub="real-id", email="admin@corp.com")
        )
        assert user.user_id == "real-id"
        assert user.user_id != user.email


class TestOpaqueMetadata:
    """CM-4 / TB-1: metadata passes through opaque and uninterpreted."""

    def test_metadata_passes_through_identically(self):
        claims = make_claims(
            app_metadata=MappingProxyType({"provider": "google", "x": 1}),
            user_metadata=MappingProxyType({"name": "Test", "y": [2, 3]}),
        )
        user = build_authenticated_user(claims)
        assert dict(user.app_metadata) == {"provider": "google", "x": 1}
        assert dict(user.user_metadata) == {"name": "Test", "y": [2, 3]}

    def test_planted_role_in_app_metadata_is_not_interpreted(self):
        # TB-1: a role planted in app_metadata grants nothing and surfaces no
        # roles concept — M4 reads no key from it.
        claims = make_claims(app_metadata=MappingProxyType({"role": "admin"}))
        user = build_authenticated_user(claims)
        assert not hasattr(user, "roles")
        assert not hasattr(user, "role")
        assert not hasattr(user, "is_admin")
        # The blob is still carried verbatim, just uninterpreted.
        assert user.app_metadata["role"] == "admin"

    def test_planted_roles_in_user_metadata_is_not_interpreted(self):
        # TB-1: user-controlled metadata never influences anything in M4.
        claims = make_claims(user_metadata=MappingProxyType({"roles": ["admin"]}))
        user = build_authenticated_user(claims)
        assert not hasattr(user, "roles")
        assert user.user_metadata["roles"] == ["admin"]

    def test_missing_metadata_defaults_to_empty_mapping(self):
        # Defensive non-M2 path: non-dict metadata becomes an empty mapping.
        claims = make_claims(app_metadata=None, user_metadata=None)
        user = build_authenticated_user(claims)
        assert dict(user.app_metadata) == {}
        assert dict(user.user_metadata) == {}


class TestInvalidIdentity:
    """CM-1: only sub problems raise, and only InvalidIdentityError."""

    def test_empty_sub_raises(self):
        with pytest.raises(InvalidIdentityError):
            build_authenticated_user(make_claims(sub=""))

    def test_non_str_sub_raises(self):
        with pytest.raises(InvalidIdentityError):
            build_authenticated_user(make_claims(sub=12345))

    def test_none_sub_raises(self):
        with pytest.raises(InvalidIdentityError):
            build_authenticated_user(make_claims(sub=None))

    def test_invalid_identity_is_supabase_auth_error(self):
        # Inherits the M2 base so existing handling/detail discipline applies.
        with pytest.raises(SupabaseAuthError):
            build_authenticated_user(make_claims(sub=""))

    def test_valid_sub_does_not_raise(self):
        # Sanity: a well-formed sub maps cleanly.
        user = build_authenticated_user(make_claims(sub="ok"))
        assert user.user_id == "ok"


class TestImmutability:
    """frozen dataclass + read-only mappings."""

    def test_cannot_reassign_field(self):
        user = build_authenticated_user(make_claims())
        with pytest.raises(Exception):
            user.user_id = "tampered"  # frozen dataclass

    def test_cannot_mutate_app_metadata(self):
        user = build_authenticated_user(make_claims())
        with pytest.raises(Exception):
            user.app_metadata["injected"] = "x"  # read-only mapping

    def test_cannot_mutate_user_metadata(self):
        user = build_authenticated_user(make_claims())
        with pytest.raises(Exception):
            user.user_metadata["injected"] = "x"  # read-only mapping


class TestNoLeak:
    """Disclosure discipline: no token/secret/email-value leakage."""

    def test_repr_carries_no_token_or_secret(self):
        user = build_authenticated_user(make_claims())
        text = repr(user)
        # The object only ever held claim-derived identity; assert no JWT-ish
        # material could appear (there is no token field to leak).
        assert "eyJ" not in text  # no JWT segment
        assert not hasattr(user, "token")
        assert not hasattr(user, "raw_token")

    def test_exception_detail_has_no_claim_values(self):
        try:
            build_authenticated_user(make_claims(sub=""))
        except InvalidIdentityError as exc:
            # detail is a short reason, never the email/sub value or token.
            assert exc.detail == "empty/non-str sub"
            assert "user@example.com" not in (exc.detail or "")


class TestDeterminismAndPurity:
    """Same input → equal output; no I/O inside the mapper."""

    def test_deterministic_equal_output(self):
        a = build_authenticated_user(make_claims())
        b = build_authenticated_user(make_claims())
        assert a == b  # frozen dataclass equality

    def test_no_io_during_mapping(self, monkeypatch):
        # Purity proof: socket creation would raise if the mapper touched the
        # network. (It does no I/O, so this passes.)
        import socket

        def _no_socket(*args, **kwargs):
            raise AssertionError("mapper attempted network I/O")

        monkeypatch.setattr(socket, "socket", _no_socket)
        user = build_authenticated_user(make_claims())
        assert user.user_id


class TestNoAuthzSurface:
    """Negative: M4 introduced no roles, no user-state, no gate (AC-9)."""

    def test_authenticated_user_has_no_role_or_state_fields(self):
        user = build_authenticated_user(make_claims())
        for forbidden in ("roles", "role", "state", "status", "is_banned", "is_active"):
            assert not hasattr(user, forbidden), f"M4 must not add {forbidden!r}"

    def test_module_exposes_no_authorization_symbols(self):
        import kiro.supabase_auth.user as m

        for forbidden in (
            "UserState",
            "UserStateProvider",
            "authorize",
            "UserBannedError",
            "UserInactiveError",
            "UserStateUnavailableError",
        ):
            assert not hasattr(m, forbidden), f"M4 must not define {forbidden!r}"

    def test_factory_takes_only_verified_claims(self):
        # No state argument, no provider — single-arg construction path.
        import inspect

        sig = inspect.signature(build_authenticated_user)
        params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        assert len(params) == 1
        assert params[0].name == "claims"
