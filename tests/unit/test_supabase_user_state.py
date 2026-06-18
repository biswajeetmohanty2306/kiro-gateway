# -*- coding: utf-8 -*-

"""
Unit tests for the pure authorization gate
(kiro/supabase_auth/user_state.py, M8a).

No I/O: deterministic clock via now_fn. Verifies derive_state precedence and the
enforce_active matrix (ACTIVE proceeds; deleted/banned/unknown raise; missing row
→ ProfileUnavailableError; expired ban → ACTIVE; fail-closed on indeterminate).
"""

from datetime import datetime, timezone, timedelta

import pytest

from kiro.supabase_auth.user_state import (
    AuthState,
    UserState,
    derive_state,
    enforce_active,
)
from kiro.supabase_auth.exceptions import (
    AccountDisabledError,
    ProfileUnavailableError,
    SupabaseAuthzError,
    UserBannedError,
    UserDeletedError,
)

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _now():
    return _NOW


def _state(**kw):
    return AuthState(user_id="u1", row_exists=True, **kw)


class TestDeriveState:
    def test_active_when_no_flags(self):
        assert derive_state(_state(), now_fn=_now) is UserState.ACTIVE

    def test_deleted_when_deleted_at_set(self):
        assert derive_state(_state(deleted_at=_NOW), now_fn=_now) is UserState.DELETED

    def test_banned_when_banned_until_future(self):
        s = _state(banned_until=_NOW + timedelta(hours=1))
        assert derive_state(s, now_fn=_now) is UserState.BANNED

    def test_expired_ban_is_active(self):
        s = _state(banned_until=_NOW - timedelta(seconds=1))
        assert derive_state(s, now_fn=_now) is UserState.ACTIVE

    def test_deleted_takes_precedence_over_ban(self):
        s = _state(deleted_at=_NOW, banned_until=_NOW + timedelta(hours=1))
        assert derive_state(s, now_fn=_now) is UserState.DELETED

    def test_non_datetime_banned_until_is_unknown(self):
        assert derive_state(_state(banned_until="soon"), now_fn=_now) is UserState.UNKNOWN

    def test_non_datetime_deleted_at_is_unknown(self):
        assert derive_state(_state(deleted_at="yes"), now_fn=_now) is UserState.UNKNOWN

    def test_naive_datetime_banned_until_treated_as_utc(self):
        # A naive future datetime is treated as UTC → still BANNED.
        naive_future = (_NOW + timedelta(hours=1)).replace(tzinfo=None)
        assert derive_state(_state(banned_until=naive_future), now_fn=_now) is UserState.BANNED


class TestEnforceActive:
    def test_active_returns_active(self):
        assert enforce_active(_state(), now_fn=_now) is UserState.ACTIVE

    def test_deleted_raises(self):
        with pytest.raises(UserDeletedError):
            enforce_active(_state(deleted_at=_NOW), now_fn=_now)

    def test_banned_raises(self):
        with pytest.raises(UserBannedError):
            enforce_active(_state(banned_until=_NOW + timedelta(hours=1)), now_fn=_now)

    def test_unknown_fails_closed_account_disabled(self):
        with pytest.raises(AccountDisabledError):
            enforce_active(_state(banned_until="garbage"), now_fn=_now)

    def test_missing_row_raises_profile_unavailable(self):
        with pytest.raises(ProfileUnavailableError):
            enforce_active(AuthState(user_id="u1", row_exists=False), now_fn=_now)

    def test_expired_ban_proceeds(self):
        s = _state(banned_until=_NOW - timedelta(hours=1))
        assert enforce_active(s, now_fn=_now) is UserState.ACTIVE

    @pytest.mark.parametrize("exc", [UserDeletedError, UserBannedError, AccountDisabledError])
    def test_denials_are_authz_errors(self, exc):
        # All 403 denials are SupabaseAuthzError (→ 403 mapping); ProfileUnavailable
        # is NOT (it's a 500 server fault).
        assert issubclass(exc, SupabaseAuthzError)
        assert not issubclass(ProfileUnavailableError, SupabaseAuthzError)


class TestNoStateFromJwt:
    def test_module_is_pure_no_db_no_fastapi(self):
        import kiro.supabase_auth.user_state as m
        src = m.__file__
        assert src.endswith("user_state.py")
        # No DB/FastAPI imports leaked into the pure gate module.
        assert not hasattr(m, "asyncpg")
        assert not hasattr(m, "Request")
