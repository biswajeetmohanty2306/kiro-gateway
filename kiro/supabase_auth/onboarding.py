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
Onboarding completion for Phase C (milestone M8a).

The single state-changing user operation in M8a: flip
``public.users.onboarding_completed`` from ``false`` to ``true`` exactly once,
safely under concurrency (M8AuthorizationPlanV3 §8; A3, D8).

Atomic & conditional (A3): the transition is one statement —
``UPDATE ... SET onboarding_completed = true WHERE user_id = $1 AND
onboarding_completed = false RETURNING onboarding_completed``. The conditional
``WHERE`` means two concurrent submits race to update the SAME row; exactly one
performs the ``false→true`` transition (1 row returned), the other updates zero
rows. There is no divided/partial state.

Idempotent (D8): a re-submit when already onboarded is NOT a ``409``. The
zero-row UPDATE is a benign no-op; the caller reports ``200`` with the current
(already-true) state. :class:`OnboardingResult.transitioned` distinguishes a real
transition (emit the audit event) from an idempotent no-op (no audit).

Connection model: runs over the user-scoped, RLS-respecting connection (the user
updates THEIR OWN row; the deployed ``users_update_own`` policy =
``auth.uid() = user_id`` permits it). Mirrors ``profile.py``: a transaction that
drops to the ``authenticated`` role and binds the verified subject so RLS applies
on top of the explicit ``WHERE user_id = $1`` scope. Onboarding only runs for
ACTIVE users (the route depends on ``get_auth_state``), so a deleted/banned
subject never reaches here.

The paired ``AuditEvent.ONBOARDING_COMPLETED`` write is emitted by the CALLER
(the route), best-effort and OUTSIDE this transaction (M5 §6): a failed audit must
never roll back a completed onboarding. This module performs the DB transition
only and reports whether a transition happened.

No top-level ``asyncpg`` import — talks only to the injected acquirer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncContextManager, Optional, Protocol

from .exceptions import ProfileUnavailableError

# Atomic conditional transition (A3). RETURNING yields a row ONLY when the row was
# actually flipped false→true; an already-true row matches zero rows (no-op).
_TRANSITION_SQL = (
    "UPDATE public.users SET onboarding_completed = true "
    "WHERE user_id = $1 AND onboarding_completed = false "
    "RETURNING onboarding_completed"
)

# Read current state for the idempotent (zero-row) path.
_READ_SQL = "SELECT onboarding_completed FROM public.users WHERE user_id = $1"

# RLS context (transaction-scoped; reverts on commit/rollback), as in profile.py.
_SET_ROLE_SQL = "SET LOCAL role = 'authenticated'"
_SET_SUB_SQL = "SELECT set_config('request.jwt.claim.sub', $1, true)"


@dataclass(frozen=True)
class OnboardingResult:
    """
    Outcome of an onboarding submit.

    ``onboarding_completed`` is the state AFTER the call (always ``True`` on
    success — either just-flipped or already-true). ``transitioned`` is ``True``
    only when THIS call performed the ``false→true`` flip — the caller emits the
    ``ONBOARDING_COMPLETED`` audit event iff ``transitioned`` (a re-submit no-op is
    not an auditable state change).
    """

    onboarding_completed: bool
    transitioned: bool


class OnboardingConnection(Protocol):
    """Minimal async connection surface: transaction + execute + fetchrow."""

    def transaction(self) -> AsyncContextManager[Any]:  # pragma: no cover - protocol
        ...

    async def execute(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...

    async def fetchrow(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...


class OnboardingAcquirer(Protocol):
    """Acquires a connection as an async context manager (an asyncpg pool)."""

    def acquire(self) -> AsyncContextManager[OnboardingConnection]:  # pragma: no cover - protocol
        ...


def _row_value(row: Any, key: str) -> Optional[Any]:
    """Read ``key`` from an asyncpg ``Record`` or a dict-like fake; None if absent."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


async def complete_onboarding(
    acquirer: Optional[OnboardingAcquirer], user_id: str
) -> OnboardingResult:
    """
    Perform the atomic conditional onboarding transition for ``user_id``.

    Returns an :class:`OnboardingResult`:
      - real transition → ``onboarding_completed=True, transitioned=True``
      - already onboarded (idempotent no-op) → ``True, transitioned=False``

    Raises:
        ProfileUnavailableError: ``acquirer`` is ``None`` (DB unconfigured — server
            misconfiguration → 500), or the idempotent path finds no row (an active
            subject's row should exist; absence is a server-side integrity fault).
    """
    if acquirer is None:
        raise ProfileUnavailableError(
            "User profile unavailable.",
            detail="no acquirer for onboarding transition",
        )

    async with acquirer.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_SET_ROLE_SQL)
            await conn.execute(_SET_SUB_SQL, user_id)

            updated = await conn.fetchrow(_TRANSITION_SQL, user_id)
            if updated is not None:
                # We performed the false→true transition.
                return OnboardingResult(
                    onboarding_completed=bool(
                        _row_value(updated, "onboarding_completed")
                    ),
                    transitioned=True,
                )

            # Zero rows updated → already onboarded (idempotent), or row missing.
            current = await conn.fetchrow(_READ_SQL, user_id)

    if current is None:
        # An active subject's row should exist; absence is a server-side fault.
        raise ProfileUnavailableError(
            "User profile unavailable.",
            detail="no profile row on onboarding no-op",
        )
    return OnboardingResult(
        onboarding_completed=bool(_row_value(current, "onboarding_completed")),
        transitioned=False,
    )
