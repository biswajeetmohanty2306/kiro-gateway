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
Best-effort audit-event writer for Phase C (milestone M5).

Writes APPLICATION-LEVEL auth events into the pre-existing Postgres table
``public.auth_audit_log`` (created and verified by Phase A — M5 reuses it
exactly as deployed, creating/altering NO schema, indexes, RLS, or triggers).

Live-verified table contract (M5-D4), used here verbatim::

    public.auth_audit_log(
        audit_id   uuid  PK,
        user_id    uuid  NULL  FK -> public.users,
        event_type text,
        ip_address inet  NULL,
        user_agent text  NULL,
        created_at timestamptz
    )
    indexes: auth_audit_log_pkey, auth_audit_log_user_time_idx
    RLS: enabled, NO policies  -> no client access; inserts use the privileged
         (service-role / SUPABASE_DB_URL) connection that bypasses RLS.
    triggers: NONE on this table -> the backend is the SOLE writer, so there is
         no risk of duplicating a trigger-produced row.

Design invariants (docs/architecture/M5AuditPlan.md):
  - BEST-EFFORT / NON-BLOCKING (§6): a failed audit write NEVER fails the user
    request. ``record()`` is fire-and-forget; ``write()`` catches everything and
    logs to loguru. Nothing here is on the request critical path.
  - DATA-NEVER-STORED (§4): the writer API accepts ONLY safe fields
    (``user_id``, ``ip_address``, ``user_agent``). There is deliberately NO
    parameter through which a JWT, ``Authorization`` header, refresh token,
    secret, or full claim set could be passed — the no-leak rule is enforced by
    the type signature, not by discipline at call sites.
  - PURE-AUTH LAYER STAYS DB-FREE (§7): ``verifier.py`` / ``jwks_cache.py`` /
    ``user.py`` never import this module. Only audit (and sibling profile/
    onboarding) touch the DB.
  - NO TOP-LEVEL ``asyncpg`` IMPORT: the DB connection is injected via the
    ``ConnectionAcquirer`` protocol (an ``asyncpg`` pool satisfies it; tests
    inject a fake). This keeps the module importable without the driver and the
    writer unit-testable without a database.

``audit_id`` is generated here with ``uuid4`` (no DB default is assumed), and
``created_at`` is set by SQL ``now()`` (server-authoritative; no Python clock,
no assumed column default).
"""

from __future__ import annotations

import asyncio
import uuid
from enum import Enum
from typing import Any, AsyncContextManager, Optional, Protocol, Set

from loguru import logger


class AuditEvent(str, Enum):
    """
    Closed set of application-level audit event types M5 writes (design §3.1).

    Free ``text`` in the DB (no CHECK constraint, no triggers — M5-D4), but
    governed by this closed enum in code so the written values are stable and
    do not drift into ad-hoc strings (§3.4). ``auth.success`` is intentionally
    absent: routine per-request successes are NOT audited (volume rule D6/§3.3).
    """

    AUTH_FAILURE = "auth.failure"            # a 401 in verification (M7)
    AUTHZ_DENIED = "authz.denied"            # a 403 (banned/role gate, future)
    ONBOARDING_COMPLETED = "onboarding.completed"
    PROFILE_PROVISIONED = "profile.provisioned"
    LOGOUT = "logout"                        # /auth/logout — event only (M7)


# The single parameterized insert. created_at = now() (server time); audit_id is
# supplied as a generated uuid4 ($1). NO string interpolation — values are bound.
_INSERT_SQL = (
    "INSERT INTO public.auth_audit_log "
    "(audit_id, user_id, event_type, ip_address, user_agent, created_at) "
    "VALUES ($1, $2, $3, $4, $5, now())"
)


class Connection(Protocol):
    """Minimal async connection surface (satisfied by an ``asyncpg`` connection)."""

    async def execute(self, sql: str, *args: Any) -> Any:  # pragma: no cover - protocol
        ...


class ConnectionAcquirer(Protocol):
    """
    Acquires a pooled connection as an async context manager.

    An ``asyncpg.Pool`` satisfies this directly (``async with pool.acquire()``).
    Tests inject a fake with the same shape — so this module needs neither a
    live database nor the ``asyncpg`` package to be unit-tested.
    """

    def acquire(self) -> AsyncContextManager[Connection]:  # pragma: no cover - protocol
        ...


class AuditLogger:
    """
    Best-effort writer for ``auth_audit_log``.

    Construct with the privileged (service-role) connection acquirer. When the
    acquirer is ``None`` the logger is DORMANT — every call is a safe no-op, so
    a deployment without Phase C configured (no ``SUPABASE_DB_URL``) is
    unaffected. The acquirer is used for NOTHING but audit inserts (design §2,
    M5-D1).
    """

    def __init__(self, acquirer: Optional[ConnectionAcquirer] = None) -> None:
        self._acquirer = acquirer
        # Strong refs to in-flight fire-and-forget tasks so they are not
        # garbage-collected mid-write (asyncio only holds weak refs).
        self._tasks: Set["asyncio.Task[None]"] = set()

    def record(
        self,
        event: AuditEvent,
        *,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Fire-and-forget dispatch of an audit write (NON-BLOCKING, §6).

        Schedules ``write`` as a background task and returns immediately. NEVER
        blocks the caller and NEVER raises — if no event loop is running or the
        logger is dormant, it degrades to a no-op / a single loguru line. This
        is the method request handlers (M7) call.

        Only safe fields are accepted; see the module no-leak note (§4).
        """
        if self._acquirer is None:
            return  # dormant: Phase C DB not configured — nothing to do.
        # Resolve the running loop FIRST. If there is none (sync context), we
        # must not even construct the write() coroutine — an un-awaited coroutine
        # would leak. Best-effort: log and drop rather than raise on the path.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "audit: could not schedule write (no running loop) "
                "event={} request_id={}",
                event.value,
                request_id,
            )
            return
        task: "asyncio.Task[None]" = loop.create_task(
            self.write(
                event,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def write(
        self,
        event: AuditEvent,
        *,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Insert one audit row. BEST-EFFORT: catches every error and logs it; it
        never propagates, so an audit failure can never fail the user request
        or roll back a sibling transaction (§6).

        ``user_id`` (a Supabase ``sub`` UUID string) is converted to ``uuid.UUID``
        defensively; a malformed value is recorded as ``NULL`` rather than
        raising. ``ip_address``/``user_agent`` are bound as-is (or ``NULL``).
        """
        if self._acquirer is None:
            return  # dormant no-op.

        try:
            uid: Optional[uuid.UUID] = None
            if user_id:
                try:
                    uid = uuid.UUID(user_id)
                except (ValueError, AttributeError, TypeError):
                    # Don't drop the whole event over a bad id; store NULL user.
                    logger.warning(
                        "audit: non-uuid user_id, storing NULL event={} request_id={}",
                        event.value,
                        request_id,
                    )
                    uid = None

            async with self._acquirer.acquire() as conn:
                await conn.execute(
                    _INSERT_SQL,
                    uuid.uuid4(),       # $1 audit_id (no DB default assumed)
                    uid,                # $2 user_id (nullable)
                    event.value,        # $3 event_type
                    ip_address,         # $4 ip_address (nullable)
                    user_agent,         # $5 user_agent (nullable)
                )
        except Exception as exc:  # noqa: BLE001 — best-effort: never propagate.
            # Log the failure (and only safe context) for correlation. NEVER log
            # a token, header, secret, or claim set — none reach this scope.
            logger.warning(
                "audit write failed event={} request_id={} error={}",
                event.value,
                request_id,
                type(exc).__name__,
            )
