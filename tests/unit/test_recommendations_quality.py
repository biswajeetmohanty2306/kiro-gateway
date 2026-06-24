# -*- coding: utf-8 -*-
"""Tests for recommendation content quality (F8B).

Verifies:
- All recommendations load without errors
- All entries have required fields
- No clinical/therapy jargon
- Action steps are concrete (no vague wording)
- Weekly exercises have measurable elements
- Compatible with F8A personalization layer
"""

from __future__ import annotations

import pytest

from kiro.compatibility.recommendations import (
    RECOMMENDATIONS,
    GENERIC_RECOMMENDATIONS,
    get_recommendation,
)
from kiro.compatibility.personalize import (
    personalize_challenge_plans,
    personalize_action_steps,
)


# ─────────────────────────────────────────────────────────────────────────────
# Structure validation
# ─────────────────────────────────────────────────────────────────────────────

class TestRecommendationStructure:

    def test_all_entries_have_challenge_description(self):
        """Every recommendation has a non-empty challenge_description."""
        for key, rec in RECOMMENDATIONS.items():
            assert "challenge_description" in rec, f"Missing challenge_description in {key}"
            assert len(rec["challenge_description"]) > 20, f"Too short challenge_description in {key}"

    def test_all_entries_have_action_plan(self):
        """Every recommendation has a non-empty action_plan list."""
        for key, rec in RECOMMENDATIONS.items():
            assert "action_plan" in rec, f"Missing action_plan in {key}"
            assert isinstance(rec["action_plan"], list), f"action_plan not a list in {key}"
            assert len(rec["action_plan"]) >= 3, f"Too few action steps in {key}"

    def test_all_entries_have_weekly_exercise(self):
        """Every recommendation has a non-empty weekly_exercise."""
        for key, rec in RECOMMENDATIONS.items():
            assert "weekly_exercise" in rec, f"Missing weekly_exercise in {key}"
            assert len(rec["weekly_exercise"]) > 20, f"Too short weekly_exercise in {key}"

    def test_generics_have_all_severities(self):
        """Generic fallbacks exist for all severity levels."""
        assert "low" in GENERIC_RECOMMENDATIONS
        assert "medium" in GENERIC_RECOMMENDATIONS
        assert "high" in GENERIC_RECOMMENDATIONS

    def test_generics_have_required_fields(self):
        """Generic fallbacks have all required fields."""
        for severity, rec in GENERIC_RECOMMENDATIONS.items():
            assert "challenge_description" in rec
            assert "action_plan" in rec
            assert "weekly_exercise" in rec
            assert len(rec["action_plan"]) >= 3

    def test_total_recommendations_count(self):
        """We have at least 17 specific recommendations."""
        assert len(RECOMMENDATIONS) >= 17


# ─────────────────────────────────────────────────────────────────────────────
# Content quality
# ─────────────────────────────────────────────────────────────────────────────

# Words that indicate clinical/therapy jargon
BANNED_WORDS = [
    "attachment wound",
    "emotional dysregulation",
    "trauma response",
    "activation pattern",
    "dysregulated",
    "hyperactivation",
    "deactivation strategy",
    "object constancy",
    "differentiation",
    "enmeshment",
    "codependency",
    "narcissistic",
]

# Words that indicate vague/generic action steps
VAGUE_PHRASES = [
    "discuss your expectations",
    "work on this together",
    "be more mindful",
    "try to understand",
    "make an effort to",
    "consider how",
    "think about why",
    "reflect on your",
]


class TestContentQuality:

    def test_no_clinical_jargon(self):
        """Recommendations don't use clinical/therapy language."""
        for key, rec in RECOMMENDATIONS.items():
            full_text = (
                rec["challenge_description"]
                + " ".join(rec["action_plan"])
                + rec["weekly_exercise"]
            ).lower()
            for banned in BANNED_WORDS:
                assert banned not in full_text, (
                    f"Clinical jargon '{banned}' found in {key}"
                )

    def test_no_vague_action_steps(self):
        """Action steps don't use vague phrasing."""
        for key, rec in RECOMMENDATIONS.items():
            for step in rec["action_plan"]:
                lower = step.lower()
                for vague in VAGUE_PHRASES:
                    assert vague not in lower, (
                        f"Vague phrase '{vague}' found in action step of {key}: '{step[:50]}...'"
                    )

    def test_exercises_mention_time(self):
        """Weekly exercises mention duration or time commitment."""
        time_words = ["minute", "min", "hour", "daily", "evening", "morning",
                      "sunday", "week", "once", "time:"]
        for key, rec in RECOMMENDATIONS.items():
            exercise_lower = rec["weekly_exercise"].lower()
            has_time = any(word in exercise_lower for word in time_words)
            assert has_time, (
                f"Weekly exercise in {key} doesn't mention time/duration"
            )

    def test_exercises_are_measurable(self):
        """Weekly exercises include measurement/tracking language."""
        measure_words = ["track", "count", "rate", "notice", "did you",
                         "how many", "aim for", "target"]
        for key, rec in RECOMMENDATIONS.items():
            exercise_lower = rec["weekly_exercise"].lower()
            has_measure = any(word in exercise_lower for word in measure_words)
            assert has_measure, (
                f"Weekly exercise in {key} has no measurement/tracking element"
            )

    def test_action_steps_are_specific(self):
        """Each action step is at least 30 chars (not too terse)."""
        for key, rec in RECOMMENDATIONS.items():
            for i, step in enumerate(rec["action_plan"]):
                assert len(step) >= 30, (
                    f"Action step {i} in {key} is too short ({len(step)} chars): '{step}'"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Lookup behavior (no regressions)
# ─────────────────────────────────────────────────────────────────────────────

class TestLookupBehavior:

    def test_specific_lookup_works(self):
        """Known type pairing returns specific recommendation."""
        rec = get_recommendation("attachment_style", "anxious", "avoidant", "high")
        assert "pattern" in rec
        assert rec["pattern"] == "The Pursuit-Distance Cycle"

    def test_reversed_order_works(self):
        """Type order doesn't matter (frozenset)."""
        rec = get_recommendation("attachment_style", "avoidant", "anxious", "high")
        assert rec["pattern"] == "The Pursuit-Distance Cycle"

    def test_unknown_pairing_falls_back_to_generic(self):
        """Unknown type pairing returns generic for the severity."""
        rec = get_recommendation("attachment_style", "secure", "secure", "low")
        # Should be the generic 'low' fallback (no specific entry for secure+secure)
        assert "pattern" not in rec  # generics don't have pattern field
        assert "challenge_description" in rec

    def test_unknown_dimension_falls_back(self):
        """Unknown dimension returns generic."""
        rec = get_recommendation("nonexistent_dim", "a", "b", "medium")
        assert "challenge_description" in rec
        assert "action_plan" in rec

    def test_all_severity_levels_return_something(self):
        """Every severity level returns a valid recommendation."""
        for severity in ["low", "medium", "high"]:
            rec = get_recommendation("attachment_style", "unknown", "unknown", severity)
            assert "challenge_description" in rec
            assert len(rec["action_plan"]) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# F8A compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestF8ACompatibility:

    def test_action_plans_personalizable(self):
        """All action plans work with personalize_action_steps."""
        for key, rec in RECOMMENDATIONS.items():
            result = personalize_action_steps(rec["action_plan"], "Alice", "Bob")
            assert len(result) == len(rec["action_plan"])
            # Should not crash
            for step in result:
                assert isinstance(step, str)
                assert len(step) > 0

    def test_full_personalization_pipeline(self):
        """A full challenge plan flows through personalization without errors."""
        sample_plan = {
            "dimension": "attachment_style",
            "dimension_name": "Attachment Style",
            "severity": "high",
            "score": 35,
            "user_a_type": "anxious",
            "user_b_type": "avoidant",
            "challenge_description": get_recommendation("attachment_style", "anxious", "avoidant", "high")["challenge_description"],
            "action_plan": get_recommendation("attachment_style", "anxious", "avoidant", "high")["action_plan"],
            "weekly_exercise": get_recommendation("attachment_style", "anxious", "avoidant", "high")["weekly_exercise"],
        }

        user_types = {"attachment_style": "anxious"}
        partner_types = {"attachment_style": "avoidant"}

        result = personalize_challenge_plans(
            [sample_plan], "Sarah", "Raj", user_types, partner_types
        )

        assert len(result) == 1
        plan = result[0]
        assert "Sarah" in plan["current_situation"]
        assert "Raj" in plan["current_situation"]
        assert "expected_outcome" in plan
        assert len(plan["expected_outcome"]) > 20

    def test_generic_plans_also_personalizable(self):
        """Generic fallback plans also work with personalization."""
        generic = get_recommendation("unknown_dim", "typeA", "typeB", "medium")
        sample_plan = {
            "dimension": "unknown_dim",
            "severity": "medium",
            "user_a_type": "typeA",
            "user_b_type": "typeB",
            "challenge_description": generic["challenge_description"],
            "action_plan": generic["action_plan"],
            "weekly_exercise": generic["weekly_exercise"],
        }

        result = personalize_challenge_plans(
            [sample_plan], "Alice", "Bob", {}, {}
        )

        assert len(result) == 1
        assert "Alice" in result[0]["current_situation"]
