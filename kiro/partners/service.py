# -*- coding: utf-8 -*-
"""Partner invitation business logic (F4)."""

from __future__ import annotations

import secrets
import string
from typing import Any, Optional

from .exceptions import (
    AlreadyConnectedError,
    InviteNotFoundError,
    NotConnectedError,
    SelfInviteError,
)


def _generate_invite_code() -> str:
    """Generate an 8-character alphanumeric invite code."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


async def create_invite(pool: Any, user_id: str) -> dict:
    """
    Generate a new partner invite code.

    Raises AlreadyConnectedError if user has an active connection.
    """
    async with pool.acquire() as conn:
        # Check for existing active connection
        existing = await conn.fetchrow(
            """
            SELECT id FROM public.partner_connections
            WHERE (inviter_id = $1 OR invitee_id = $1)
              AND status IN ('pending', 'accepted')
            LIMIT 1
            """,
            user_id,
        )
        if existing:
            raise AlreadyConnectedError()

        # Generate unique code (retry on collision)
        for _ in range(5):
            code = _generate_invite_code()
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO public.partner_connections (inviter_id, invite_code, status)
                    VALUES ($1, $2, 'pending')
                    RETURNING id, invite_code, created_at
                    """,
                    user_id,
                    code,
                )
                return {
                    "connection_id": str(row["id"]),
                    "invite_code": row["invite_code"],
                    "created_at": row["created_at"].isoformat(),
                }
            except Exception as e:
                if "unique" in str(e).lower() and "invite_code" in str(e).lower():
                    continue  # Code collision, retry
                raise

        # Exhausted retries (extremely unlikely)
        raise RuntimeError("Failed to generate unique invite code")


async def validate_invite(pool: Any, code: str) -> Optional[dict]:
    """
    Validate an invite code. Returns inviter info if valid, None if not.
    Runs as service-role (no auth required for public validation).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pc.id, pc.invite_code, u.name as inviter_name, u.email as inviter_email
            FROM public.partner_connections pc
            JOIN public.users u ON u.user_id = pc.inviter_id
            WHERE pc.invite_code = $1 AND pc.status = 'pending'
            LIMIT 1
            """,
            code,
        )
        if not row:
            return None

        return {
            "valid": True,
            "invite_code": row["invite_code"],
            "inviter_name": row["inviter_name"],
            "inviter_email": row["inviter_email"],
        }


async def accept_invite(pool: Any, user_id: str, invite_code: str) -> dict:
    """
    Accept a partner invitation.

    Raises:
        InviteNotFoundError: code doesn't exist or isn't pending
        SelfInviteError: user trying to accept their own invite
        AlreadyConnectedError: accepting user already has a partner
    """
    async with pool.acquire() as conn:
        # Find the pending invite
        invite = await conn.fetchrow(
            """
            SELECT id, inviter_id, invite_code
            FROM public.partner_connections
            WHERE invite_code = $1 AND status = 'pending'
            FOR UPDATE
            """,
            invite_code,
        )

        if not invite:
            raise InviteNotFoundError()

        # Prevent self-invite
        if str(invite["inviter_id"]) == user_id:
            raise SelfInviteError()

        # Check accepting user doesn't already have a connection
        existing = await conn.fetchrow(
            """
            SELECT id FROM public.partner_connections
            WHERE (inviter_id = $1 OR invitee_id = $1)
              AND status IN ('pending', 'accepted')
              AND id != $2
            LIMIT 1
            """,
            user_id,
            invite["id"],
        )
        if existing:
            raise AlreadyConnectedError()

        # Accept the invite
        row = await conn.fetchrow(
            """
            UPDATE public.partner_connections
            SET invitee_id = $1, status = 'accepted', accepted_at = now()
            WHERE id = $2
            RETURNING id, accepted_at
            """,
            user_id,
            invite["id"],
        )

        return {
            "connection_id": str(row["id"]),
            "accepted_at": row["accepted_at"].isoformat(),
        }


async def get_status(pool: Any, user_id: str) -> dict:
    """
    Get the user's current partner connection status.
    Returns connected=True with partner info, or connected=False.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pc.id, pc.inviter_id, pc.invitee_id, pc.status,
                   pc.invite_code, pc.created_at, pc.accepted_at
            FROM public.partner_connections pc
            WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1)
              AND pc.status IN ('pending', 'accepted')
            LIMIT 1
            """,
            user_id,
        )

        if not row:
            return {"connected": False, "pending_invite": None}

        # Determine partner id
        inviter_id = str(row["inviter_id"])
        invitee_id = str(row["invitee_id"]) if row["invitee_id"] else None
        is_inviter = (inviter_id == user_id)
        partner_id = invitee_id if is_inviter else inviter_id

        if row["status"] == "pending":
            return {
                "connected": False,
                "pending_invite": {
                    "connection_id": str(row["id"]),
                    "invite_code": row["invite_code"],
                    "role": "inviter" if is_inviter else "invitee",
                    "created_at": row["created_at"].isoformat(),
                },
            }

        # Status is 'accepted' — fetch partner info
        partner_row = await conn.fetchrow(
            "SELECT name, email FROM public.users WHERE user_id = $1",
            partner_id,
        )

        return {
            "connected": True,
            "connection_id": str(row["id"]),
            "partner": {
                "name": partner_row["name"] if partner_row else None,
                "email": partner_row["email"] if partner_row else None,
            },
            "since": row["accepted_at"].isoformat() if row["accepted_at"] else None,
            "role": "inviter" if is_inviter else "invitee",
        }


async def disconnect(pool: Any, user_id: str) -> dict:
    """
    Disconnect from the current partner.
    Raises NotConnectedError if no active connection exists.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.partner_connections
            SET status = 'disconnected', disconnected_at = now()
            WHERE (inviter_id = $1 OR invitee_id = $1)
              AND status = 'accepted'
            RETURNING id, disconnected_at
            """,
            user_id,
        )

        if not row:
            raise NotConnectedError()

        return {
            "disconnected": True,
            "connection_id": str(row["id"]),
            "disconnected_at": row["disconnected_at"].isoformat(),
        }
