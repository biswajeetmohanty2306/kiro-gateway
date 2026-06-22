# -*- coding: utf-8 -*-
"""Unit tests for notification system (F6D)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from kiro.progress.notifications import (
    create_notification,
    get_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    notify_milestone_unlocked,
    notify_goal_completed,
    notify_goals_sweep,
    notify_streak_reached,
    NOTIFICATION_ICONS,
)
from kiro.progress.exceptions import ProgressError


NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


class MockConnection:
    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()
        self.fetchval = AsyncMock()
        self.execute = AsyncMock()


class MockPool:
    def __init__(self, conn=None):
        self._conn = conn or MockConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


# =============================================================================
# create_notification
# =============================================================================

@pytest.mark.asyncio
async def test_create_notification_basic():
    """Creates a notification and returns its ID."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "notif-1"}

    result = await create_notification(
        pool, "user-1", "milestone_unlocked",
        "Week Warrior!", "You maintained a 7-day streak",
    )

    assert result == "notif-1"
    call_args = conn.fetchrow.call_args[0]
    assert "INSERT INTO public.notifications" in call_args[0]
    assert call_args[1] == "user-1"
    assert call_args[2] == "milestone_unlocked"
    assert call_args[3] == "Week Warrior!"
    assert call_args[4] == "You maintained a 7-day streak"
    assert call_args[5] == "🏆"  # default icon for milestone_unlocked


@pytest.mark.asyncio
async def test_create_notification_custom_icon():
    """Uses custom icon when provided."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "notif-2"}

    await create_notification(
        pool, "user-1", "streak_reached",
        "14-day streak!", "You've been consistent",
        icon="⚡",
    )

    call_args = conn.fetchrow.call_args[0]
    assert call_args[5] == "⚡"


@pytest.mark.asyncio
async def test_create_notification_with_metadata():
    """Stores metadata as JSON."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "notif-3"}

    await create_notification(
        pool, "user-1", "weekly_goal_completed",
        "Goal Complete!", "You completed a plan",
        metadata={"goal_type": "complete_plan"},
    )

    call_args = conn.fetchrow.call_args[0]
    assert json.loads(call_args[6]) == {"goal_type": "complete_plan"}


@pytest.mark.asyncio
async def test_create_notification_error_returns_none():
    """Returns None on database error (non-raising)."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = Exception("DB error")

    result = await create_notification(
        pool, "user-1", "milestone_unlocked", "Test", "Test body"
    )

    assert result is None


# =============================================================================
# get_notifications
# =============================================================================

@pytest.mark.asyncio
async def test_get_notifications_empty():
    """Returns empty list when no notifications."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    result = await get_notifications(pool, "user-1")

    assert result["notifications"] == []
    assert result["unread_count"] == 0


@pytest.mark.asyncio
async def test_get_notifications_with_data():
    """Returns formatted notifications newest first."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = [
        {
            "id": "n1", "type": "milestone_unlocked",
            "title": "Week Warrior!", "body": "7-day streak",
            "icon": "🔥", "metadata": "{}",
            "read": False, "created_at": NOW,
        },
        {
            "id": "n2", "type": "weekly_goal_completed",
            "title": "Goal Complete!", "body": "Plan completed",
            "icon": "✅", "metadata": json.dumps({"goal_type": "complete_plan"}),
            "read": True, "created_at": NOW,
        },
    ]
    conn.fetchval.return_value = 1  # 1 unread

    result = await get_notifications(pool, "user-1")

    assert len(result["notifications"]) == 2
    assert result["unread_count"] == 1
    assert result["notifications"][0]["type"] == "milestone_unlocked"
    assert result["notifications"][0]["read"] is False
    assert result["notifications"][1]["metadata"] == {"goal_type": "complete_plan"}


@pytest.mark.asyncio
async def test_get_notifications_unread_only():
    """Filters to unread notifications when flag set."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = [
        {
            "id": "n1", "type": "milestone_unlocked",
            "title": "Test", "body": "Body",
            "icon": "🏆", "metadata": "{}",
            "read": False, "created_at": NOW,
        },
    ]
    conn.fetchval.return_value = 1

    result = await get_notifications(pool, "user-1", unread_only=True)

    assert len(result["notifications"]) == 1
    # Verify the correct query was used (with read = false filter)
    query = conn.fetch.call_args[0][0]
    assert "read = false" in query


# =============================================================================
# mark_notification_read
# =============================================================================

@pytest.mark.asyncio
async def test_mark_read_success():
    """Marks a notification as read."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "n1", "read": True}

    result = await mark_notification_read(pool, "user-1", "n1")

    assert result["id"] == "n1"
    assert result["read"] is True


@pytest.mark.asyncio
async def test_mark_read_not_found():
    """Raises ProgressError when notification not found."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    with pytest.raises(ProgressError) as exc_info:
        await mark_notification_read(pool, "user-1", "bad-id")

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


# =============================================================================
# mark_all_notifications_read
# =============================================================================

@pytest.mark.asyncio
async def test_mark_all_read():
    """Marks all unread notifications as read."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.execute.return_value = "UPDATE 5"

    result = await mark_all_notifications_read(pool, "user-1")

    assert result["marked"] == 5


@pytest.mark.asyncio
async def test_mark_all_read_none_unread():
    """Returns 0 when no unread notifications."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.execute.return_value = "UPDATE 0"

    result = await mark_all_notifications_read(pool, "user-1")

    assert result["marked"] == 0


# =============================================================================
# Integration helpers
# =============================================================================

@pytest.mark.asyncio
async def test_notify_milestone_unlocked():
    """Creates milestone notification with correct fields."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "n1"}

    await notify_milestone_unlocked(
        pool, "user-1", "seven_day_streak", "Week Warrior", "🔥"
    )

    call_args = conn.fetchrow.call_args[0]
    assert call_args[2] == "milestone_unlocked"
    assert call_args[3] == "Week Warrior!"
    assert call_args[4] == "You unlocked: Week Warrior"
    assert call_args[5] == "🔥"


@pytest.mark.asyncio
async def test_notify_goal_completed():
    """Creates goal completion notification."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "n2"}

    await notify_goal_completed(pool, "user-1", "complete_plan")

    call_args = conn.fetchrow.call_args[0]
    assert call_args[2] == "weekly_goal_completed"
    assert call_args[3] == "Goal Complete!"
    assert "complete plan" in call_args[4]


@pytest.mark.asyncio
async def test_notify_goals_sweep():
    """Creates sweep notification."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "n3"}

    await notify_goals_sweep(pool, "user-1")

    call_args = conn.fetchrow.call_args[0]
    assert call_args[2] == "weekly_goals_sweep"
    assert call_args[3] == "Perfect Week!"


@pytest.mark.asyncio
async def test_notify_streak_reached():
    """Creates streak notification with day count."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "n4"}

    await notify_streak_reached(pool, "user-1", 14)

    call_args = conn.fetchrow.call_args[0]
    assert call_args[2] == "streak_reached"
    assert "14-day" in call_args[3]
    assert "14 days" in call_args[4]


# =============================================================================
# Icon mapping
# =============================================================================

def test_notification_icons_complete():
    """All notification types have default icons."""
    expected_types = [
        "milestone_unlocked", "weekly_goal_completed", "weekly_goals_sweep",
        "streak_reached", "assessment_completed", "partner_connected", "report_generated",
    ]
    for t in expected_types:
        assert t in NOTIFICATION_ICONS, f"Missing icon for type: {t}"
