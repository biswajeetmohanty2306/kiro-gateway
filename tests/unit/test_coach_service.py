# -*- coding: utf-8 -*-
"""Unit tests for the AI Relationship Coach Service (J7-F).

Tests service orchestration with mocked database pools.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from kiro.coach.service import (
    start_conversation,
    send_message,
    get_conversation,
    list_conversations,
    complete_conversation,
)
from kiro.coach.exceptions import (
    NoConnectionError,
    ConversationLimitError,
    ConversationNotFoundError,
    ConversationCompletedError,
    TurnLimitError,
    ProviderError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Infrastructure
# ─────────────────────────────────────────────────────────────────────────────

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

SAMPLE_DIMS = json.dumps({
    "attachment_style": {"score": 80, "label": "Good", "recommendation": "Strong bond."},
    "communication_style": {"score": 65, "label": "Moderate", "recommendation": "Room to grow."},
    "conflict_style": {"score": 50, "label": "Challenging", "recommendation": "Needs attention."},
})


class MockConnection:
    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetchval = AsyncMock()
        self.fetch = AsyncMock()
        self.execute = AsyncMock()


class MockPool:
    def __init__(self, conn=None):
        self._conn = conn or MockConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def _setup_connection(conn, user_id="user-1", partner_id="user-2", connection_id="conn-1"):
    """Setup mock for standard connection resolution."""
    conn.fetchrow.side_effect = _make_side_effect(conn, user_id, partner_id, connection_id)


def _make_side_effect(conn, user_id, partner_id, connection_id):
    """Create a flexible side_effect that responds to different queries."""
    call_count = [0]

    async def _side_effect(*args, **kwargs):
        query = args[0] if args else ""
        if "partner_connections" in query and "inviter_id" in query:
            return {"id": connection_id, "inviter_id": user_id, "invitee_id": partner_id}
        if "users" in query and "user_id" in query:
            uid = args[1] if len(args) > 1 else ""
            if uid == user_id:
                return {"name": "Alice", "email": "alice@test.com"}
            return {"name": "Bob", "email": "bob@test.com"}
        if "compatibility_reports" in query:
            return {"overall_score": 72.5, "dimension_scores": SAMPLE_DIMS}
        if "journey_state" in query:
            return {"started_at": NOW}
        if "coach_conversations" in query and "$1" in query and "user_id" in query:
            return {"id": "conv-1", "connection_id": connection_id, "user_id": user_id,
                    "status": "active", "context_version": 1, "context_hash": "abc",
                    "summary": None, "turn_count": 3, "started_at": NOW,
                    "completed_at": None, "created_at": NOW}
        if "INSERT INTO public.coach_conversations" in query:
            return {"id": "new-conv-1", "started_at": NOW, "created_at": NOW}
        if "partner_connections" in query and "id = $1" in query:
            return {"inviter_id": user_id, "invitee_id": partner_id}
        return None

    return _side_effect


# ─────────────────────────────────────────────────────────────────────────────
# Tests: start_conversation
# ─────────────────────────────────────────────────────────────────────────────


class TestStartConversation:
    """Tests for starting a new conversation."""

    @pytest.mark.asyncio
    async def test_no_connection_raises(self):
        """Raises NoConnectionError when no partner connection exists."""
        conn = MockConnection()
        conn.fetchrow.return_value = None
        pool = MockPool(conn)

        with pytest.raises(NoConnectionError):
            await start_conversation(pool, "user-1")

    @pytest.mark.asyncio
    async def test_conversation_limit_raises(self):
        """Raises ConversationLimitError when limit reached."""
        conn = MockConnection()
        conn.fetchrow.side_effect = [
            {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},  # connection
        ]
        conn.fetchval.return_value = 5  # at limit
        pool = MockPool(conn)

        with pytest.raises(ConversationLimitError):
            await start_conversation(pool, "user-1")

    @pytest.mark.asyncio
    async def test_successful_creation(self):
        """Successfully creates a conversation and returns greeting."""
        conn = MockConnection()
        _setup_connection(conn)
        conn.fetchval.return_value = 0  # no active conversations
        conn.fetch.return_value = []  # no plans
        pool = MockPool(conn)

        result = await start_conversation(pool, "user-1")

        assert "conversation_id" in result
        assert result["status"] == "active"
        assert "Alice" in result["greeting"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: send_message
# ─────────────────────────────────────────────────────────────────────────────


class TestSendMessage:
    """Tests for sending messages."""

    @pytest.mark.asyncio
    async def test_conversation_not_found(self):
        """Raises ConversationNotFoundError for invalid conversation."""
        conn = MockConnection()
        conn.fetchrow.return_value = None
        pool = MockPool(conn)

        with pytest.raises(ConversationNotFoundError):
            await send_message(pool, "user-1", "bad-id", "Hello")

    @pytest.mark.asyncio
    async def test_completed_conversation_rejected(self):
        """Raises ConversationCompletedError for non-active conversations."""
        conn = MockConnection()
        conn.fetchrow.return_value = {
            "id": "conv-1", "connection_id": "conn-1", "user_id": "user-1",
            "status": "completed", "turn_count": 5, "started_at": NOW,
            "context_version": 1, "context_hash": "", "summary": None,
            "completed_at": NOW, "created_at": NOW,
        }
        pool = MockPool(conn)

        with pytest.raises(ConversationCompletedError):
            await send_message(pool, "user-1", "conv-1", "Hello")

    @pytest.mark.asyncio
    async def test_turn_limit_rejected(self):
        """Raises TurnLimitError when max turns reached."""
        conn = MockConnection()
        conn.fetchrow.return_value = {
            "id": "conv-1", "connection_id": "conn-1", "user_id": "user-1",
            "status": "active", "turn_count": 20, "started_at": NOW,
            "context_version": 1, "context_hash": "", "summary": None,
            "completed_at": None, "created_at": NOW,
        }
        pool = MockPool(conn)

        with pytest.raises(TurnLimitError):
            await send_message(pool, "user-1", "conv-1", "Hello")

    @pytest.mark.asyncio
    async def test_safety_block_returns_replacement(self):
        """Safety-blocked messages return replacement without calling provider."""
        conn = MockConnection()
        _setup_connection(conn)
        conn.fetchval.return_value = False
        conn.fetch.return_value = []
        pool = MockPool(conn)

        result = await send_message(pool, "user-1", "conv-1", "")

        # Empty message triggers safety block
        assert "response" in result
        assert result["safety_action"] == "block"

    @pytest.mark.asyncio
    async def test_provider_stub_raises(self):
        """Provider stub raises ProviderError (until J7-G)."""
        conn = MockConnection()
        _setup_connection(conn)
        conn.fetchval.return_value = False
        conn.fetch.return_value = []
        pool = MockPool(conn)

        with pytest.raises(ProviderError):
            await send_message(pool, "user-1", "conv-1", "How can we communicate better?")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: get_conversation
# ─────────────────────────────────────────────────────────────────────────────


class TestGetConversation:
    """Tests for getting conversation details."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Raises ConversationNotFoundError for invalid ID."""
        conn = MockConnection()
        conn.fetchrow.return_value = None
        pool = MockPool(conn)

        with pytest.raises(ConversationNotFoundError):
            await get_conversation(pool, "user-1", "bad-id")

    @pytest.mark.asyncio
    async def test_returns_conversation(self):
        """Returns conversation with messages."""
        conn = MockConnection()
        conn.fetchrow.return_value = {
            "id": "conv-1", "connection_id": "conn-1", "user_id": "user-1",
            "status": "active", "turn_count": 2, "started_at": NOW,
            "context_version": 1, "context_hash": "", "summary": None,
            "completed_at": None, "created_at": NOW,
        }
        conn.fetch.return_value = [
            {"role": "user", "content": "Hello", "turn_number": 1, "created_at": NOW},
            {"role": "assistant", "content": "Hi there!", "turn_number": 1, "created_at": NOW},
        ]
        pool = MockPool(conn)

        result = await get_conversation(pool, "user-1", "conv-1")

        assert result["id"] == "conv-1"
        assert result["status"] == "active"
        assert len(result["messages"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: list_conversations
# ─────────────────────────────────────────────────────────────────────────────


class TestListConversations:
    """Tests for listing conversations."""

    @pytest.mark.asyncio
    async def test_empty_list(self):
        """Returns empty list when no conversations exist."""
        conn = MockConnection()
        conn.fetch.return_value = []
        pool = MockPool(conn)

        result = await list_conversations(pool, "user-1")
        assert result["conversations"] == []

    @pytest.mark.asyncio
    async def test_returns_list(self):
        """Returns conversation list."""
        conn = MockConnection()
        conn.fetch.return_value = [
            {"id": "conv-1", "status": "active", "turn_count": 3, "started_at": NOW, "completed_at": None},
            {"id": "conv-2", "status": "completed", "turn_count": 10, "started_at": NOW, "completed_at": NOW},
        ]
        pool = MockPool(conn)

        result = await list_conversations(pool, "user-1")
        assert len(result["conversations"]) == 2
        assert result["conversations"][0]["id"] == "conv-1"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: complete_conversation
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteConversation:
    """Tests for completing a conversation."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Raises ConversationNotFoundError for invalid ID."""
        conn = MockConnection()
        conn.fetchrow.return_value = None
        pool = MockPool(conn)

        with pytest.raises(ConversationNotFoundError):
            await complete_conversation(pool, "user-1", "bad-id")

    @pytest.mark.asyncio
    async def test_already_completed(self):
        """Raises ConversationCompletedError for non-active conversations."""
        conn = MockConnection()
        conn.fetchrow.return_value = {
            "id": "conv-1", "connection_id": "conn-1", "user_id": "user-1",
            "status": "completed", "turn_count": 5, "started_at": NOW,
            "context_version": 1, "context_hash": "", "summary": "Done",
            "completed_at": NOW, "created_at": NOW,
        }
        pool = MockPool(conn)

        with pytest.raises(ConversationCompletedError):
            await complete_conversation(pool, "user-1", "conv-1")

    @pytest.mark.asyncio
    async def test_successful_completion(self):
        """Successfully completes a conversation."""
        conn = MockConnection()
        conn.fetchrow.return_value = {
            "id": "conv-1", "connection_id": "conn-1", "user_id": "user-1",
            "status": "active", "turn_count": 5, "started_at": NOW,
            "context_version": 1, "context_hash": "", "summary": None,
            "completed_at": None, "created_at": NOW,
        }
        pool = MockPool(conn)

        result = await complete_conversation(pool, "user-1", "conv-1")
        assert result["status"] == "completed"
