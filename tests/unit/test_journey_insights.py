# -*- coding: utf-8 -*-
"""Unit tests for the Journey Insights Engine (J4)."""

from __future__ import annotations

import pytest

from kiro.journey.insights import generate_insight, _compute_slope, _answer_to_score


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_reflections(safety_scores: list, conn_scores: list = None) -> list:
    """Build mock reflection history (most recent first)."""
    if conn_scores is None:
        conn_scores = safety_scores

    reflections = []
    for i in range(len(safety_scores)):
        week = len(safety_scores) - i  # Most recent first
        reflections.append({
            "week_number": week,
            "responses": [
                {"question_id": "safety_1", "answer": str(safety_scores[len(safety_scores) - 1 - i])},
                {"question_id": "conn_1", "answer": str(conn_scores[len(conn_scores) - 1 - i])},
            ],
        })
    return reflections


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Insufficient Data
# ─────────────────────────────────────────────────────────────────────────────


class TestInsufficientData:
    """Tests when fewer than 3 reflections exist."""

    def test_empty_history(self):
        """Returns insufficient insight for empty history."""
        result = generate_insight([])
        assert result["trend"] == "insufficient"
        assert result["confidence"] == 0.0
        assert "patterns" in result["message"]

    def test_one_reflection(self):
        """Returns insufficient for single reflection."""
        reflections = _make_reflections([4])
        result = generate_insight(reflections)
        assert result["trend"] == "insufficient"

    def test_two_reflections(self):
        """Returns insufficient for two reflections."""
        reflections = _make_reflections([3, 4])
        result = generate_insight(reflections)
        assert result["trend"] == "insufficient"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Improving Trends
# ─────────────────────────────────────────────────────────────────────────────


class TestImprovingTrends:
    """Tests when scores are increasing over time."""

    def test_steady_increase(self):
        """Detects improving trend when scores rise consistently."""
        reflections = _make_reflections([2, 3, 4, 5])
        result = generate_insight(reflections)
        assert result["trend"] == "improving"
        assert result["confidence"] > 0.5

    def test_gradual_increase(self):
        """Detects improving even with smaller increments."""
        reflections = _make_reflections([3, 3, 4, 4, 5])
        result = generate_insight(reflections)
        assert result["trend"] == "improving"

    def test_safety_specific_improving(self):
        """Detects safety-specific improvement."""
        # Safety improving, connection flat
        reflections = _make_reflections(
            safety_scores=[2, 3, 4, 5],
            conn_scores=[3, 3, 3, 3],
        )
        result = generate_insight(reflections)
        assert result["trend"] == "improving"
        assert result["confidence"] > 0.5

    def test_connection_specific_improving(self):
        """Detects connection-specific improvement."""
        # Connection improving, safety flat
        reflections = _make_reflections(
            safety_scores=[3, 3, 3, 3],
            conn_scores=[2, 3, 4, 5],
        )
        result = generate_insight(reflections)
        assert result["trend"] == "improving"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Stable Trends
# ─────────────────────────────────────────────────────────────────────────────


class TestStableTrends:
    """Tests when scores remain relatively flat."""

    def test_flat_scores(self):
        """Detects stable trend for consistent scores."""
        reflections = _make_reflections([4, 4, 4, 4])
        result = generate_insight(reflections)
        # Should be stable or consistency, not declining
        assert result["trend"] in ("stable", "consistency")

    def test_minor_fluctuation(self):
        """Small fluctuations are still considered stable."""
        reflections = _make_reflections([3, 4, 3, 4, 3])
        result = generate_insight(reflections)
        assert result["trend"] in ("stable", "consistency")
        assert result["confidence"] > 0

    def test_high_stable(self):
        """High consistent scores show as stable."""
        reflections = _make_reflections([5, 5, 5, 5, 5])
        result = generate_insight(reflections)
        assert result["trend"] in ("stable", "consistency")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Declining Trends
# ─────────────────────────────────────────────────────────────────────────────


class TestDecliningTrends:
    """Tests when scores are decreasing — should NEVER show negative messaging."""

    def test_declining_shows_stable(self):
        """Declining scores are framed as stable, never negative."""
        reflections = _make_reflections([5, 4, 3, 2])
        result = generate_insight(reflections)
        # Should NOT say "declining" — always supportive
        assert result["trend"] in ("stable", "consistency")
        # Message should not contain negative words
        msg_lower = result["message"].lower()
        assert "declin" not in msg_lower
        assert "worse" not in msg_lower
        assert "struggling" not in msg_lower

    def test_sharp_decline_still_supportive(self):
        """Even sharp declines produce supportive messaging."""
        reflections = _make_reflections([5, 5, 2, 1])
        result = generate_insight(reflections)
        assert result["trend"] in ("stable", "consistency")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Mixed Answers
# ─────────────────────────────────────────────────────────────────────────────


class TestMixedAnswers:
    """Tests with various answer types (yes/no, scales, mixed)."""

    def test_yes_no_answers(self):
        """Yes/no answers are converted correctly."""
        reflections = []
        for i in range(4):
            reflections.append({
                "week_number": 4 - i,
                "responses": [
                    {"question_id": "safety_1", "answer": str(3 + i)},
                    {"question_id": "conn_2", "answer": "yes"},
                ],
            })
        result = generate_insight(reflections)
        assert result["trend"] in ("improving", "stable", "consistency")
        assert result["confidence"] > 0

    def test_open_answers_ignored(self):
        """Open-ended answers don't affect trend calculation."""
        reflections = []
        for i in range(4):
            reflections.append({
                "week_number": 4 - i,
                "responses": [
                    {"question_id": "safety_1", "answer": str(2 + i)},
                    {"question_id": "open_1", "answer": "Some long text that should be ignored"},
                ],
            })
        result = generate_insight(reflections)
        # Improving or consistency (consecutive weeks also detected)
        assert result["trend"] in ("improving", "consistency")

    def test_v1_payload_format(self):
        """Handles v1 payload format with nested answers array."""
        reflections = []
        for i in range(4):
            reflections.append({
                "week_number": 4 - i,
                "responses": {
                    "version": 1,
                    "answers": [
                        {"question_id": "safety_1", "answer": str(2 + i)},
                        {"question_id": "conn_1", "answer": str(2 + i)},
                    ],
                },
            })
        result = generate_insight(reflections)
        # Improving or consistency (consecutive weeks also detected)
        assert result["trend"] in ("improving", "consistency")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Consistency Detection
# ─────────────────────────────────────────────────────────────────────────────


class TestConsistency:
    """Tests for streak/consistency detection."""

    def test_consecutive_weeks(self):
        """Detects consecutive week streak."""
        reflections = _make_reflections([4, 4, 4, 4, 4])
        # Week numbers 5, 4, 3, 2, 1 (consecutive descending)
        result = generate_insight(reflections)
        # Should detect consistency since weeks are consecutive
        assert result["confidence"] > 0
        assert result["trend"] in ("stable", "consistency")

    def test_non_consecutive_weeks(self):
        """Non-consecutive weeks don't form a streak."""
        reflections = [
            {"week_number": 8, "responses": [{"question_id": "safety_1", "answer": "4"}]},
            {"week_number": 6, "responses": [{"question_id": "safety_1", "answer": "4"}]},
            {"week_number": 3, "responses": [{"question_id": "safety_1", "answer": "4"}]},
        ]
        result = generate_insight(reflections)
        # Should not claim consistency streak
        if result["trend"] == "consistency":
            # The streak detection should only find 1 (no consecutive)
            assert "1" not in result["message"] or "checking in" in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Math Utilities
# ─────────────────────────────────────────────────────────────────────────────


class TestMathUtilities:
    """Tests for the underlying math functions."""

    def test_slope_increasing(self):
        """Positive slope for increasing values."""
        assert _compute_slope([1, 2, 3, 4]) > 0

    def test_slope_decreasing(self):
        """Negative slope for decreasing values."""
        assert _compute_slope([4, 3, 2, 1]) < 0

    def test_slope_flat(self):
        """Zero slope for constant values."""
        assert _compute_slope([3, 3, 3, 3]) == 0.0

    def test_slope_single_value(self):
        """Returns 0 for single value."""
        assert _compute_slope([5]) == 0.0

    def test_slope_empty(self):
        """Returns 0 for empty list."""
        assert _compute_slope([]) == 0.0

    def test_answer_to_score_numeric(self):
        """Converts numeric strings to float."""
        assert _answer_to_score("3") == 3.0
        assert _answer_to_score("5") == 5.0
        assert _answer_to_score("1") == 1.0

    def test_answer_to_score_yes_no(self):
        """Converts yes/no to 5/1."""
        assert _answer_to_score("yes") == 5.0
        assert _answer_to_score("no") == 1.0
        assert _answer_to_score("Yes") == 5.0

    def test_answer_to_score_invalid(self):
        """Returns None for non-numeric non-boolean."""
        assert _answer_to_score("some text") is None
        assert _answer_to_score("") is None

    def test_answer_to_score_out_of_range(self):
        """Returns None for numbers outside 1-5."""
        assert _answer_to_score("0") is None
        assert _answer_to_score("6") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Output Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputStructure:
    """Tests that output always matches expected schema."""

    def test_always_has_required_fields(self):
        """Every insight has trend, confidence, message."""
        test_cases = [
            [],
            _make_reflections([3]),
            _make_reflections([2, 3, 4, 5]),
            _make_reflections([4, 4, 4, 4]),
            _make_reflections([5, 4, 3, 2]),
        ]
        for reflections in test_cases:
            result = generate_insight(reflections)
            assert "trend" in result
            assert "confidence" in result
            assert "message" in result
            assert isinstance(result["trend"], str)
            assert isinstance(result["confidence"], float)
            assert isinstance(result["message"], str)
            assert len(result["message"]) > 0

    def test_confidence_range(self):
        """Confidence is always between 0 and 1."""
        test_cases = [
            _make_reflections([1, 1, 1, 1]),
            _make_reflections([1, 2, 3, 4, 5]),
            _make_reflections([5, 5, 5, 5, 5, 5]),
        ]
        for reflections in test_cases:
            result = generate_insight(reflections)
            assert 0.0 <= result["confidence"] <= 1.0

    def test_trend_values(self):
        """Trend is one of the expected values."""
        valid_trends = {"improving", "stable", "consistency", "insufficient"}
        test_cases = [
            [],
            _make_reflections([2, 3, 4, 5]),
            _make_reflections([4, 4, 4, 4]),
        ]
        for reflections in test_cases:
            result = generate_insight(reflections)
            assert result["trend"] in valid_trends
