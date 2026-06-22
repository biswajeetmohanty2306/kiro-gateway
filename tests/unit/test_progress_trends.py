# -*- coding: utf-8 -*-
"""Unit tests for health trends system (F6D)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from kiro.progress.trends import (
    create_health_snapshot,
    get_latest_snapshot,
    calculate_trend_direction,
    get_health_trends,
    _get_week_start,
)


NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
TODAY = date(2026, 6, 22)  # Monday


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
# _get_week_start
# =============================================================================

def test_week_start_monday():
    """Monday returns itself."""
    assert _get_week_start(date(2026, 6, 22)) == date(2026, 6, 22)


def test_week_start_friday():
    """Friday returns the preceding Monday."""
    assert _get_week_start(date(2026, 6, 26)) == date(2026, 6, 22)


def test_week_start_sunday():
    """Sunday returns the preceding Monday."""
    assert _get_week_start(date(2026, 6, 28)) == date(2026, 6, 22)


# =============================================================================
# calculate_trend_direction
# =============================================================================

def test_trend_up():
    """More than 5% increase → up."""
    result = calculate_trend_direction(60, 50)
    assert result["direction"] == "up"
    assert result["delta"] == 10
    assert result["percentage_change"] == 20.0


def test_trend_down():
    """More than 5% decrease → down."""
    result = calculate_trend_direction(40, 50)
    assert result["direction"] == "down"
    assert result["delta"] == -10
    assert result["percentage_change"] == -20.0


def test_trend_flat():
    """Less than 5% change → flat."""
    result = calculate_trend_direction(51, 50)
    assert result["direction"] == "flat"
    assert result["delta"] == 1


def test_trend_none_current():
    """None current score → flat."""
    result = calculate_trend_direction(None, 50)
    assert result["direction"] == "flat"
    assert result["delta"] == 0


def test_trend_none_previous():
    """None previous score → flat."""
    result = calculate_trend_direction(60, None)
    assert result["direction"] == "flat"


def test_trend_both_none():
    """Both None → flat."""
    result = calculate_trend_direction(None, None)
    assert result["direction"] == "flat"


def test_trend_from_zero():
    """Previous 0, current > 0 → up with 100% change."""
    result = calculate_trend_direction(50, 0)
    assert result["direction"] == "up"
    assert result["percentage_change"] == 100


def test_trend_same_value():
    """Same value → flat with 0% change."""
    result = calculate_trend_direction(50, 50)
    assert result["direction"] == "flat"
    assert result["delta"] == 0
    assert result["percentage_change"] == 0


# =============================================================================
# create_health_snapshot
# =============================================================================

@pytest.mark.asyncio
async def test_create_snapshot_success():
    """Creates a snapshot with correct values."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.side_effect = [
        72.5,   # compatibility_score
        45,     # engagement_score (weekly points)
        3,      # plans_completed
    ]
    conn.fetchrow.side_effect = [
        {"current_streak": 5},  # streak
        {"id": "snap-1", "week_start": TODAY, "compatibility_score": 72.5,
         "engagement_score": 45, "plans_completed": 3, "streak_days": 5},  # UPSERT RETURNING
    ]

    result = await create_health_snapshot(pool, "user-1", "conn-1")

    assert result is not None
    assert result["id"] == "snap-1"
    assert result["compatibility_score"] == 72.5
    assert result["engagement_score"] == 45
    assert result["plans_completed"] == 3
    assert result["streak_days"] == 5


@pytest.mark.asyncio
async def test_create_snapshot_no_report():
    """Creates snapshot with None compatibility score when no report exists."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.side_effect = [
        None,   # no compatibility report
        20,     # engagement_score
        1,      # plans_completed
    ]
    conn.fetchrow.side_effect = [
        None,   # no streak
        {"id": "snap-2", "week_start": TODAY, "compatibility_score": None,
         "engagement_score": 20, "plans_completed": 1, "streak_days": 0},
    ]

    result = await create_health_snapshot(pool, "user-1")

    assert result is not None
    assert result["compatibility_score"] is None
    assert result["streak_days"] == 0


@pytest.mark.asyncio
async def test_create_snapshot_error_returns_none():
    """Returns None on database error."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchval.side_effect = Exception("DB error")

    result = await create_health_snapshot(pool, "user-1")

    assert result is None


@pytest.mark.asyncio
async def test_create_snapshot_idempotent():
    """UPSERT semantics: second call for same week updates existing row."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.side_effect = [80.0, 60, 5]
    conn.fetchrow.side_effect = [
        {"current_streak": 10},
        # UPSERT returns same id (ON CONFLICT DO UPDATE)
        {"id": "snap-1", "week_start": TODAY, "compatibility_score": 80.0,
         "engagement_score": 60, "plans_completed": 5, "streak_days": 10},
    ]

    result = await create_health_snapshot(pool, "user-1")

    assert result["id"] == "snap-1"
    # Verify UPSERT query was used
    insert_call = conn.fetchrow.call_args_list[1][0][0]
    assert "ON CONFLICT" in insert_call


# =============================================================================
# get_latest_snapshot
# =============================================================================

@pytest.mark.asyncio
async def test_get_latest_snapshot_exists():
    """Returns the most recent snapshot."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.return_value = {
        "id": "snap-1", "week_start": TODAY,
        "compatibility_score": 72.5, "engagement_score": 45,
        "plans_completed": 3, "streak_days": 5,
    }

    result = await get_latest_snapshot(pool, "user-1")

    assert result is not None
    assert result["compatibility_score"] == 72.5


@pytest.mark.asyncio
async def test_get_latest_snapshot_none():
    """Returns None when no snapshots exist."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    result = await get_latest_snapshot(pool, "user-1")

    assert result is None


# =============================================================================
# get_health_trends
# =============================================================================

@pytest.mark.asyncio
async def test_get_trends_with_data():
    """Returns snapshots and trend when data exists."""
    conn = MockConnection()
    pool = MockPool(conn)

    # First call: check if current week snapshot exists
    conn.fetchval.return_value = True  # snapshot exists

    # Second call: fetch snapshots
    conn.fetch.return_value = [
        {"week_start": date(2026, 6, 22), "compatibility_score": 72.5,
         "engagement_score": 60, "plans_completed": 5, "streak_days": 7},
        {"week_start": date(2026, 6, 15), "compatibility_score": 70.0,
         "engagement_score": 45, "plans_completed": 3, "streak_days": 5},
        {"week_start": date(2026, 6, 8), "compatibility_score": 68.0,
         "engagement_score": 30, "plans_completed": 2, "streak_days": 3},
    ]

    result = await get_health_trends(pool, "user-1", weeks=12)

    assert result["total"] == 3
    assert len(result["snapshots"]) == 3
    assert result["snapshots"][0]["engagement_score"] == 60
    # Trend: 60 vs 45 = +33% → up
    assert result["trend"]["direction"] == "up"
    assert result["trend"]["delta"] == 15


@pytest.mark.asyncio
async def test_get_trends_single_snapshot():
    """Returns flat trend when only 1 snapshot exists."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.return_value = True  # snapshot exists

    conn.fetch.return_value = [
        {"week_start": date(2026, 6, 22), "compatibility_score": 72.5,
         "engagement_score": 45, "plans_completed": 3, "streak_days": 5},
    ]

    result = await get_health_trends(pool, "user-1")

    assert result["total"] == 1
    assert result["trend"]["direction"] == "flat"


@pytest.mark.asyncio
async def test_get_trends_creates_snapshot_lazily():
    """Creates snapshot for current week if none exists."""
    conn = MockConnection()
    pool = MockPool(conn)

    # First pool.acquire: check existence → False (no snapshot this week)
    conn.fetchval.side_effect = [
        False,  # snapshot does not exist for current week
        # create_health_snapshot: compatibility_score, engagement, plans
        72.5, 45, 3,
        # Then get_health_trends second check: fetch snapshots (via conn.fetch)
    ]
    # create_health_snapshot fetchrow: streak + UPSERT
    conn.fetchrow.side_effect = [
        {"current_streak": 5},
        {"id": "snap-new", "week_start": TODAY, "compatibility_score": 72.5,
         "engagement_score": 45, "plans_completed": 3, "streak_days": 5},
    ]
    # Final fetch for trends
    conn.fetch.return_value = [
        {"week_start": TODAY, "compatibility_score": 72.5,
         "engagement_score": 45, "plans_completed": 3, "streak_days": 5},
    ]

    result = await get_health_trends(pool, "user-1")

    assert result["total"] == 1
    assert result["snapshots"][0]["engagement_score"] == 45


@pytest.mark.asyncio
async def test_get_trends_empty():
    """Returns empty list when no data and snapshot creation fails."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.side_effect = [
        False,  # no snapshot exists
        # create_health_snapshot fails
        Exception("DB error"),
    ]
    # After failed creation, fetch returns empty
    conn.fetch.return_value = []

    result = await get_health_trends(pool, "user-1")

    assert result["total"] == 0
    assert result["snapshots"] == []
    assert result["trend"]["direction"] == "flat"


@pytest.mark.asyncio
async def test_get_trends_declining():
    """Detects declining trend when engagement drops > 5%."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchval.return_value = True

    conn.fetch.return_value = [
        {"week_start": date(2026, 6, 22), "compatibility_score": 70.0,
         "engagement_score": 20, "plans_completed": 3, "streak_days": 1},
        {"week_start": date(2026, 6, 15), "compatibility_score": 70.0,
         "engagement_score": 50, "plans_completed": 3, "streak_days": 7},
    ]

    result = await get_health_trends(pool, "user-1")

    # 20 vs 50 = -60% → down
    assert result["trend"]["direction"] == "down"
    assert result["trend"]["delta"] == -30
