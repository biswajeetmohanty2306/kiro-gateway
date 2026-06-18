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
Profile-body reader for Phase C (milestone M8a, READ 2).

The user-facing, NON-authorization read: it returns display fields
(``email``/``name``/``gender``/``birth_date``/``country``) plus
``onboarding_completed`` for a user whose state has ALREADY been authorized by the
authoritative READ 1 (``state_read.py`` → ``enforce_active``). It is run ONLY for
``ACTIVE`` users — a deleted/banned/missing subject is rejected before this point
(M8AuthorizationPlanV3 §3, §7.1).

Two guarantees make this RLS-respecting (D3), in priority order:
  1. PRIMARY — explicit scope: the query is ``... WHERE user_id = $1`` with ``$1``
     bound from the verified ``sub``. The read can never widen past the subject.
  2. DEFENCE-IN-DEPTH — RLS session context: the read runs as the ``authenticated``
     role (``SET LOCAL role = 'authenticated'``) with ``request.jwt.claim.sub`` set
     to the verified subject, so Postgres' ``users_select_own`` policy
     (``auth.uid() = user_id AND deleted_at IS NULL``) also applies. This is why the
     body read is NOT done over the service-role/privileged path — it must be
     RLS-confined, unlike the authoritative state read.

Because ``SET LOCAL`` is transaction-scoped, the role/claim context reverts when
the transaction ends, so this safely reuses the privileged connection without
leaving it elevated.

No top-level ``asyncpg`` import — talks only to the injected acquirer; imports
cleanly without the driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncContextManager, Optional, Protocol

from .exceptions import ProfileUnavailableError

# Body fields only — NO deleted_at / banned_until (those are authorization state,
# read authoritatively in state_read.py, never blended into the body object).
_PROFILE_SQL = (
    "SELECT user_id, email, name, gender, birth_date, country, onboarding_completed "
    "FROM public.users WHERE user_id = $1"
)

# Drop to the RLS-enforced role and bind the verified subject for auth.uid().
# `set_config(..., true)` = LOCAL (transaction-scoped), reverts on commit/rollback.
_SET_ROLE_SQL = "SET LOCAL role = 'authenticated'"
_SET_SUB_SQL = "SELECT set_config('request.jwt.claim.sub', $1, true)"


@dataclass(frozen=True)
class UserProfile:
    """
    Immutable profile BODY for an authenticated, active user (M8a READ 2).

    Carries display fields and the onboarding flag only. It holds NO authorization
    state (``deleted_at``/``banned_until`` live on
    :class:`~kiro.supabase_auth.user_state.AuthState`), and never the raw token or
    any secret. ``email`` is informational — never a key or an authz input.
    """

    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[Any] = None     # date | None (driver-native)
    country: Optional[str] = None
    onboarding_completed: bool = False


class ProfileConnection(Protocol):
    """Minimal async connection surface: a transaction + execute + fetchrow."""

    def transaction(self) -> AsyncContextManager[Any]:  # pragma: no cover - protocol
        ...

    async def execute(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...

    async def fetchrow(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...


class ProfileAcquirer(Protocol):
    """Acquires a connection as an async context manager (an asyncpg pool)."""

    def acquire(self) -> AsyncContextManager[ProfileConnection]:  # pragma: no cover - protocol
        ...


def _row_value(row: Any, key: str) -> Optional[Any]:
    """Read ``key`` from an asyncpg ``Record`` or a dict-like fake; None if absent."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def build_user_profile(row: Any, *, expected_user_id: str) -> UserProfile:
    """
    Map a ``public.users`` row to a :class:`UserProfile` (single construction path).

    Asserts the returned ``user_id`` equals the request subject — defence-in-depth
    so a misconfigured query can never hand back another user's row. Raises
    :class:`ProfileUnavailableError` (→ 500) on identity mismatch (a server-side
    integrity fault, never reflected to the client).
    """
    row_uid = _row_value(row, "user_id")
    if str(row_uid) != str(expected_user_id):
        raise ProfileUnavailableError(
            "User profile unavailable.",
            detail="profile row user_id mismatch",
        )
    return UserProfile(
        user_id=str(row_uid),
        email=_row_value(row, "email"),
        name=_row_value(row, "name"),
        gender=_row_value(row, "gender"),
        birth_date=_row_value(row, "birth_date"),
        country=_row_value(row, "country"),
        onboarding_completed=bool(_row_value(row, "onboarding_completed")),
    )


class ProfileReader:
    """
    Reads the profile BODY over a user-scoped, RLS-respecting connection (READ 2).

    Construct with the read acquirer. ``acquirer=None`` makes every read raise
    :class:`ProfileUnavailableError` (→ 500) — a route that reached the body read
    with no DB configured is a server misconfiguration, not a client error.
    """

    def __init__(self, acquirer: Optional[ProfileAcquirer] = None) -> None:
        self._acquirer = acquirer

    async def fetch_profile(self, user_id: str) -> UserProfile:
        """
        Return the :class:`UserProfile` for ``user_id`` (already-authorized active
        subject). Runs in a transaction that drops to the ``authenticated`` role and
        binds ``request.jwt.claim.sub`` (so RLS applies), then the explicitly-scoped
        ``WHERE user_id = $1`` query.

        Raises:
            ProfileUnavailableError: no row returned (unexpected for an active user
                whose state read found a present, non-deleted row — treated as a
                server-side integrity fault → 500), or a row whose ``user_id`` does
                not match the subject.
        """
        if self._acquirer is None:
            raise ProfileUnavailableError(
                "User profile unavailable.",
                detail="no user-scoped acquirer for profile read",
            )

        async with self._acquirer.acquire() as conn:
            async with conn.transaction():
                # Defence-in-depth: run as the RLS-enforced role with the verified
                # subject bound, so users_select_own applies on top of the explicit
                # WHERE. SET LOCAL reverts when the transaction ends.
                await conn.execute(_SET_ROLE_SQL)
                await conn.execute(_SET_SUB_SQL, user_id)
                row = await conn.fetchrow(_PROFILE_SQL, user_id)

        if row is None:
            # An active user's row should be visible (not deleted → passes RLS).
            # Absence here is a server-side integrity fault, not a client error.
            raise ProfileUnavailableError(
                "User profile unavailable.",
                detail="no profile row for active subject",
            )
        return build_user_profile(row, expected_user_id=user_id)
