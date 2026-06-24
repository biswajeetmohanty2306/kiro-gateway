# -*- coding: utf-8 -*-
"""Unit tests for the empathetic coaching layer (F8E Phase 1)."""

from __future__ import annotations

import pytest

from kiro.compatibility.coach import (
    generate_coaching_plan,
    split_actions,
    format_challenge,
    FEELINGS_BY_TYPE,
    VALIDATION_TEMPLATES,
    CAN_IMPROVE,
    WHATS_HAPPENING,
    EXAMPLE_DIALOGUES,
    MISTAKES,
    FIRST_STEPS,
)


# ─────────────────────────────────────────────────────────────────────────────
# generate_coaching_plan — full pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateCoachingPlan:

    def test_returns_version_3(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Sarah", "Raj",
            "anxious", "avoidant", ["Step 1", "Step 2"], "Exercise text"
        )
        assert result["version"] == 3

    def test_contains_all_sections(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Sarah", "Raj",
            "anxious", "avoidant",
            ["Sarah: do X", "Raj: do Y", "Together: do Z"],
            "The Exercise — Do this for 10 minutes. Track: did you do it?"
        )
        assert "whats_happening" in result
        assert "example_dialogue" in result
        assert "feelings" in result
        assert "why_this_happens" in result
        assert "validation" in result
        assert "difficulty" in result
        assert "user_actions" in result
        assert "partner_actions" in result
        assert "together_actions" in result
        assert "mistakes" in result
        assert "weekly_challenge" in result
        assert "first_step" in result
        assert "can_this_improve" in result
        assert "expected_outcome" in result

    def test_names_in_whats_happening(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Alice", "Bob",
            "anxious", "avoidant", [], ""
        )
        assert "Alice" in result["whats_happening"]
        assert "Bob" in result["whats_happening"]

    def test_names_in_validation(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Alice", "Bob",
            "anxious", "avoidant", [], ""
        )
        assert "Alice" in result["validation"]
        assert "Bob" in result["validation"]

    def test_names_in_first_step(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Alice", "Bob",
            "anxious", "avoidant", [], ""
        )
        assert "Bob" in result["first_step"]["user_action"]
        assert "Alice" in result["first_step"]["partner_action"]

    def test_feelings_populated(self):
        result = generate_coaching_plan(
            "attachment_style", "high", "Sarah", "Raj",
            "anxious", "avoidant", [], ""
        )
        assert len(result["feelings"]["user"]) >= 3
        assert len(result["feelings"]["partner"]) >= 3

    def test_can_improve_always_positive(self):
        result = generate_coaching_plan(
            "conflict_style", "high", "A", "B",
            "avoiding", "competing", [], ""
        )
        lower = result["can_this_improve"].lower()
        assert lower.startswith("yes")

    def test_difficulty_maps_severity(self):
        low = generate_coaching_plan("attachment_style", "low", "A", "B", "anxious", "avoidant", [], "")
        high = generate_coaching_plan("attachment_style", "high", "A", "B", "anxious", "avoidant", [], "")
        assert low["difficulty"]["level"] == "easy"
        assert high["difficulty"]["level"] == "challenging"

    def test_unknown_dimension_doesnt_crash(self):
        result = generate_coaching_plan(
            "unknown_dimension", "medium", "X", "Y",
            "typeA", "typeB", ["Step 1"], "Exercise — 5 min."
        )
        assert result["version"] == 3
        assert len(result["whats_happening"]) > 20
        assert len(result["validation"]) > 20


# ─────────────────────────────────────────────────────────────────────────────
# split_actions
# ─────────────────────────────────────────────────────────────────────────────

class TestSplitActions:

    def test_splits_by_name_prefix(self):
        user, partner, together = split_actions(
            ["Sarah: Do X", "Raj: Do Y", "Together: Do Z"],
            "Sarah", "Raj"
        )
        assert len(user) == 1
        assert len(partner) == 1
        assert len(together) == 1

    def test_together_keywords(self):
        user, partner, together = split_actions(
            ["Alice: do A", "Bob: do B", "Both of you sit down", "Schedule a weekly meeting"],
            "Alice", "Bob"
        )
        # "Both" and "Schedule" are together-markers
        assert "Both of you sit down" in together
        assert "Schedule a weekly meeting" in together

    def test_name_in_body(self):
        user, partner, together = split_actions(
            ["When Alice feels worried, pause", "Give Bob space to think"],
            "Alice", "Bob"
        )
        assert "When Alice" in user[0]
        assert "Give Bob" in partner[0]

    def test_ambiguous_goes_to_together(self):
        user, partner, together = split_actions(
            ["Sit together for 10 minutes"],
            "Alice", "Bob"
        )
        assert len(together) == 1

    def test_empty_input(self):
        user, partner, together = split_actions([], "A", "B")
        assert user == [] and partner == [] and together == []


# ─────────────────────────────────────────────────────────────────────────────
# format_challenge
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatChallenge:

    def test_extracts_name(self):
        result = format_challenge("The Evening Check — Do this every night. Time: 10 minutes.")
        assert result["name"] == "The Evening Check"

    def test_extracts_duration(self):
        result = format_challenge("Exercise — Do it. Time: 15 minutes.")
        assert "15" in result["duration"]

    def test_extracts_tracking(self):
        result = format_challenge("Do the thing. Track: did you complete it 5/7 days?")
        assert "5/7" in result["tracking"]

    def test_handles_no_markers(self):
        result = format_challenge("Just do something nice for each other this week.")
        assert result["name"] is not None
        assert result["duration"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Content quality
# ─────────────────────────────────────────────────────────────────────────────

BANNED_LABELS = ["anxious", "avoidant", "fearful", "secure", "competing",
                 "avoiding", "collaborative", "direct", "diplomatic",
                 "analytical", "expressive"]


class TestContentQuality:

    def test_validation_no_blame(self):
        """Validation templates never use blame language."""
        blame_words = ["fault", "blame", "wrong with you", "your problem", "you caused"]
        for dim, template in VALIDATION_TEMPLATES.items():
            text = template.lower()
            for word in blame_words:
                assert word not in text, f"Blame word '{word}' in {dim} validation"

    def test_can_improve_all_dimensions(self):
        """Every dimension has a 'can improve' entry starting with Yes."""
        for dim in ["attachment_style", "communication_style", "conflict_style",
                    "love_language", "financial_personality", "lifestyle_type",
                    "relationship_archetype"]:
            assert dim in CAN_IMPROVE
            assert CAN_IMPROVE[dim].lower().startswith("yes")

    def test_feelings_non_judgmental(self):
        """Feelings lists don't contain blame words."""
        blame = ["should", "fault", "wrong", "bad", "toxic", "unhealthy"]
        for key, feelings in FEELINGS_BY_TYPE.items():
            for feeling in feelings:
                lower = feeling.lower()
                for word in blame:
                    assert word not in lower, (
                        f"Blame word '{word}' in feelings for {key}: '{feeling}'"
                    )

    def test_whats_happening_no_type_labels(self):
        """What's happening text doesn't use raw type labels."""
        for dim, entries in WHATS_HAPPENING.items():
            for key, template in entries.items():
                lower = template.lower()
                for label in BANNED_LABELS:
                    assert label not in lower, (
                        f"Type label '{label}' found in whats_happening for {dim}/{key}"
                    )

    def test_mistakes_are_actionable(self):
        """Each mistake describes observable behavior."""
        for dim, entries in MISTAKES.items():
            for key, mistakes in entries.items():
                for m in mistakes:
                    # Should be at least moderately specific
                    assert len(m) >= 20, f"Too short mistake in {dim}/{key}: '{m}'"

    def test_dialogue_alternates_speakers(self):
        """Example dialogues alternate between user and partner."""
        for dim, entries in EXAMPLE_DIALOGUES.items():
            for key, entry in entries.items():
                lines = entry["lines"]
                if len(lines) >= 4:
                    # At least some alternation
                    speakers = [l[0] for l in lines]
                    # Not all same speaker
                    assert len(set(speakers)) > 1, f"No alternation in {dim}/{key}"
