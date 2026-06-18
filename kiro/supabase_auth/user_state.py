# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
User-state model and the authorization gate for Phase C (milestone M8a).

PURE module: no FastAPI, no database, no network — zero I/O (mirrors M4's
``user.py``). It turns the authoritative state read (M8a READ 1, ``state_read.py``)
into an allow/deny decision.

Why this lives apart from the profile body (M8AuthorizationPlanV3 §0/§3): the
deployed RLS policy on ``public.users`` is ``auth.uid() = user_id AND deleted_at
IS NULL``, and the ``auth`` schema exposes no policies. So the user-scoped read
can see *neither* ``deleted_at`` (it filters deleted rows to zero) *nor*
``auth.users.banned_until``. Authorization state therefore comes from an
authoritative, RLS-bypassing read and is modeled here, separate from the
RLS-confined profile body.

Trust rule (S1): state is DB-sourced ONLY. Nothing here reads the JWT or any
metadata — a valid, unexpired token for a just-banned/just-deleted user is
rejected because the truth lives in the database, not the token.

Fail-closed (M4-D4): only an explicitly ``ACTIVE`` state proceeds. A missing row
is a server fault (``ProfileUnavailableError`` → 500, handled by the caller's D4
retry, not here); anything indeterminate denies (``AccountDisabledError`` → 403).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from .exceptions import (
    AccountDisabledError,
    ProfileUnavailableError,
    UserBannedError,
    UserDeletedError,
)


class UserState(str, Enum):
    """
    The closed set of authorization states M8a recognizes (V3 §4.1).

    Only the states the *deployed schema* can express are modeled: ``DELETED``
    (``public.users.deleted_at``) and ``BANNED`` (``auth.users.banned_until``),
    plus ``ACTIVE`` (the default) and ``UNKNOWN`` (the fail-closed bucket for an
    indeterminate/unrecognized row). ``DISABLED`` is deliberately absent — there
    is no source column for it (M8 preconditions report; D-B2).
    """

    ACTIVE = "active"      # row present, not deleted, not currently banned — the ONLY pass state
    BANNED = "banned"      # auth.users.banned_until IS NOT NULL AND in the future
    DELETED = "deleted"    # public.users.deleted_at IS NOT NULL
    UNKNOWN = "unknown"    # indeterminate / unrecognized → fail closed


@dataclass(frozen=True)
class AuthState:
    """
    The authorization-state inputs from the authoritative read (M8a READ 1).

    Immutable and PII-free: it carries no email, name, or any profile-body field
    (those live on :class:`~kiro.supabase_auth.profile.UserProfile`, read on the
    separate user-scoped path only for ACTIVE users). ``deleted_at`` /
    ``banned_until`` are the raw timestamps from the DB (or ``None``); the
    derivation into a :class:`UserState` happens in :func:`derive_state`.
    """

    user_id: str
    row_exists: bool
    deleted_at: Optional[datetime] = None
    banned_until: Optional[datetime] = None


def _now_utc() -> datetime:
    """Default clock: tz-aware UTC (so comparisons with tz-aware DB timestamps work)."""
    return datetime.now(timezone.utc)


def _is_future(value: object, now: datetime) -> Optional[bool]:
    """
    Return True if ``value`` is a datetime strictly in the future, False if it is a
    datetime in the past/now, or ``None`` if ``value`` is not a usable datetime
    (an indeterminate value the caller must treat as UNKNOWN — fail closed).
    """
    if not isinstance(value, datetime):
        return None
    # Compare safely across naive/aware: treat a naive DB value as UTC.
    candidate = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return candidate > now


def derive_state(
    state: AuthState, *, now_fn: Callable[[], datetime] = _now_utc
) -> UserState:
    """
    Map an :class:`AuthState` (with ``row_exists`` already True) to a
    :class:`UserState`. Total and deterministic given ``now_fn``.

    Precedence (V3 §4.2): ``DELETED`` (deleted_at set) → ``BANNED`` (banned_until
    in the future) → ``ACTIVE``. An **expired** ``banned_until`` is NOT a ban
    (past). A field present but not a usable datetime → ``UNKNOWN`` (fail closed).

    Caller contract: ``row_exists`` must be True here — the missing-row case is a
    server fault handled by :func:`enforce_active`, not a ``UserState``.
    """
    now = now_fn()

    if state.deleted_at is not None:
        # deleted_at present: confirm it is a real timestamp; a non-datetime value
        # is indeterminate → fail closed rather than silently treating as active.
        if isinstance(state.deleted_at, datetime):
            return UserState.DELETED
        return UserState.UNKNOWN

    if state.banned_until is not None:
        future = _is_future(state.banned_until, now)
        if future is None:
            return UserState.UNKNOWN     # unusable value → fail closed
        if future:
            return UserState.BANNED
        # else: ban expired → fall through to ACTIVE.

    return UserState.ACTIVE


def enforce_active(
    state: AuthState, *, now_fn: Callable[[], datetime] = _now_utc
) -> UserState:
    """
    The authorization gate (V3 §4.3). Returns :data:`UserState.ACTIVE` when the
    request may proceed; otherwise raises a typed authz/server error. Performs NO
    HTTP mapping (that is M8's handler, ``http.py``).

    Raises:
        ProfileUnavailableError: ``row_exists`` is False — a valid JWT with no
            ``public.users`` row. A SERVER fault (broken Phase A trigger), NOT an
            authorization decision and NOT a 403. The caller (dependency) owns the
            single bounded retry before this surfaces (D4); by the time it reaches
            here un-retried-away, it is a 500.
        UserDeletedError / UserBannedError: soft-deleted / currently banned → 403.
        AccountDisabledError: any indeterminate/unknown state → 403 (fail closed,
            M4-D4). Banned/deleted/unknown all collapse to one client code at M8.

    Returns:
        ``UserState.ACTIVE`` (the only state that proceeds).
    """
    if not state.row_exists:
        # Missing row: not authz — a server-side fault per D4. The caller's retry
        # has already been exhausted by the time enforce_active is invoked.
        raise ProfileUnavailableError(
            "User profile unavailable.",
            detail="no public.users row for verified sub",
        )

    resolved = derive_state(state, now_fn=now_fn)

    if resolved is UserState.ACTIVE:
        return resolved
    if resolved is UserState.DELETED:
        raise UserDeletedError("Account is not available.", detail="deleted_at set")
    if resolved is UserState.BANNED:
        raise UserBannedError("Account is not available.", detail="banned_until in future")
    # UserState.UNKNOWN — fail closed.
    raise AccountDisabledError(
        "Account is not available.", detail=f"indeterminate state ({resolved.value})"
    )
