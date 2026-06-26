# -*- coding: utf-8 -*-
"""Unit tests for the Couple Synchronization Engine (J5)."""

from __future__ import annotations

import pytest

from kiro.journey.relationship_sync import generate_weekly_relationship_summary


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _answers(safety: str, connection: str) -> list:
    """Build a minimal answer set."""
    return [
        {"question_id": "safety_1", "answer": safety},
        {"question_id": "conn_1", "answer": connection},
    ]


def _full_answers(safety: str, conn_scale: str, conn_yn: str) -> list:
    """Build a more complete answer set."""
    return [
        {"question_id": "safety_1", "answer": safety},
        {"question_id": "conn_1", "answer": conn_scale},
        {"question_id": "conn_2", "answer": conn_yn},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Both Improving (GROWING)
# ─────────────────────────────────────────────────────────────────────────────


class TestBothImproving:
    """Both partners report high aligned scores → GROWING."""

    def test_both_high_aligned(self):
        """Both scoring 4+ → GROWING."""
        result = generate_weekly_relationship_summary(
            _answers("4", "5"),
            _answers("4", "4"),
        )
        assert result["status"] == "GROWING"
        assert result["confidence"] > 0.6
        assert "positive direction" in result["summary"]

    def test_both_very_high(self):
        """Both scoring 5 → GROWING with high confidence."""
        result = generate_weekly_relationship_summary(
            _answers("5", "5"),
            _answers("5", "5"),
        )
        assert result["status"] == "GROWING"
        assert result["confidence"] >= 0.8

    def test_both_above_threshold(self):
        """Both just above growth threshold → GROWING."""
        result = generate_weekly_relationship_summary(
            _answers("4", "4"),
            _answers("4", "3"),
        )
        # Average for each is 4 and 3.5 — both >= 3.5 and within 1.0
        assert result["status"] == "GROWING"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Both Low/Aligned (SYNCED)
# ─────────────────────────────────────────────────────────────────────────────


class TestSynced:
    """Both partners report similar scores that aren't high → SYNCED."""

    def test_both_moderate_aligned(self):
        """Both scoring 3 → SYNCED (not GROWING — below threshold)."""
        result = generate_weekly_relationship_summary(
            _answers("3", "3"),
            _answers("3", "3"),
        )
        assert result["status"] == "SYNCED"
        assert "similar" in result["summary"].lower()

    def test_close_but_not_high(self):
        """Aligned scores below growth threshold → SYNCED."""
        result = generate_weekly_relationship_summary(
            _answers("2", "3"),
            _answers("3", "2"),
        )
        assert result["status"] == "SYNCED"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Different Answers (MISALIGNED)
# ─────────────────────────────────────────────────────────────────────────────


class TestMisaligned:
    """Partners report noticeably different experiences → MISALIGNED."""

    def test_large_difference(self):
        """One scores 5, other scores 2 → MISALIGNED."""
        result = generate_weekly_relationship_summary(
            _answers("5", "5"),
            _answers("2", "2"),
        )
        assert result["status"] == "MISALIGNED"
        assert result["confidence"] > 0.4

    def test_never_blames(self):
        """MISALIGNED messaging never uses blame language."""
        result = generate_weekly_relationship_summary(
            _answers("5", "5"),
            _answers("1", "1"),
        )
        msg = result["summary"].lower()
        assert "wrong" not in msg
        assert "fault" not in msg
        assert "blame" not in msg
        assert "problem" not in msg

    def test_misaligned_supportive_highlight(self):
        """MISALIGNED highlight is supportive."""
        result = generate_weekly_relationship_summary(
            _answers("5", "4"),
            _answers("2", "2"),
        )
        assert result["status"] == "MISALIGNED"
        assert "normal" in result["highlight"].lower() or "conversation" in result["highlight"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Only One Submitted (CHECK_IN)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckIn:
    """Only one partner has submitted → CHECK_IN."""

    def test_only_user_submitted(self):
        """User submitted, partner hasn't → CHECK_IN."""
        result = generate_weekly_relationship_summary(
            _answers("4", "4"),
            None,
        )
        assert result["status"] == "CHECK_IN"
        assert "partner" in result["summary"].lower()

    def test_only_partner_submitted(self):
        """Partner submitted, user hasn't → CHECK_IN."""
        result = generate_weekly_relationship_summary(
            None,
            _answers("4", "4"),
        )
        assert result["status"] == "CHECK_IN"

    def test_user_empty_list(self):
        """User has empty answer list → CHECK_IN."""
        result = generate_weekly_relationship_summary(
            [],
            _answers("4", "4"),
        )
        assert result["status"] == "CHECK_IN"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Neither Submitted (INSUFFICIENT)
# ─────────────────────────────────────────────────────────────────────────────


class TestInsufficient:
    """Neither partner has submitted → INSUFFICIENT."""

    def test_both_none(self):
        """Both None → INSUFFICIENT."""
        result = generate_weekly_relationship_summary(None, None)
        assert result["status"] == "INSUFFICIENT"
        assert result["confidence"] == 0.0

    def test_both_empty(self):
        """Both empty lists → INSUFFICIENT."""
        result = generate_weekly_relationship_summary([], [])
        assert result["status"] == "INSUFFICIENT"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Missing Specific Answers
# ─────────────────────────────────────────────────────────────────────────────


class TestMissingAnswers:
    """Handles missing safety or connection answers gracefully."""

    def test_only_safety_answers(self):
        """Only safety questions answered — still works."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "safety_1", "answer": "4"}],
            [{"question_id": "safety_1", "answer": "4"}],
        )
        assert result["status"] in ("SYNCED", "GROWING")

    def test_only_connection_answers(self):
        """Only connection questions answered — still works."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "conn_1", "answer": "4"}],
            [{"question_id": "conn_1", "answer": "4"}],
        )
        assert result["status"] in ("SYNCED", "GROWING")

    def test_only_open_text(self):
        """Only open-ended text → INSUFFICIENT (no numeric data)."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "open_1", "answer": "Had a good week"}],
            [{"question_id": "open_1", "answer": "Felt connected"}],
        )
        assert result["status"] == "INSUFFICIENT"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Mixed Yes/No Answers
# ─────────────────────────────────────────────────────────────────────────────


class TestYesNo:
    """Yes/no answers converted and compared correctly."""

    def test_both_yes(self):
        """Both answering yes → aligned high (5, 5)."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "safety_1", "answer": "4"}, {"question_id": "conn_2", "answer": "yes"}],
            [{"question_id": "safety_1", "answer": "4"}, {"question_id": "conn_2", "answer": "yes"}],
        )
        assert result["status"] in ("SYNCED", "GROWING")

    def test_one_yes_one_no(self):
        """One yes, one no → misaligned (5 vs 1)."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "conn_2", "answer": "yes"}, {"question_id": "safety_1", "answer": "5"}],
            [{"question_id": "conn_2", "answer": "no"}, {"question_id": "safety_1", "answer": "2"}],
        )
        assert result["status"] == "MISALIGNED"

    def test_both_no(self):
        """Both answering no → aligned low (1, 1)."""
        result = generate_weekly_relationship_summary(
            [{"question_id": "conn_2", "answer": "no"}, {"question_id": "safety_1", "answer": "2"}],
            [{"question_id": "conn_2", "answer": "no"}, {"question_id": "safety_1", "answer": "2"}],
        )
        assert result["status"] == "SYNCED"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Output Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputStructure:
    """All outputs have the correct shape."""

    def test_required_fields(self):
        """Every result has all required fields."""
        cases = [
            (None, None),
            (_answers("4", "4"), None),
            (_answers("4", "4"), _answers("4", "4")),
            (_answers("5", "5"), _answers("1", "1")),
        ]
        for user, partner in cases:
            result = generate_weekly_relationship_summary(user, partner)
            assert "status" in result
            assert "confidence" in result
            assert "title" in result
            assert "summary" in result
            assert "highlight" in result
            assert "conversation_prompt" in result

    def test_confidence_range(self):
        """Confidence is always 0–1."""
        cases = [
            (None, None),
            (_answers("5", "5"), _answers("5", "5")),
            (_answers("1", "1"), _answers("5", "5")),
        ]
        for user, partner in cases:
            result = generate_weekly_relationship_summary(user, partner)
            assert 0.0 <= result["confidence"] <= 1.0

    def test_valid_statuses(self):
        """Status is one of the defined values."""
        valid = {"SYNCED", "GROWING", "MISALIGNED", "CHECK_IN", "INSUFFICIENT"}
        cases = [
            (None, None),
            (_answers("4", "4"), None),
            (_answers("4", "4"), _answers("4", "4")),
            (_answers("5", "5"), _answers("1", "1")),
        ]
        for user, partner in cases:
            result = generate_weekly_relationship_summary(user, partner)
            assert result["status"] in valid
