# -*- coding: utf-8 -*-
"""Unit tests for progress tracking service (F6B)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from kiro.progress.service import (
    record_progress_event,
    update_streak,
    award_milestone,
    evaluate_milestones,
    on_plan_completed,
    get_progress_overview,
    get_progress_history,
    get_milestones,
)
from kiro.progress.types import (
    POINTS_PLAN_COMPLETED,
    EVENT_PLAN_COMPLETED,
)


NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


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
# record_progress_event
# =============================================================================

@pytest.mark.asyncio
async def test_record_event_basic():
    """Records event and returns ID."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "event-1"}

    event_id = await record_progress_event(
        pool, "user-1", "plan_completed", 50,
        connection_id="conn-1",
        metadata={"plan_id": "plan-1"},
    )

    assert event_id == "event-1"
    conn.fetchrow.assert_called_once()
    call_args = conn.fetchrow.call_args[0]
    assert "INSERT INTO public.progress_events" in call_args[0]
    assert call_args[1] == "user-1"
    assert call_args[2] == "conn-1"
    assert call_args[3] == "plan_completed"
    assert call_args[4] == 50


@pytest.mark.asyncio
async def test_record_event_no_connection_id():
    """Records event with None connection_id."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "event-2"}

    event_id = await record_progress_event(pool, "user-1", "assessment_completed", 30)

    assert event_id == "event-2"
    call_args = conn.fetchrow.call_args[0]
    assert call_args[2] is None  # connection_id


@pytest.mark.asyncio
async def test_record_event_empty_metadata():
    """Records event with empty metadata as '{}'."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {"id": "event-3"}

    await record_progress_event(pool, "user-1", "partner_connected", 25)

    call_args = conn.fetchrow.call_args[0]
    assert call_args[5] == "{}"  # empty JSON


# =============================================================================
# update_streak
# =============================================================================

@pytest.mark.asyncio
async def test_streak_first_activity():
    """First ever activity creates streak row with current=1."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None  # No existing streak

    result = await update_streak(pool, "user-1")

    assert result["current_streak"] == 1
    assert result["longest_streak"] == 1
    assert result["is_new_day"] is True
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_streak_same_day_no_op():
    """Activity on the same day doesn't increment streak."""
    conn = MockConnection()
    pool = MockPool(conn)
    today = date.today()
    conn.fetchrow.return_value = {
        "id": "streak-1",
        "current_streak": 5,
        "longest_streak": 10,
        "last_active_date": today,
    }

    result = await update_streak(pool, "user-1")

    assert result["current_streak"] == 5
    assert result["longest_streak"] == 10
    assert result["is_new_day"] is False
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_streak_consecutive_day_increments():
    """Activity on the next day increments streak."""
    conn = MockConnection()
    pool = MockPool(conn)
    yesterday = date.today() - timedelta(days=1)
    conn.fetchrow.return_value = {
        "id": "streak-1",
        "current_streak": 5,
        "longest_streak": 10,
        "last_active_date": yesterday,
    }

    result = await update_streak(pool, "user-1")

    assert result["current_streak"] == 6
    assert result["longest_streak"] == 10
    assert result["is_new_day"] is True
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_streak_gap_resets():
    """Activity after a gap resets streak to 1."""
    conn = MockConnection()
    pool = MockPool(conn)
    two_days_ago = date.today() - timedelta(days=2)
    conn.fetchrow.return_value = {
        "id": "streak-1",
        "current_streak": 5,
        "longest_streak": 10,
        "last_active_date": two_days_ago,
    }

    result = await update_streak(pool, "user-1")

    assert result["current_streak"] == 1
    assert result["longest_streak"] == 10
    assert result["is_new_day"] is True


@pytest.mark.asyncio
async def test_streak_new_longest():
    """When current exceeds longest, longest is updated."""
    conn = MockConnection()
    pool = MockPool(conn)
    yesterday = date.today() - timedelta(days=1)
    conn.fetchrow.return_value = {
        "id": "streak-1",
        "current_streak": 10,
        "longest_streak": 10,
        "last_active_date": yesterday,
    }

    result = await update_streak(pool, "user-1")

    assert result["current_streak"] == 11
    assert result["longest_streak"] == 11


# =============================================================================
# award_milestone
# =============================================================================

@pytest.mark.asyncio
async def test_award_milestone_new():
    """Awards a new milestone successfully."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.execute.return_value = "INSERT 0 1"

    awarded = await award_milestone(pool, "user-1", "first_assessment")

    assert awarded is True
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO public.milestones" in call_args[0]
    assert call_args[3] == "first_assessment"
    assert call_args[4] == "Self-Discovery"


@pytest.mark.asyncio
async def test_award_milestone_already_earned():
    """Returns False when milestone already exists (ON CONFLICT DO NOTHING)."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.execute.return_value = "INSERT 0 0"  # conflict, nothing inserted

    awarded = await award_milestone(pool, "user-1", "first_assessment")

    assert awarded is False


@pytest.mark.asyncio
async def test_award_milestone_unknown_key():
    """Returns False for unknown milestone key."""
    conn = MockConnection()
    pool = MockPool(conn)

    awarded = await award_milestone(pool, "user-1", "nonexistent_milestone")

    assert awarded is False
    conn.execute.assert_not_called()


# =============================================================================
# evaluate_milestones
# =============================================================================

@pytest.mark.asyncio
async def test_evaluate_milestones_awards_first_assessment():
    """Awards first_assessment when user has completed assessment."""
    conn = MockConnection()
    pool = MockPool(conn)

    # No existing milestones
    conn.fetch.return_value = []
    # Queries for all milestone conditions:
    conn.fetchval.side_effect = [
        True,   # first_assessment: has completed
        False,  # first_partner: no partner
        False,  # first_report: no report
        0,      # first_plan_complete: count = 0
        0,      # five_plans_complete: count = 0
        0,      # ten_plans_complete: count = 0
        False,  # all_plans_complete
        None,   # relationship_champion: no score
        None,   # communication_master: no dim_scores
        0,      # consistency_star: 0 weeks
        0,      # elite_partner: 0 points
    ]
    # streak ladder: fetchrow for streak
    conn.fetchrow.return_value = None  # no streak row
    # award_milestone calls conn.execute
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "first_assessment" in awarded


@pytest.mark.asyncio
async def test_evaluate_milestones_skips_already_earned():
    """Skips milestones that are already earned."""
    conn = MockConnection()
    pool = MockPool(conn)

    # Already has first_assessment
    conn.fetch.return_value = [{"milestone_key": "first_assessment"}]
    conn.fetchval.side_effect = [
        False,  # first_partner: no partner
        False,  # first_report: no report
        0,      # first_plan_complete
        0,      # five_plans_complete
        0,      # ten_plans_complete
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        0,      # elite_partner
    ]
    conn.fetchrow.return_value = None  # no streak row

    awarded = await evaluate_milestones(pool, "user-1")

    assert "first_assessment" not in awarded
    assert awarded == []


@pytest.mark.asyncio
async def test_evaluate_milestones_seven_day_streak():
    """Awards seven_day_streak when current_streak >= 7."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []  # no existing milestones
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        0,      # first_plan_complete
        0,      # five_plans_complete
        0,      # ten_plans_complete
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        0,      # elite_partner
    ]
    # streak fetchrow returns streak >= 7
    conn.fetchrow.return_value = {"current_streak": 7}
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "three_day_streak" in awarded
    assert "seven_day_streak" in awarded

    assert "seven_day_streak" in awarded


# =============================================================================
# on_plan_completed
# =============================================================================

@pytest.mark.asyncio
async def test_on_plan_completed_records_event():
    """on_plan_completed records event, updates streak, and evaluates milestones."""
    conn = MockConnection()
    pool = MockPool(conn)

    # fetchrow order: record_event, update_streak(None), [milestone award triggers notify→fetchrow],
    #   then evaluate continues to streak check (fetchrow)
    # Award order: first_plan_complete qualifies → award → notify (fetchrow) BEFORE streak check
    conn.fetchrow.side_effect = [
        {"id": "event-1"},   # record_progress_event
        None,                # update_streak: no existing streak (INSERT)
        {"id": "notif-1"},   # notify_milestone_unlocked for first_plan_complete (inside evaluate)
        None,                # evaluate_milestones: streak row (after milestones awarded)
    ]
    # fetch: evaluate_milestones(existing), update_weekly_goals_progress(active goals)
    conn.fetch.side_effect = [
        [],  # evaluate_milestones: no existing milestones
        [],  # update_weekly_goals_progress: no active goals
    ]
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        1,      # first_plan_complete: count = 1 (just completed!)
        1,      # five_plans_complete: count = 1
        1,      # ten_plans_complete: count = 1
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        50,     # elite_partner: 50 points (not enough)
    ]
    conn.execute.return_value = "INSERT 0 1"

    result = await on_plan_completed(pool, "user-1", "plan-1", connection_id="conn-1")

    assert result["event_id"] == "event-1"
    assert result["points"] == POINTS_PLAN_COMPLETED
    assert result["streak"]["current_streak"] == 1
    assert "first_plan_complete" in result["new_milestones"]


@pytest.mark.asyncio
async def test_on_plan_completed_streak_7_day_bonus():
    """Awards streak bonus when streak hits 7-day multiple."""
    conn = MockConnection()
    pool = MockPool(conn)
    yesterday = date.today() - timedelta(days=1)

    # fetchrow order:
    # 1. record_event, 2. update_streak, 3. streak_bonus_event,
    # 4. notify_streak_reached
    # Then evaluate_milestones: milestones that qualify get awarded, each triggers notify
    # first_plan_complete → award → notify; three_day → award → notify; seven_day → award → notify
    # THEN streak check fetchrow
    conn.fetchrow.side_effect = [
        {"id": "event-1"},   # 1. record_progress_event
        {"id": "streak-1", "current_streak": 6, "longest_streak": 6, "last_active_date": yesterday},  # 2. update_streak
        {"id": "event-2"},   # 3. streak bonus record_progress_event
        {"id": "notif-s"},   # 4. notify_streak_reached
        # evaluate_milestones:
        {"id": "notif-m1"},  # 5. notify first_plan_complete (awarded before streak check)
        {"current_streak": 7},  # 6. streak fetchrow (AFTER plan milestones)
        {"id": "notif-m2"},  # 7. notify three_day_streak
        {"id": "notif-m3"},  # 8. notify seven_day_streak
    ]
    # fetch: evaluate_milestones(existing), update_weekly_goals_progress(active goals)
    conn.fetch.side_effect = [
        [],  # evaluate_milestones: no existing milestones
        [],  # update_weekly_goals_progress: no active goals
    ]
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        1,      # first_plan_complete
        1,      # five_plans_complete
        1,      # ten_plans_complete
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        50,     # elite_partner
    ]
    conn.execute.return_value = "INSERT 0 1"

    result = await on_plan_completed(pool, "user-1", "plan-1")

    assert result["streak"]["current_streak"] == 7
    assert "three_day_streak" in result["new_milestones"]
    assert "seven_day_streak" in result["new_milestones"]


# =============================================================================
# get_progress_overview
# =============================================================================

@pytest.mark.asyncio
async def test_overview_empty_user():
    """Returns zeros for a user with no progress."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchval.side_effect = [
        0,     # lifetime points
        0,     # weekly points
        0,     # completed plans
        0,     # milestones count
        None,  # no report score
    ]
    conn.fetchrow.return_value = None  # no streak

    result = await get_progress_overview(pool, "user-1")

    assert result["relationship_health"] == 0
    assert result["weekly_points"] == 0
    assert result["lifetime_points"] == 0
    assert result["current_streak"] == 0
    assert result["completed_plans"] == 0
    assert result["milestones_unlocked"] == 0


@pytest.mark.asyncio
async def test_overview_with_data():
    """Returns correct data for an active user."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchval.side_effect = [
        285,   # lifetime points
        45,    # weekly points
        2,     # completed plans
        4,     # milestones count
        72.5,  # report score
    ]
    conn.fetchrow.return_value = {"current_streak": 5, "longest_streak": 12}

    result = await get_progress_overview(pool, "user-1")

    assert result["relationship_health"] == 72.5
    assert result["weekly_points"] == 45
    assert result["lifetime_points"] == 285
    assert result["current_streak"] == 5
    assert result["completed_plans"] == 2
    assert result["milestones_unlocked"] == 4


# =============================================================================
# get_progress_history
# =============================================================================

@pytest.mark.asyncio
async def test_history_empty():
    """Returns empty list when no events."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = []

    result = await get_progress_history(pool, "user-1")

    assert result["activities"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_history_with_events():
    """Returns recent events formatted correctly."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = [
        {
            "id": "event-1",
            "event_type": "plan_completed",
            "points": 50,
            "metadata": json.dumps({"plan_id": "plan-1"}),
            "created_at": NOW,
        },
        {
            "id": "event-2",
            "event_type": "partner_connected",
            "points": 25,
            "metadata": "{}",
            "created_at": NOW,
        },
    ]

    result = await get_progress_history(pool, "user-1")

    assert result["total"] == 2
    assert result["activities"][0]["event_type"] == "plan_completed"
    assert result["activities"][0]["points"] == 50
    assert result["activities"][0]["metadata"] == {"plan_id": "plan-1"}


# =============================================================================
# get_milestones
# =============================================================================

@pytest.mark.asyncio
async def test_milestones_empty():
    """Returns empty list when no milestones earned."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = []

    result = await get_milestones(pool, "user-1")

    assert result["milestones"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_milestones_with_data():
    """Returns earned milestones formatted correctly."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetch.return_value = [
        {
            "milestone_key": "first_assessment",
            "title": "Self-Discovery",
            "description": "Completed your first assessment",
            "icon": "📝",
            "earned_at": NOW,
        },
    ]

    result = await get_milestones(pool, "user-1")

    assert result["total"] == 1
    assert result["milestones"][0]["key"] == "first_assessment"
    assert result["milestones"][0]["title"] == "Self-Discovery"
    assert result["milestones"][0]["icon"] == "📝"



# =============================================================================
# New milestone condition tests (F6D expansion)
# =============================================================================

@pytest.mark.asyncio
async def test_milestone_five_plans_complete():
    """Awards five_plans_complete when 5+ plan_completed events exist."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [{"milestone_key": "first_plan_complete"}]  # already earned
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        # first_plan already earned, skipped
        5,      # five_plans_complete: count = 5
        5,      # ten_plans_complete: count = 5 (not enough)
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        250,    # elite_partner: not enough
    ]
    conn.fetchrow.return_value = None  # no streak
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "five_plans_complete" in awarded
    assert "ten_plans_complete" not in awarded


@pytest.mark.asyncio
async def test_milestone_ten_plans_complete():
    """Awards ten_plans_complete when 10+ plan_completed events exist."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"milestone_key": "first_plan_complete"},
        {"milestone_key": "five_plans_complete"},
    ]
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        # first_plan already earned, skipped
        # five_plans already earned, skipped
        10,     # ten_plans_complete: count = 10
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        500,    # elite_partner: 500 (enough!)
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "ten_plans_complete" in awarded
    assert "elite_partner" in awarded


@pytest.mark.asyncio
async def test_milestone_three_day_streak():
    """Awards three_day_streak when current streak >= 3."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False,  # first_assessment
        False,  # first_partner
        False,  # first_report
        0, 0, 0,  # plan counts
        False,  # all_plans_complete
        None,   # relationship_champion
        None,   # communication_master
        0,      # consistency_star
        0,      # elite_partner
    ]
    conn.fetchrow.return_value = {"current_streak": 3}
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "three_day_streak" in awarded
    assert "seven_day_streak" not in awarded


@pytest.mark.asyncio
async def test_milestone_fourteen_day_streak():
    """Awards fourteen_day_streak when current streak >= 14."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"milestone_key": "three_day_streak"},
        {"milestone_key": "seven_day_streak"},
    ]
    conn.fetchval.side_effect = [
        False, False, False,  # journey milestones
        0, 0, 0,              # plan counts
        False,                # all_plans_complete
        None,                 # relationship_champion
        None,                 # communication_master
        0,                    # consistency_star
        0,                    # elite_partner
    ]
    conn.fetchrow.return_value = {"current_streak": 14}
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "fourteen_day_streak" in awarded
    assert "thirty_day_streak" not in awarded


@pytest.mark.asyncio
async def test_milestone_thirty_day_streak():
    """Awards thirty_day_streak when current streak >= 30."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = [
        {"milestone_key": "three_day_streak"},
        {"milestone_key": "seven_day_streak"},
        {"milestone_key": "fourteen_day_streak"},
    ]
    conn.fetchval.side_effect = [
        False, False, False,
        0, 0, 0,
        False,
        None, None,
        0, 0,
    ]
    conn.fetchrow.return_value = {"current_streak": 30}
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "thirty_day_streak" in awarded


@pytest.mark.asyncio
async def test_milestone_relationship_champion():
    """Awards relationship_champion when overall score >= 80."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False, False, False,  # journey
        0, 0, 0,              # plans
        False,                # all_plans
        82.5,                 # relationship_champion: score = 82.5
        None,                 # communication_master: no dim_scores
        0,                    # consistency_star
        0,                    # elite_partner
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "relationship_champion" in awarded


@pytest.mark.asyncio
async def test_milestone_communication_master():
    """Awards communication_master when communication dimension score >= 80."""
    conn = MockConnection()
    pool = MockPool(conn)

    dim_scores = json.dumps({
        "communication_style": {"score": 85, "label": "Good"},
        "attachment_style": {"score": 50},
    })

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False, False, False,
        0, 0, 0,
        False,
        60.0,      # relationship_champion: score 60 (not enough)
        dim_scores, # communication_master: has dimension_scores
        0,         # consistency_star
        0,         # elite_partner
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "communication_master" in awarded
    assert "relationship_champion" not in awarded


@pytest.mark.asyncio
async def test_milestone_consistency_star():
    """Awards consistency_star when active for 4 consecutive weeks."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False, False, False,
        0, 0, 0,
        False,
        None, None,
        4,     # consistency_star: 4 distinct weeks
        0,     # elite_partner
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "consistency_star" in awarded


@pytest.mark.asyncio
async def test_milestone_elite_partner():
    """Awards elite_partner when lifetime points >= 500."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False, False, False,
        0, 0, 0,
        False,
        None, None,
        0,     # consistency_star
        500,   # elite_partner: exactly 500
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "elite_partner" in awarded


@pytest.mark.asyncio
async def test_milestone_not_awarded_below_threshold():
    """Does not award elite_partner when points below 500."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetch.return_value = []
    conn.fetchval.side_effect = [
        False, False, False,
        0, 0, 0,
        False,
        None, None,
        0,     # consistency_star
        499,   # elite_partner: 499 (not enough)
    ]
    conn.fetchrow.return_value = None
    conn.execute.return_value = "INSERT 0 1"

    awarded = await evaluate_milestones(pool, "user-1")

    assert "elite_partner" not in awarded
