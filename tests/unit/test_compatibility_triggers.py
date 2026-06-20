# -*- coding: utf-8 -*-
"""Unit tests for automatic compatibility report generation triggers (F5E)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from kiro.compatibility.triggers import try_generate_compatibility_report


NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

SAMPLE_DIM_SCORES = json.dumps({
    "attachment_style": {"type": "secure", "strength": 85, "score": 80, "sub_scores": {}},
    "communication_style": {"type": "direct", "strength": 75, "score": 70, "sub_scores": {}},
    "conflict_style": {"type": "collaborative", "strength": 90, "score": 85, "sub_scores": {}},
    "love_language": {"type": "touch", "strength": 70, "score": 65, "sub_scores": {}},
    "financial_personality": {"type": "investor", "strength": 80, "score": 75, "sub_scores": {}},
    "lifestyle_type": {"type": "adventurous", "strength": 78, "score": 72, "sub_scores": {}},
    "relationship_archetype": {"type": "partner", "strength": 82, "score": 78, "sub_scores": {}},
})


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


# --- Case 1: Both profiles exist + accept invite → report generated ---

@pytest.mark.asyncio
async def test_trigger_both_profiles_exist_generates_report():
    """When both users have profiles and connection is accepted, report is generated."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = [
        # 1. Connection lookup
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": "user-b", "status": "accepted"},
        # 2. Inviter profile
        {"id": "profile-a", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        # 3. Invitee profile
        {"id": "profile-b", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        # 4. UPSERT report returning
        {"id": "report-1"},
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is True
    # Should have called execute for DELETE old plans + 3 INSERT plans
    assert conn.execute.call_count == 4


# --- Case 2: Only inviter has profile + accept invite → no report ---

@pytest.mark.asyncio
async def test_trigger_only_inviter_profile_returns_false():
    """When only the inviter has a profile, no report is generated."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = [
        # 1. Connection lookup
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": "user-b", "status": "accepted"},
        # 2. Inviter profile exists
        {"id": "profile-a", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        # 3. Invitee profile missing
        None,
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is False
    # No DB writes should have happened
    assert conn.execute.call_count == 0


# --- Case 3: Partner connected + complete assessment → report generated ---

@pytest.mark.asyncio
async def test_trigger_partner_connected_assessment_complete_generates():
    """When partner already has profile and user completes assessment, report generates."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = [
        # 1. Connection accepted
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": "user-b", "status": "accepted"},
        # 2. Inviter profile (the user who just completed)
        {"id": "profile-a", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        # 3. Invitee profile (partner already has one)
        {"id": "profile-b", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        # 4. UPSERT report
        {"id": "report-1"},
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is True
    assert conn.execute.call_count == 4  # 1 delete + 3 inserts


# --- Case 4: Assessment retake → report regenerated ---

@pytest.mark.asyncio
async def test_trigger_retake_regenerates_report():
    """When user retakes assessment, the existing report is regenerated (UPSERT)."""
    conn = MockConnection()
    pool = MockPool(conn)

    # Same flow as case 1/3 — UPSERT handles regeneration
    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": "user-b", "status": "accepted"},
        {"id": "profile-a-v2", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        {"id": "profile-b", "dimension_scores": SAMPLE_DIM_SCORES, "created_at": NOW},
        {"id": "report-1"},  # Same report ID due to UPSERT
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is True
    # DELETE old plans still fires (idempotent for regeneration)
    assert conn.execute.call_count == 4


# --- Case 5: No accepted connection → no report ---

@pytest.mark.asyncio
async def test_trigger_connection_not_accepted_returns_false():
    """When connection is pending (not accepted), no report is generated."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": None, "status": "pending"},
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is False
    assert conn.execute.call_count == 0


# --- Case 6: Connection not found → returns False ---

@pytest.mark.asyncio
async def test_trigger_connection_not_found_returns_false():
    """When connection doesn't exist, returns False gracefully."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.return_value = None

    result = await try_generate_compatibility_report(pool, "nonexistent-conn")

    assert result is False


# --- Case 7: Exception during generation → returns False (never raises) ---

@pytest.mark.asyncio
async def test_trigger_exception_returns_false_never_raises():
    """If an unexpected error occurs, the trigger returns False and never raises."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = Exception("Database connection lost")

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is False


# --- Case 8: Only invitee has profile → no report ---

@pytest.mark.asyncio
async def test_trigger_only_invitee_profile_returns_false():
    """When only the invitee has a profile, no report is generated."""
    conn = MockConnection()
    pool = MockPool(conn)

    conn.fetchrow.side_effect = [
        {"id": "conn-1", "inviter_id": "user-a", "invitee_id": "user-b", "status": "accepted"},
        None,  # Inviter profile missing
    ]

    result = await try_generate_compatibility_report(pool, "conn-1")

    assert result is False
    assert conn.execute.call_count == 0
