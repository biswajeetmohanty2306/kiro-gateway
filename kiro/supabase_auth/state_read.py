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
Authoritative user-state reader for Phase C (milestone M8a, READ 1).

This is the ONLY read that can establish authorization state. The deployed RLS
policy on ``public.users`` is ``auth.uid() = user_id AND deleted_at IS NULL`` and
the ``auth`` schema exposes no policies, so a user-scoped (RLS-respecting)
connection can see neither a soft-deleted row (the policy filters it to zero rows,
making "deleted" and "missing" indistinguishable) nor ``auth.users.banned_until``
(no grant). Authorization state therefore comes from this RLS-BYPASSING,
service-role read (M8AuthorizationPlanV3 §5.1, Option A).

Isolation (Option A, NOT a general escape hatch): the reader reuses the existing
privileged connection (the same pool the audit writer uses — ``db.py``) but
exposes EXACTLY ONE operation, :meth:`StateReader.read_auth_state`, backed by ONE
fixed, parameterized, ``user_id``-keyed query. There is no general ``execute`` /
``fetch`` surface. The query reads only the three authorization fields — never the
profile body (that is the separate user-scoped READ 2, ``profile.py``).

Fail-closed (S1 / D5): a transient read failure raises
:class:`UserStateUnavailableError` (→ 503 at M8) — the request is rejected, never
fail-open. A genuinely absent row is reported as ``row_exists=False`` (the caller
applies the D4 retry-then-500 policy); it is NOT an error here.

No top-level ``asyncpg`` import — this module talks only to the injected acquirer
(``db.py``'s ``PrivilegedConnectionPool`` in production, a fake in tests), so it
imports cleanly without the driver.
"""

from __future__ import annotations

from typing import Any, AsyncContextManager, Optional, Protocol

from loguru import logger

from .exceptions import UserStateUnavailableError
from .user_state import AuthState

# The single authoritative state query (M8a READ 1). LEFT JOIN so a present
# public.users row with no matching auth.users row still returns (banned_until
# NULL). A NULL result row (no public.users match) => the user has no profile
# (row_exists False). Parameterized ($1 = user_id); never string-interpolated.
_STATE_SQL = (
    "SELECT u.deleted_at AS deleted_at, a.banned_until AS banned_until "
    "FROM public.users u "
    "LEFT JOIN auth.users a ON a.id = u.user_id "
    "WHERE u.user_id = $1"
)


class StateConnection(Protocol):
    """Minimal async connection surface used here: a single ``fetchrow``."""

    async def fetchrow(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...


class StateAcquirer(Protocol):
    """Acquires a privileged connection as an async context manager (asyncpg pool)."""

    def acquire(self) -> AsyncContextManager[StateConnection]:  # pragma: no cover - protocol
        ...


def _row_value(row: Any, key: str) -> Optional[Any]:
    """Read ``key`` from an asyncpg ``Record`` (mapping access) or a dict-like fake."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


class StateReader:
    """
    Reads the authoritative :class:`AuthState` for a ``user_id`` over the
    privileged (RLS-bypassing) connection. Single-purpose by design.

    Construct with the privileged acquirer (``db.py``'s ``PrivilegedConnectionPool``).
    When the acquirer is ``None`` the reader is **non-functional** and every read
    FAILS CLOSED with :class:`UserStateUnavailableError` — a deployment that
    enabled user-auth routes but configured no DB cannot silently allow requests
    through an unenforceable gate.
    """

    def __init__(self, acquirer: Optional[StateAcquirer] = None) -> None:
        self._acquirer = acquirer

    async def read_auth_state(self, user_id: str) -> AuthState:
        """
        Return the :class:`AuthState` for ``user_id`` (the verified ``sub``).

        Runs exactly one parameterized query. A missing row → ``AuthState`` with
        ``row_exists=False`` (NOT an error — D4 missing-profile is the caller's
        concern). Any DB/connection failure → :class:`UserStateUnavailableError`
        (→ 503, fail closed): the gate never proceeds on an unreadable state.
        """
        if self._acquirer is None:
            # No privileged connection => the gate is unenforceable. Fail closed.
            raise UserStateUnavailableError(
                "User state is unavailable.",
                detail="no privileged acquirer for state read",
            )

        try:
            async with self._acquirer.acquire() as conn:
                row = await conn.fetchrow(_STATE_SQL, user_id)
        except Exception as exc:  # noqa: BLE001 — any read failure fails closed.
            # Log the type only (never the value); surface a transient 503.
            logger.warning(
                "user-state read failed user_id_present={} error={}",
                bool(user_id),
                type(exc).__name__,
            )
            raise UserStateUnavailableError(
                "User state is unavailable.",
                detail=f"state read error: {type(exc).__name__}",
            ) from exc

        if row is None:
            # No public.users row for this verified sub → missing profile (D4).
            return AuthState(user_id=user_id, row_exists=False)

        return AuthState(
            user_id=user_id,
            row_exists=True,
            deleted_at=_row_value(row, "deleted_at"),
            banned_until=_row_value(row, "banned_until"),
        )
