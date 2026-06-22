# -*- coding: utf-8 -*-
"""Unit tests for weekly goals system (F6D)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from kiro.progress.goals import (
    generate_weekly_goals,
    get_weekly_goals,
    update_weekly_goals_progress,
    complete_goal_rewards,
    check_goal_sweep_bonus,
    _get_week_start,
    _select_goals_for_user,
    GOAL_TYPES,
    SWEEP_BONUS,
)


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
# Helper function tests
# =============================================================================

def test_get_week_start_monday():
    """Returns the Monday of the week."""
    # June 22, 2026 is a Monday
    monday = date(2026, 6, 22)
    assert _get_week_start(monday) == monday


def test_get_week_start_midweek():
    """Returns Monday for a Wednesday."""
    wednesday = date(2026, 6, 24)
    assert _get_week_start(wednesday) == date(2026, 6, 22)


def test_get_week_start_sunday():
    """Returns Monday for a Sunday."""
    sunday = date(2026, 6, 28)
    assert _get_week_start(sunday) == date(2026, 6, 22)


def test_select_goals_with_incomplete_plans():
    """Selects complete_plan when user has incomplete plans."""
    goals = _select_goals_for_user(has_incomplete_plans=True, week_number=1)
    assert len(goals) == 3
    assert "maintain_streak" in goals
    assert "complete_plan" in goals


def test_select_goals_without_incomplete_plans():
    """Selects log_activity when no incomplete plans."""
    goals = _select_goals_for_user(has_incomplete_plans=False, week_number=1)
    assert len(goals) == 3
    assert "maintain_streak" in goals
    assert "log_activity" in goals


# =============================================================================
# generate_weekly_goals
# =============================================================================

@pytest.mark.asyncio
async def test_generate_goals_creates_new():
    """Generates 3 goals for a new week."""
    conn = MockConnection()
    pool = MockPool(conn)

    # No existing goals
    conn.fetch.return_value = []
    # has_incomplete_plans check
    conn.fetchval.return_value = True

    # INSERT RETURNING for each goal
    conn.fetchrow.side_effect = [
        {"id": "goal-1", "goal_type": "maintain_streak", "target": 3, "progress": 0, "completed": False, "completed_at": None, "bonus_points": 10},
        {"id": "goal-2", "goal_type": "complete_plan", "target": 1, "progress": 0, "completed": False, "completed_at": None, "bonus_points": 15},
        {"id": "goal-3", "goal_type": "log_activity", "target": 2, "progress": 0, "completed": False, "completed_at": None, "bonus_points": 10},
    ]

    goals = await generate_weekly_goals(pool, "user-1")

    assert len(goals) == 3
    assert goals[0]["goal_type"] == "maintain_streak"
    assert goals[0]["target"] == 3
    assert goals[0]["completed"] is False


@pytest.mark.asyncio
async def test_generate_goals_idempotent():
    """Returns existing goals if already generated for this week."""
    conn = MockConnection()
    pool = MockPool(conn)

    # Goals already exist
    conn.fetch.return_value = [
        {"id": "goal-1", "goal_type": "maintain_streak", "target": 3, "progress": 1, "completed": False, "completed_at": None, "bonus_points": 10},
        {"id": "goal-2", "goal_type": "complete_plan", "target": 1, "progress": 0, "completed": False, "completed_at": None, "bonus_points": 15},
        {"id": "goal-3", "goal_type": "log_activity", "target": 2, "progress": 1, "completed": False, "completed_at": None, "bonus_points": 10},
    ]

    goals = await generate_weekly_goals(pool, "user-1")

    assert len(goals) == 3
    assert goals[0]["progress"] == 1
    # fetchval and fetchrow should NOT have been called (short-circuited)
    conn.fetchval.assert_not_called()
    conn.fetchrow.assert_not_called()


# =============================================================================
# get_weekly_goals
# =============================================================================

@pytest.mark.asyncio
async def test_get_weekly_goals_not_all_completed():
    """Returns goals with all_completed=False when some are incomplete."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"id": "g1", "goal_type": "maintain_streak", "target": 3, "progress": 3, "completed": True, "completed_at": NOW, "bonus_points": 10},
        {"id": "g2", "goal_type": "complete_plan", "target": 1, "progress": 0, "completed": False, "completed_at": None, "bonus_points": 15},
        {"id": "g3", "goal_type": "log_activity", "target": 2, "progress": 1, "completed": False, "completed_at": None, "bonus_points": 10},
    ]

    result = await get_weekly_goals(pool, "user-1")

    assert result["all_completed"] is False
    assert result["sweep_bonus"] == SWEEP_BONUS
    assert len(result["goals"]) == 3


@pytest.mark.asyncio
async def test_get_weekly_goals_all_completed():
    """Returns all_completed=True when all goals are done."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"id": "g1", "goal_type": "maintain_streak", "target": 3, "progress": 3, "completed": True, "completed_at": NOW, "bonus_points": 10},
        {"id": "g2", "goal_type": "complete_plan", "target": 1, "progress": 1, "completed": True, "completed_at": NOW, "bonus_points": 15},
        {"id": "g3", "goal_type": "log_activity", "target": 2, "progress": 2, "completed": True, "completed_at": NOW, "bonus_points": 10},
    ]

    result = await get_weekly_goals(pool, "user-1")

    assert result["all_completed"] is True


# =============================================================================
# update_weekly_goals_progress
# =============================================================================

@pytest.mark.asyncio
async def test_update_goals_plan_completed():
    """plan_completed advances complete_plan and log_activity goals."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"id": "g1", "goal_type": "complete_plan", "target": 1, "progress": 0, "completed": False},
        {"id": "g2", "goal_type": "log_activity", "target": 2, "progress": 0, "completed": False},
        {"id": "g3", "goal_type": "maintain_streak", "target": 3, "progress": 0, "completed": False},
    ]

    newly_completed = await update_weekly_goals_progress(pool, "user-1", "plan_completed", streak_days=1)

    # complete_plan target=1, progress goes to 1 → completed
    # log_activity target=2, progress goes to 1 → not completed
    assert len(newly_completed) == 1
    assert newly_completed[0]["goal_type"] == "complete_plan"
    # Should have called execute twice (one for each advanced goal)
    assert conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_update_goals_streak_advances():
    """Streak update advances maintain_streak when streak >= target."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"id": "g1", "goal_type": "maintain_streak", "target": 3, "progress": 0, "completed": False},
    ]

    newly_completed = await update_weekly_goals_progress(pool, "user-1", "plan_completed", streak_days=3)

    assert len(newly_completed) == 1
    assert newly_completed[0]["goal_type"] == "maintain_streak"


@pytest.mark.asyncio
async def test_update_goals_streak_below_target():
    """Streak below target does not advance maintain_streak."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"id": "g1", "goal_type": "maintain_streak", "target": 3, "progress": 0, "completed": False},
    ]

    newly_completed = await update_weekly_goals_progress(pool, "user-1", "plan_completed", streak_days=2)

    assert len(newly_completed) == 0
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_goals_no_active_goals():
    """No updates when no active goals exist."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = []  # no active goals

    newly_completed = await update_weekly_goals_progress(pool, "user-1", "plan_completed")

    assert newly_completed == []
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_goals_already_completed_skipped():
    """Already-completed goals are not fetched (query filters completed=false)."""
    conn = MockConnection()
    pool = MockPool(conn)
    # Only returns uncompleted goals
    conn.fetch.return_value = []

    newly_completed = await update_weekly_goals_progress(pool, "user-1", "plan_completed")

    assert newly_completed == []


# =============================================================================
# complete_goal_rewards
# =============================================================================

@pytest.mark.asyncio
async def test_complete_goal_rewards_awards_bonus():
    """Awards bonus points for each completed goal."""
    conn = MockConnection()
    pool = MockPool(conn)

    # record_progress_event for goal bonus + notify_goal_completed + check_goal_sweep_bonus
    conn.fetchrow.side_effect = [
        {"id": "evt-1"},         # record_progress_event for goal bonus
        {"id": "notif-1"},       # notify_goal_completed
        {"total": 3, "done": 2}, # sweep check: stats (not all done)
    ]

    result = await complete_goal_rewards(
        pool, "user-1",
        [{"goal_type": "complete_plan", "bonus_points": 15}],
    )

    assert result["goals_completed"] == 1
    assert result["bonus_points"] == 15
    assert result["sweep_awarded"] is False


@pytest.mark.asyncio
async def test_complete_goal_rewards_no_goals():
    """No rewards when no goals completed."""
    conn = MockConnection()
    pool = MockPool(conn)

    result = await complete_goal_rewards(pool, "user-1", [])

    assert result["goals_completed"] == 0
    assert result["bonus_points"] == 0
    assert result["sweep_awarded"] is False


# =============================================================================
# check_goal_sweep_bonus
# =============================================================================

@pytest.mark.asyncio
async def test_sweep_bonus_all_complete():
    """Awards sweep bonus when all 3 goals are complete."""
    conn = MockConnection()
    pool = MockPool(conn)

    # Stats: all 3 done
    conn.fetchrow.side_effect = [
        {"total": 3, "done": 3},
        {"id": "sweep-evt"},  # record_progress_event
    ]
    # Not already awarded
    conn.fetchval.return_value = False

    result = await check_goal_sweep_bonus(pool, "user-1")

    assert result is True


@pytest.mark.asyncio
async def test_sweep_bonus_not_all_complete():
    """Does not award sweep when not all goals complete."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.return_value = {"total": 3, "done": 2}

    result = await check_goal_sweep_bonus(pool, "user-1")

    assert result is False


@pytest.mark.asyncio
async def test_sweep_bonus_already_awarded():
    """Does not double-award sweep bonus in same week."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.return_value = {"total": 3, "done": 3}
    conn.fetchval.return_value = True  # already awarded this week

    result = await check_goal_sweep_bonus(pool, "user-1")

    assert result is False


@pytest.mark.asyncio
async def test_sweep_bonus_no_goals():
    """Returns False when no goals exist."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.return_value = {"total": 0, "done": 0}

    result = await check_goal_sweep_bonus(pool, "user-1")

    assert result is False
