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
Service-role Postgres pool adapter for privileged Phase C DB access (M6 + M8a).

Provides the ``ConnectionAcquirer`` that M5's ``AuditLogger`` consumes — backed
by an ``asyncpg`` connection pool built from ``SUPABASE_DB_URL``. As of M8a the
SAME privileged pool also backs the authoritative user-state read
(``state_read.py``): the deployed RLS (`auth.uid()=user_id AND deleted_at IS
NULL`) and the policy-free ``auth`` schema mean a user-scoped connection can read
neither ``deleted_at`` nor ``auth.users.banned_until``, so authorization state
must come from this RLS-bypassing connection (M8AuthorizationPlanV3 §5.1,
Option A). It remains NOT a general-purpose escape hatch: each consumer
(``AuditLogger``, ``StateReader``) exposes exactly one narrow, parameterized,
``user_id``-keyed operation; profile-BODY reads use a separate RLS-respecting
path (a sibling concern), never this pool.

Design constraints:
  - NO top-level ``asyncpg`` import. The driver is imported lazily inside
    :func:`build_audit_pool` so this module — and the whole ``supabase_auth``
    package — imports cleanly in environments where ``asyncpg`` is not installed
    (e.g. the unit-test environment). The package only needs the driver when a
    DB-backed pool is actually built at startup.
  - INJECTABLE pool factory so the builder is unit-testable without a live
    database (or the driver) — tests pass a fake factory.
  - Small pool + bounded command timeout: audit is low-volume and best-effort;
    a hung DB must not pile up connections or stall the event loop.

The returned :class:`AuditConnectionPool` satisfies M5's ``ConnectionAcquirer``
protocol: ``acquire()`` returns an async context manager yielding a connection
whose ``execute(sql, *args)`` runs the parameterized audit insert and whose
``fetchrow(sql, *args)`` runs the parameterized M8a state read. An ``asyncpg``
connection provides exactly that surface.
"""

from __future__ import annotations

from typing import Any, AsyncContextManager, Awaitable, Callable, Optional

from loguru import logger

# Conservative defaults: audit traffic is light and best-effort.
_DEFAULT_MIN_SIZE = 1
_DEFAULT_MAX_SIZE = 4
# Per-statement timeout (seconds) so a slow/hung DB fails fast rather than
# stalling fire-and-forget audit tasks indefinitely.
_DEFAULT_COMMAND_TIMEOUT = 10.0


class AuditConnectionPool:
    """
    Thin wrapper over an ``asyncpg`` pool exposing the M5 ``ConnectionAcquirer``
    surface (``acquire()``) plus ``close()`` for lifespan teardown.

    ``acquire()`` delegates straight to the underlying pool, whose acquire
    context manager yields a connection with ``execute(sql, *args)`` — exactly
    what ``AuditLogger.write`` calls.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def acquire(self) -> AsyncContextManager[Any]:
        # asyncpg's Pool.acquire() is itself an async context manager.
        return self._pool.acquire()

    async def close(self) -> None:
        """Close the pool (lifespan shutdown). Best-effort: never raises."""
        try:
            await self._pool.close()
        except Exception as exc:  # noqa: BLE001 — teardown must not raise.
            logger.warning("audit pool close failed: {}", type(exc).__name__)


async def build_audit_pool(
    db_url: str,
    *,
    min_size: int = _DEFAULT_MIN_SIZE,
    max_size: int = _DEFAULT_MAX_SIZE,
    command_timeout: float = _DEFAULT_COMMAND_TIMEOUT,
    pool_factory: Optional[Callable[..., Awaitable[Any]]] = None,
) -> Optional[AuditConnectionPool]:
    """
    Build the audit-write pool from ``db_url``, or return ``None`` if no DB is
    configured (audit then stays dormant — ``AuditLogger(None)``).

    Args:
        db_url: the ``SUPABASE_DB_URL`` connection string (service-role creds).
            Empty/None → returns ``None`` (dormant; not an error).
        min_size, max_size, command_timeout: pool tuning.
        pool_factory: optional injected coroutine ``(**kwargs) -> pool`` used in
            place of ``asyncpg.create_pool``. Lets tests build the adapter
            without ``asyncpg`` or a live database.

    Returns:
        An :class:`AuditConnectionPool`, or ``None`` when ``db_url`` is empty.

    Raises:
        Propagates whatever the pool factory raises (e.g. a connection error).
        The caller (bootstrap) decides whether that should fail startup.
    """
    if not db_url:
        return None

    if pool_factory is None:
        # Lazy import: only needed when a real DB pool is actually built.
        import asyncpg  # noqa: PLC0415 — intentional lazy import (see module docstring).

        pool_factory = asyncpg.create_pool

    pool = await pool_factory(
        dsn=db_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )
    return AuditConnectionPool(pool)


# --- M8a aliases ----------------------------------------------------------- #
# The privileged pool backs BOTH audit writes (M5/M6) and the authoritative
# user-state read (M8a). These aliases let state-read code depend on an
# intent-revealing name without a second pool or a second DB connection
# (Option A: reuse the existing privileged connection). The audit names above are
# unchanged so M5/M6 call sites and their tests are untouched.
PrivilegedConnectionPool = AuditConnectionPool
build_privileged_pool = build_audit_pool
