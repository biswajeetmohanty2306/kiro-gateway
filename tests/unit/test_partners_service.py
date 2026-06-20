# -*- coding: utf-8 -*-
"""Unit tests for partner invitation service (F4)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

from kiro.partners.service import (
    create_invite,
    validate_invite,
    accept_invite,
    get_status,
    disconnect,
    _generate_invite_code,
)
from kiro.partners.exceptions import (
    AlreadyConnectedError,
    InviteNotFoundError,
    SelfInviteError,
    NotConnectedError,
)


# --- Mock helpers ---

class MockConnection:
    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()
        self.execute = AsyncMock()


class MockPool:
    def __init__(self, conn=None):
        self._conn = conn or MockConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def make_pool(conn=None):
    if conn is None:
        conn = MockConnection()
    return MockPool(conn), conn


# --- Tests: _generate_invite_code ---

class TestGenerateInviteCode:
    def test_length(self):
        code = _generate_invite_code()
        assert len(code) == 8

    def test_alphanumeric(self):
        code = _generate_invite_code()
        assert code.isalnum()

    def test_uniqueness(self):
        codes = {_generate_invite_code() for _ in range(100)}
        assert len(codes) == 100  # extremely unlikely collision in 100 codes


# --- Tests: create_invite ---

@pytest.mark.asyncio
async def test_create_invite_success():
    """Creates invite when user has no active connection."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    # No existing connection
    conn.fetchrow.side_effect = [
        None,  # existing check
        {"id": "conn-1", "invite_code": "AbCd1234", "created_at": datetime(2026, 6, 20, tzinfo=timezone.utc)},
    ]

    result = await create_invite(pool, "user-1")

    assert result["connection_id"] == "conn-1"
    assert "invite_code" in result
    assert "created_at" in result


@pytest.mark.asyncio
async def test_create_invite_already_connected():
    """Raises AlreadyConnectedError when user has active connection."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = {"id": "existing-conn"}

    with pytest.raises(AlreadyConnectedError):
        await create_invite(pool, "user-1")


# --- Tests: validate_invite ---

@pytest.mark.asyncio
async def test_validate_invite_valid():
    """Returns inviter info for valid pending code."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = {
        "id": "conn-1",
        "invite_code": "AbCd1234",
        "inviter_name": "Alice",
        "inviter_email": "alice@example.com",
    }

    result = await validate_invite(pool, "AbCd1234")

    assert result["valid"] is True
    assert result["inviter_name"] == "Alice"


@pytest.mark.asyncio
async def test_validate_invite_invalid():
    """Returns None for non-existent/used code."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None

    result = await validate_invite(pool, "BADCODE1")
    assert result is None


# --- Tests: accept_invite ---

@pytest.mark.asyncio
async def test_accept_invite_success():
    """Accepts valid invite from different user."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-inviter", "invite_code": "AbCd1234"},  # find invite
        None,  # no existing connection for acceptor
        {"id": "conn-1", "accepted_at": datetime(2026, 6, 20, tzinfo=timezone.utc)},  # update
    ]

    result = await accept_invite(pool, "user-acceptor", "AbCd1234")

    assert result["connection_id"] == "conn-1"
    assert "accepted_at" in result


@pytest.mark.asyncio
async def test_accept_invite_not_found():
    """Raises InviteNotFoundError for invalid code."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None

    with pytest.raises(InviteNotFoundError):
        await accept_invite(pool, "user-1", "BADCODE1")


@pytest.mark.asyncio
async def test_accept_invite_self_invite():
    """Raises SelfInviteError when user accepts their own invite."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = {
        "id": "conn-1",
        "inviter_id": "user-1",  # same as acceptor
        "invite_code": "AbCd1234",
    }

    with pytest.raises(SelfInviteError):
        await accept_invite(pool, "user-1", "AbCd1234")


@pytest.mark.asyncio
async def test_accept_invite_acceptor_already_connected():
    """Raises AlreadyConnectedError when acceptor has existing connection."""
    pool, conn = make_pool()
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-inviter", "invite_code": "AbCd1234"},
        {"id": "other-conn"},  # acceptor already connected
    ]

    with pytest.raises(AlreadyConnectedError):
        await accept_invite(pool, "user-acceptor", "AbCd1234")


# --- Tests: get_status ---

@pytest.mark.asyncio
async def test_get_status_no_connection():
    """Returns connected=False when user has no connection."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None

    result = await get_status(pool, "user-1")

    assert result["connected"] is False
    assert result["pending_invite"] is None


@pytest.mark.asyncio
async def test_get_status_pending():
    """Returns pending invite info."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.return_value = {
        "id": "conn-1",
        "inviter_id": "user-1",
        "invitee_id": None,
        "status": "pending",
        "invite_code": "AbCd1234",
        "created_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
        "accepted_at": None,
    }

    result = await get_status(pool, "user-1")

    assert result["connected"] is False
    assert result["pending_invite"]["invite_code"] == "AbCd1234"
    assert result["pending_invite"]["role"] == "inviter"


@pytest.mark.asyncio
async def test_get_status_connected():
    """Returns partner info when connected."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.side_effect = [
        {
            "id": "conn-1",
            "inviter_id": "user-1",
            "invitee_id": "user-2",
            "status": "accepted",
            "invite_code": "AbCd1234",
            "created_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
            "accepted_at": datetime(2026, 6, 21, tzinfo=timezone.utc),
        },
        {"name": "Bob", "email": "bob@example.com"},  # partner info
    ]

    result = await get_status(pool, "user-1")

    assert result["connected"] is True
    assert result["partner"]["name"] == "Bob"
    assert result["role"] == "inviter"


# --- Tests: disconnect ---

@pytest.mark.asyncio
async def test_disconnect_success():
    """Disconnects existing accepted connection."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.return_value = {
        "id": "conn-1",
        "disconnected_at": datetime(2026, 6, 22, tzinfo=timezone.utc),
    }

    result = await disconnect(pool, "user-1")

    assert result["disconnected"] is True
    assert result["connection_id"] == "conn-1"


@pytest.mark.asyncio
async def test_disconnect_not_connected():
    """Raises NotConnectedError when no accepted connection exists."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None

    with pytest.raises(NotConnectedError):
        await disconnect(pool, "user-1")
