# -*- coding: utf-8 -*-
"""Unit tests for the assessment service (F2A).

Tests use a mock pool that simulates asyncpg behavior without a real database.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from kiro.assessment.service import (
    get_or_create_assessment,
    get_questions,
    submit_answers,
    get_progress,
)
from kiro.assessment.schemas import AnswerItem
from kiro.assessment.exceptions import (
    AssessmentNotFoundError,
    AssessmentAlreadyCompletedError,
    InvalidQuestionError,
)


# --- Mock pool helper ---

class MockConnection:
    """Simulates an asyncpg connection with fetchrow/fetch/fetchval/execute."""

    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()
        self.fetchval = AsyncMock()
        self.execute = AsyncMock()


class MockPool:
    """Simulates the AuditConnectionPool.acquire() pattern."""

    def __init__(self, conn: MockConnection):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def make_pool(conn=None):
    if conn is None:
        conn = MockConnection()
    return MockPool(conn), conn


# --- Tests: get_or_create_assessment ---

@pytest.mark.asyncio
async def test_get_or_create_returns_existing():
    """If an in-progress assessment exists, return it (not create new)."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.return_value = {
        "id": "test-uuid-123",
        "status": "in_progress",
        "started_at": datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
    }
    conn.fetchval.return_value = 10  # 10 answers already

    data, created = await get_or_create_assessment(pool, "user-abc")

    assert created is False
    assert data["assessment_id"] == "test-uuid-123"
    assert data["status"] == "in_progress"
    assert data["progress"]["answered"] == 10
    assert data["progress"]["total"] == 68


@pytest.mark.asyncio
async def test_get_or_create_creates_new():
    """If no in-progress assessment, create a new one."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    # First fetchrow (check existing): None
    # Second fetchrow (INSERT RETURNING): new row
    conn.fetchrow.side_effect = [
        None,
        {
            "id": "new-uuid-456",
            "status": "in_progress",
            "started_at": datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]

    data, created = await get_or_create_assessment(pool, "user-abc")

    assert created is True
    assert data["assessment_id"] == "new-uuid-456"
    assert data["progress"]["answered"] == 0


# --- Tests: get_questions ---

@pytest.mark.asyncio
async def test_get_questions_strips_scores():
    """Questions returned to client must not include score/weight/sub_scale."""
    pool, conn = make_pool()

    conn.fetch.return_value = [
        {
            "id": "q_attachment_01",
            "category": "attachment_style",
            "order_index": 1,
            "text": "When someone shares something...",
            "answer_options": json.dumps([
                {"text": "Option A", "score": 5},
                {"text": "Option B", "score": 4},
                {"text": "Option C", "score": 3},
                {"text": "Option D", "score": 2},
                {"text": "Option E", "score": 1},
            ]),
        }
    ]

    questions = await get_questions(pool)

    assert len(questions) == 1
    q = questions[0]
    assert q["id"] == "q_attachment_01"
    assert q["category"] == "attachment_style"
    # Verify no score exposed
    for opt in q["answer_options"]:
        assert "score" not in opt
        assert "text" in opt
        assert "index" in opt


# --- Tests: submit_answers ---

@pytest.mark.asyncio
async def test_submit_answers_computes_score():
    """Answers should have server-computed scores, not client-supplied."""
    pool, conn = make_pool()

    # Assessment exists and is in-progress
    conn.fetchrow.return_value = {
        "id": "assess-1",
        "status": "in_progress",
        "user_id": "user-1",
    }

    # Question metadata
    conn.fetch.return_value = [
        {
            "id": "q_attachment_01",
            "answer_options": json.dumps([
                {"text": "A", "score": 5},
                {"text": "B", "score": 4},
                {"text": "C", "score": 3},
                {"text": "D", "score": 2},
                {"text": "E", "score": 1},
            ]),
            "reverse_scored": False,
        }
    ]

    # Answer count after insertion
    conn.fetchval.return_value = 1

    answers = [AnswerItem(question_id="q_attachment_01", selected_option_index=2)]
    result = await submit_answers(pool, "user-1", "assess-1", answers)

    assert result["accepted"] == 1
    assert result["progress"]["answered"] == 1

    # Verify execute was called with computed score = 3 (option index 2, score 3)
    call_args = conn.execute.call_args[0]
    assert call_args[4] == 3  # score argument


@pytest.mark.asyncio
async def test_submit_answers_reverse_scoring():
    """Reverse-scored questions should apply 6 - raw_score."""
    pool, conn = make_pool()

    conn.fetchrow.return_value = {
        "id": "assess-1",
        "status": "in_progress",
        "user_id": "user-1",
    }

    conn.fetch.return_value = [
        {
            "id": "q_attachment_03",
            "answer_options": json.dumps([
                {"text": "A", "score": 5},
                {"text": "B", "score": 4},
                {"text": "C", "score": 3},
                {"text": "D", "score": 2},
                {"text": "E", "score": 1},
            ]),
            "reverse_scored": True,  # REVERSE
        }
    ]

    conn.fetchval.return_value = 1

    # User selects option 0 (raw score 5) → reversed = 6 - 5 = 1
    answers = [AnswerItem(question_id="q_attachment_03", selected_option_index=0)]
    await submit_answers(pool, "user-1", "assess-1", answers)

    call_args = conn.execute.call_args[0]
    assert call_args[4] == 1  # reversed score: 6 - 5 = 1


@pytest.mark.asyncio
async def test_submit_answers_not_found():
    """Submitting to non-existent assessment raises NotFoundError."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None  # No assessment found

    answers = [AnswerItem(question_id="q_attachment_01", selected_option_index=0)]

    with pytest.raises(AssessmentNotFoundError):
        await submit_answers(pool, "user-1", "bad-id", answers)


@pytest.mark.asyncio
async def test_submit_answers_already_completed():
    """Submitting to completed assessment raises AlreadyCompletedError."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = {
        "id": "assess-1",
        "status": "completed",
        "user_id": "user-1",
    }

    answers = [AnswerItem(question_id="q_attachment_01", selected_option_index=0)]

    with pytest.raises(AssessmentAlreadyCompletedError):
        await submit_answers(pool, "user-1", "assess-1", answers)


@pytest.mark.asyncio
async def test_submit_answers_invalid_question():
    """Submitting with unknown question_id raises InvalidQuestionError."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = {
        "id": "assess-1",
        "status": "in_progress",
        "user_id": "user-1",
    }
    conn.fetch.return_value = []  # No questions found

    answers = [AnswerItem(question_id="q_nonexistent", selected_option_index=0)]

    with pytest.raises(InvalidQuestionError):
        await submit_answers(pool, "user-1", "assess-1", answers)


# --- Tests: get_progress ---

@pytest.mark.asyncio
async def test_get_progress_in_progress():
    """Returns correct progress for an in-progress assessment."""
    pool, conn = make_pool()
    from datetime import datetime, timezone

    conn.fetchrow.return_value = {
        "id": "assess-1",
        "status": "in_progress",
        "started_at": datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
        "user_id": "user-1",
    }
    conn.fetchval.return_value = 42

    result = await get_progress(pool, "user-1", "assess-1")

    assert result["assessment_id"] == "assess-1"
    assert result["progress"]["answered"] == 42
    assert result["progress"]["total"] == 68


@pytest.mark.asyncio
async def test_get_progress_not_found():
    """Raises NotFoundError when no assessment exists."""
    pool, conn = make_pool()
    conn.fetchrow.return_value = None

    with pytest.raises(AssessmentNotFoundError):
        await get_progress(pool, "user-1", None)
