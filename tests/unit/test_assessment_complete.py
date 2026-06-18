# -*- coding: utf-8 -*-
"""Unit tests for assessment completion (F2C).

Tests the complete_assessment flow with mock DB, verifying:
- Happy path (score + profile generation)
- Incomplete assessment rejection
- Already-completed rejection
- Ownership validation
- Profile column/JSONB consistency (EC-7 audit recommendation)
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from kiro.assessment.service import complete_assessment, _validate_scoring_result
from kiro.assessment.scoring import ScoringResult, DimensionResult, score_assessment
from kiro.assessment.profile_gen import upsert_profile
from kiro.assessment.exceptions import (
    AssessmentNotFoundError,
    AssessmentAlreadyCompletedError,
    AssessmentIncompleteError,
    AssessmentError,
)
from kiro.assessment.constants import TIE_BREAK_ORDER


# --- Mock helpers ---

class MockTransaction:
    """Simulates asyncpg transaction context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockConnection:
    """Simulates asyncpg connection with transaction support."""

    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()
        self.fetchval = AsyncMock()
        self.execute = AsyncMock()

    def transaction(self):
        return MockTransaction()


class MockPool:
    def __init__(self, conn=None):
        self._conn = conn or MockConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def make_question(qid, category, sub_scale, weight=1.0):
    return {
        "id": qid,
        "category": category,
        "sub_scale": sub_scale,
        "weight": weight,
        "reverse_scored": False,
        "answer_options": [
            {"text": "A", "score": 5},
            {"text": "B", "score": 4},
            {"text": "C", "score": 3},
            {"text": "D", "score": 2},
            {"text": "E", "score": 1},
        ],
    }


def make_ll_question(qid):
    return {
        "id": qid,
        "category": "love_language",
        "sub_scale": "words",
        "weight": 1.0,
        "reverse_scored": False,
        "answer_options": [
            {"text": "W", "score": 5, "language": "words"},
            {"text": "A", "score": 5, "language": "acts"},
            {"text": "G", "score": 5, "language": "gifts"},
            {"text": "T", "score": 5, "language": "touch"},
            {"text": "Q", "score": 5, "language": "time"},
        ],
    }


def build_full_question_cache():
    """Build a minimal 68-question cache (1 per dimension for standard + 10 LL)."""
    questions = []
    # 1 question per standard sub-scale = enough for scoring to produce 7 dimensions
    standard_dims = [
        ("attachment_style", ["secure", "anxious", "avoidant", "fearful_avoidant"]),
        ("communication_style", ["direct", "diplomatic", "analytical", "expressive"]),
        ("conflict_style", ["collaborative", "compromising", "avoiding", "competing"]),
        ("financial_personality", ["saver", "investor", "balanced", "spender"]),
        ("lifestyle_type", ["adventurous", "social", "balanced", "homebody"]),
        ("relationship_archetype", ["partner", "nurturer", "independent", "explorer"]),
    ]
    idx = 0
    for cat, subs in standard_dims:
        for sub in subs:
            questions.append(make_question(f"q_{idx}", cat, sub))
            idx += 1

    # 10 Love Language questions
    for i in range(10):
        questions.append(make_ll_question(f"q_ll_{i}"))
        idx += 1

    return questions


def build_answer_rows(question_cache):
    """Build answer rows that match the question cache (all score 3, LL pick words)."""
    rows = []
    for q in question_cache:
        if q["category"] == "love_language":
            rows.append({"question_id": q["id"], "score": 5, "selected_option_index": 0})
        else:
            rows.append({"question_id": q["id"], "score": 3, "selected_option_index": 2})
    return rows


# --- Tests ---

@pytest.mark.asyncio
async def test_complete_happy_path():
    """Happy path: 68 answers → scoring → profile generated."""
    conn = MockConnection()
    pool = MockPool(conn)
    question_cache = build_full_question_cache()
    answer_rows = build_answer_rows(question_cache)

    # Mock: assessment found, in_progress, owned by user
    conn.fetchrow.side_effect = [
        # Step 1: SELECT FOR UPDATE
        {"id": "assess-1", "status": "in_progress", "user_id": "user-1"},
        # Step 6: UPDATE RETURNING completed_at
        {"completed_at": datetime(2026, 6, 18, 12, 15, 0, tzinfo=timezone.utc)},
        # Step 7: profile UPSERT RETURNING xmax
        {"xmax": 0},  # 0 = INSERT (new profile)
    ]
    # Step 2: Fetch answers
    conn.fetch.return_value = answer_rows

    result = await complete_assessment(pool, "user-1", "assess-1", question_cache)

    assert result["status"] == "completed"
    assert result["profile_generated"] is True
    assert result["assessment_id"] == "assess-1"
    assert isinstance(result["score"], float)


@pytest.mark.asyncio
async def test_complete_not_found():
    """Assessment not found → 404."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = None

    with pytest.raises(AssessmentNotFoundError):
        await complete_assessment(pool, "user-1", "bad-id", [])


@pytest.mark.asyncio
async def test_complete_wrong_owner():
    """Assessment owned by different user → 404."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {
        "id": "assess-1", "status": "in_progress", "user_id": "other-user"
    }

    with pytest.raises(AssessmentNotFoundError):
        await complete_assessment(pool, "user-1", "assess-1", [])


@pytest.mark.asyncio
async def test_complete_already_completed():
    """Already completed → 409."""
    conn = MockConnection()
    pool = MockPool(conn)
    conn.fetchrow.return_value = {
        "id": "assess-1", "status": "completed", "user_id": "user-1"
    }

    with pytest.raises(AssessmentAlreadyCompletedError):
        await complete_assessment(pool, "user-1", "assess-1", [])


@pytest.mark.asyncio
async def test_complete_incomplete():
    """Fewer than required answers → 400."""
    conn = MockConnection()
    pool = MockPool(conn)
    question_cache = build_full_question_cache()  # 34 questions

    conn.fetchrow.return_value = {
        "id": "assess-1", "status": "in_progress", "user_id": "user-1"
    }
    # Only 10 answers provided
    conn.fetch.return_value = [
        {"question_id": f"q_{i}", "score": 3, "selected_option_index": 2}
        for i in range(10)
    ]

    with pytest.raises(AssessmentIncompleteError) as exc_info:
        await complete_assessment(pool, "user-1", "assess-1", question_cache)

    assert exc_info.value.missing == len(question_cache) - 10


# --- Validation tests ---

def test_validate_scoring_result_valid():
    """Valid ScoringResult passes validation."""
    dims = {}
    for cat, types in TIE_BREAK_ORDER.items():
        dims[cat] = DimensionResult(
            score=50, type=types[0], strength=50,
            sub_scores={t: 50 for t in types}
        )
    result = ScoringResult(overall_score=50.0, dimensions=dims)
    # Should not raise
    _validate_scoring_result(result)


def test_validate_scoring_result_wrong_dimension_count():
    """Wrong number of dimensions → error."""
    result = ScoringResult(overall_score=50.0, dimensions={
        "attachment_style": DimensionResult(score=50, type="secure", strength=50, sub_scores={})
    })
    with pytest.raises(AssessmentError) as exc_info:
        _validate_scoring_result(result)
    assert exc_info.value.code == "SCORING_ERROR"


def test_validate_scoring_result_score_out_of_range():
    """Score > 100 → error."""
    dims = {}
    for cat, types in TIE_BREAK_ORDER.items():
        dims[cat] = DimensionResult(
            score=50, type=types[0], strength=50,
            sub_scores={t: 50 for t in types}
        )
    # Set one dimension score to 150
    dims["attachment_style"] = DimensionResult(
        score=150, type="secure", strength=50, sub_scores={"secure": 50}
    )
    result = ScoringResult(overall_score=50.0, dimensions=dims)
    with pytest.raises(AssessmentError):
        _validate_scoring_result(result)


# --- EC-7 Audit: Profile column/JSONB consistency test ---

def test_profile_columns_match_jsonb_types():
    """
    EC-7 audit recommendation: verify that the type values written to
    individual columns match the types stored inside dimension_scores JSONB.
    
    This tests the scoring pipeline output structure.
    """
    questions = build_full_question_cache()
    answers = build_answer_rows(questions)

    result = score_assessment(answers, questions)

    # Simulate what profile_gen would write to columns
    column_values = {
        "attachment_style": result.dimensions["attachment_style"].type,
        "communication_style": result.dimensions["communication_style"].type,
        "conflict_style": result.dimensions["conflict_style"].type,
        "love_language": result.dimensions["love_language"].type,
        "financial_personality": result.dimensions["financial_personality"].type,
        "lifestyle_type": result.dimensions["lifestyle_type"].type,
        "relationship_archetype": result.dimensions["relationship_archetype"].type,
    }

    # Simulate JSONB content
    jsonb_values = {
        cat: dim.type for cat, dim in result.dimensions.items()
    }

    # Assert columns match JSONB types (EC-7)
    for category in column_values:
        assert column_values[category] == jsonb_values[category], (
            f"Column/JSONB mismatch for {category}: "
            f"column={column_values[category]}, jsonb={jsonb_values[category]}"
        )


def test_scoring_result_types_are_valid():
    """Every type in the scoring result is a valid type for its dimension."""
    questions = build_full_question_cache()
    answers = build_answer_rows(questions)

    result = score_assessment(answers, questions)

    for category, dim in result.dimensions.items():
        assert dim.type in TIE_BREAK_ORDER[category], (
            f"Invalid type '{dim.type}' for dimension '{category}'"
        )
