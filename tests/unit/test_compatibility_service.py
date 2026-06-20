# -*- coding: utf-8 -*-
"""Unit tests for the compatibility service (F5C)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from kiro.compatibility.service import (
    generate_report,
    get_report,
    get_improvement_plans,
    complete_plan,
)
from kiro.compatibility.exceptions import (
    NoPartnerError,
    PartnerNoProfileError,
    UserNoProfileError,
    ReportNotFoundError,
    PlanNotFoundError,
)


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


SAMPLE_DIM_SCORES = json.dumps({
    "attachment_style": {"type": "secure", "strength": 85, "score": 80, "sub_scores": {}},
    "communication_style": {"type": "direct", "strength": 75, "score": 70, "sub_scores": {}},
    "conflict_style": {"type": "collaborative", "strength": 90, "score": 85, "sub_scores": {}},
    "love_language": {"type": "touch", "strength": 70, "score": 65, "sub_scores": {}},
    "financial_personality": {"type": "investor", "strength": 80, "score": 75, "sub_scores": {}},
    "lifestyle_type": {"type": "adventurous", "strength": 78, "score": 72, "sub_scores": {}},
    "relationship_archetype": {"type": "partner", "strength": 82, "score": 78, "sub_scores": {}},
})

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


# --- Tests: get_report ---

@pytest.mark.asyncio
async def test_get_report_no_partner():
    """Returns has_report=False with reason 'no_partner' when no connection."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None  # No connection

    result = await get_report(pool, "user-1")
    assert result["has_report"] is False
    assert result["reason"] == "no_partner"


@pytest.mark.asyncio
async def test_get_report_not_generated():
    """Returns has_report=False with reason 'not_generated' when both profiles exist but no report."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},  # connection
        None,  # no report
        {"id": "profile-b"},  # partner profile exists
        {"id": "profile-a"},  # user profile exists
    ]

    result = await get_report(pool, "user-1")
    assert result["has_report"] is False
    assert result["reason"] == "not_generated"


@pytest.mark.asyncio
async def test_get_report_partner_no_profile():
    """Returns reason 'partner_no_profile' when partner hasn't completed assessment."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},  # connection
        None,  # no report
        None,  # partner profile missing
        {"id": "profile-a"},  # user profile exists
    ]

    result = await get_report(pool, "user-1")
    assert result["has_report"] is False
    assert result["reason"] == "partner_no_profile"


@pytest.mark.asyncio
async def test_get_report_user_no_profile():
    """Returns reason 'user_no_profile' when user hasn't completed assessment."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},  # connection
        None,  # no report
        {"id": "profile-b"},  # partner profile exists
        None,  # user profile missing
    ]

    result = await get_report(pool, "user-1")
    assert result["has_report"] is False
    assert result["reason"] == "user_no_profile"


@pytest.mark.asyncio
async def test_get_report_success():
    """Returns full report when it exists."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},
        {
            "id": "report-1",
            "overall_score": 62.5,
            "dimension_scores": SAMPLE_DIM_SCORES,
            "improvement_potential": 45.0,
            "report_version": "v1",
            "created_at": NOW,
        },
    ]

    result = await get_report(pool, "user-1")
    assert result["has_report"] is True
    assert result["report"]["overall_score"] == 62.5
    assert result["report"]["report_id"] == "report-1"


# --- Tests: generate_report ---

@pytest.mark.asyncio
async def test_generate_no_partner():
    """Raises NoPartnerError when no accepted connection."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    with pytest.raises(NoPartnerError):
        await generate_report(pool, "user-1")


@pytest.mark.asyncio
async def test_generate_user_no_profile():
    """Raises UserNoProfileError when user hasn't completed assessment."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},
        None,  # user profile not found
    ]

    with pytest.raises(UserNoProfileError):
        await generate_report(pool, "user-1")


@pytest.mark.asyncio
async def test_generate_partner_no_profile():
    """Raises PartnerNoProfileError when partner hasn't completed assessment."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},
        {"id": "profile-a", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        None,  # partner profile not found
    ]

    with pytest.raises(PartnerNoProfileError):
        await generate_report(pool, "user-1")


@pytest.mark.asyncio
async def test_generate_success():
    """Successfully generates report when both profiles exist."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-1", "invitee_id": "user-2"},
        {"id": "profile-a", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        {"id": "profile-b", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        {"id": "report-1", "created_at": NOW},  # UPSERT returning
    ]

    result = await generate_report(pool, "user-1")

    assert result["report_id"] == "report-1"
    assert "overall_score" in result
    assert "dimensions" in result
    assert "challenge_plans" in result
    assert len(result["challenge_plans"]) == 3
    # Verify execute was called (DELETE old plans + 3 INSERTs)
    assert conn.execute.call_count == 4  # 1 delete + 3 inserts


# --- Tests: get_improvement_plans ---

@pytest.mark.asyncio
async def test_get_plans_no_partner():
    """Raises NoPartnerError when no connection."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    with pytest.raises(NoPartnerError):
        await get_improvement_plans(pool, "user-1")


@pytest.mark.asyncio
async def test_get_plans_no_report():
    """Raises ReportNotFoundError when no report exists."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1"},  # connection
        None,  # no report
    ]

    with pytest.raises(ReportNotFoundError):
        await get_improvement_plans(pool, "user-1")


@pytest.mark.asyncio
async def test_get_plans_success():
    """Returns plans when they exist."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "conn-1"},
        {"id": "report-1"},
    ]
    conn.fetch.return_value = [
        {
            "id": "plan-1",
            "dimension": "attachment_style",
            "severity": "high",
            "challenge_description": "The pursuit-distance cycle",
            "action_plan": json.dumps(["Step 1", "Step 2"]),
            "weekly_exercise": "The Pause Protocol",
            "completed": False,
            "completed_at": None,
            "created_at": NOW,
        },
    ]

    result = await get_improvement_plans(pool, "user-1")
    assert result["total"] == 1
    assert result["plans"][0]["dimension"] == "attachment_style"
    assert result["plans"][0]["completed"] is False


# --- Tests: complete_plan ---

@pytest.mark.asyncio
async def test_complete_plan_not_found():
    """Raises PlanNotFoundError when plan doesn't belong to user."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    with pytest.raises(PlanNotFoundError):
        await complete_plan(pool, "user-1", "bad-plan-id")


@pytest.mark.asyncio
async def test_complete_plan_success():
    """Marks plan as complete."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.side_effect = [
        {"id": "plan-1", "completed": False},  # verify
        {"id": "plan-1", "completed": True, "completed_at": NOW},  # update
    ]

    result = await complete_plan(pool, "user-1", "plan-1")
    assert result["completed"] is True
    assert result["id"] == "plan-1"
