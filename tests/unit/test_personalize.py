# -*- coding: utf-8 -*-
"""Unit tests for improvement plan personalization (F8A)."""

from __future__ import annotations

import pytest

from kiro.compatibility.personalize import (
    personalize_challenge_plans,
    build_current_situation,
    build_why_section,
    personalize_action_steps,
    build_expected_outcome,
    TYPE_DESCRIPTIONS,
    EXPECTED_OUTCOMES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test data
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_PLAN = {
    "dimension": "attachment_style",
    "dimension_name": "Attachment Style",
    "severity": "high",
    "score": 35,
    "user_a_type": "anxious",
    "user_b_type": "avoidant",
    "challenge_description": "One partner seeks closeness while the other needs space.",
    "action_plan": [
        "Name the cycle together",
        "The pursuing partner practices self-soothing",
        "The withdrawing partner communicates return time",
        "Schedule one daily check-in",
    ],
    "weekly_exercise": "The Pause Protocol — pause for 5 minutes when triggered.",
}

USER_TYPES = {
    "attachment_style": "anxious",
    "communication_style": "direct",
    "conflict_style": "collaborative",
}

PARTNER_TYPES = {
    "attachment_style": "avoidant",
    "communication_style": "expressive",
    "conflict_style": "avoiding",
}


# ─────────────────────────────────────────────────────────────────────────────
# personalize_challenge_plans
# ─────────────────────────────────────────────────────────────────────────────

class TestPersonalizeChallengePlans:

    def test_returns_same_number_of_plans(self):
        """Output has same count as input."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        assert len(result) == 1

    def test_preserves_original_fields(self):
        """Original fields are preserved in output."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        plan = result[0]
        assert plan["dimension"] == "attachment_style"
        assert plan["severity"] == "high"
        assert plan["score"] == 35

    def test_adds_current_situation(self):
        """Adds current_situation field."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        assert "current_situation" in result[0]
        assert "Sarah" in result[0]["current_situation"]
        assert "Raj" in result[0]["current_situation"]

    def test_adds_why_this_happens(self):
        """Adds why_this_happens field."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        assert "why_this_happens" in result[0]
        assert "Sarah" in result[0]["why_this_happens"]

    def test_adds_expected_outcome(self):
        """Adds expected_outcome field."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        assert "expected_outcome" in result[0]
        assert len(result[0]["expected_outcome"]) > 20

    def test_personalizes_action_steps(self):
        """Action steps have generic references replaced with names."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", USER_TYPES, PARTNER_TYPES
        )
        steps = result[0]["action_plan"]
        # "The pursuing partner" → "Sarah"
        assert any("Sarah" in s for s in steps)
        # "The withdrawing partner" → "Raj"
        assert any("Raj" in s for s in steps)

    def test_multiple_plans(self):
        """Handles multiple plans correctly."""
        plan2 = {**SAMPLE_PLAN, "dimension": "communication_style", "severity": "medium"}
        result = personalize_challenge_plans(
            [SAMPLE_PLAN, plan2], "Alice", "Bob", USER_TYPES, PARTNER_TYPES
        )
        assert len(result) == 2
        assert "Alice" in result[0]["current_situation"]
        assert "Alice" in result[1]["current_situation"]

    def test_empty_plans_list(self):
        """Handles empty input gracefully."""
        result = personalize_challenge_plans([], "Sarah", "Raj", {}, {})
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# build_current_situation
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCurrentSituation:

    def test_different_types(self):
        """Generates situation for different types."""
        result = build_current_situation(
            "attachment_style", "Sarah", "anxious", "Raj", "avoidant"
        )
        assert "Sarah" in result
        assert "Raj" in result
        assert "reassurance" in result or "closeness" in result
        assert "independence" in result or "space" in result

    def test_same_types(self):
        """Generates situation when both share the same type."""
        result = build_current_situation(
            "attachment_style", "Sarah", "secure", "Raj", "secure"
        )
        assert "Both Sarah and Raj" in result
        assert "similar style" in result

    def test_unknown_type_uses_fallback(self):
        """Unknown types still produce readable output."""
        result = build_current_situation(
            "attachment_style", "Sarah", "unknown_type", "Raj", "avoidant"
        )
        assert "Sarah" in result
        assert "Raj" in result
        # Should not crash
        assert len(result) > 20

    def test_unknown_dimension_uses_fallback(self):
        """Unknown dimension still produces output."""
        result = build_current_situation(
            "nonexistent_dimension", "A", "typeX", "B", "typeY"
        )
        assert "A" in result
        assert "B" in result

    def test_all_dimensions_produce_output(self):
        """Every known dimension generates non-empty situation."""
        for dim in TYPE_DESCRIPTIONS:
            types = list(TYPE_DESCRIPTIONS[dim].keys())
            if len(types) >= 2:
                result = build_current_situation(dim, "User", types[0], "Partner", types[1])
                assert len(result) > 20, f"Empty situation for {dim}"


# ─────────────────────────────────────────────────────────────────────────────
# build_why_section
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildWhySection:

    def test_attachment_style(self):
        """Attachment style produces valid why section."""
        result = build_why_section(
            "attachment_style", "Sarah", "anxious", "Raj", "avoidant"
        )
        assert "Sarah" in result
        assert "Raj" in result
        assert "wrong" in result.lower()  # "Neither is wrong"

    def test_communication_style(self):
        """Communication style produces valid why section."""
        result = build_why_section(
            "communication_style", "Alice", "analytical", "Bob", "expressive"
        )
        assert "Alice" in result
        assert "Bob" in result

    def test_unknown_dimension_fallback(self):
        """Unknown dimension uses generic template."""
        result = build_why_section(
            "made_up_dimension", "X", "typeA", "Y", "typeB"
        )
        assert "X" in result
        assert "Y" in result
        assert "wrong" in result.lower()

    def test_contains_validation(self):
        """Why section always validates both sides."""
        for dim in ["attachment_style", "communication_style", "conflict_style",
                    "love_language", "financial_personality", "lifestyle_type",
                    "relationship_archetype"]:
            types = list(TYPE_DESCRIPTIONS[dim].keys())
            result = build_why_section(dim, "A", types[0], "B", types[1] if len(types) > 1 else types[0])
            # Should contain some form of validation
            lower = result.lower()
            has_validation = any(phrase in lower for phrase in [
                "wrong", "better", "valid", "healthy",
                "both of you are", "neither", "isn't about",
            ])
            assert has_validation, (
                f"No validation phrase found in why section for {dim}: {result[:100]}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# personalize_action_steps
# ─────────────────────────────────────────────────────────────────────────────

class TestPersonalizeActionSteps:

    def test_replaces_pursuing_partner(self):
        """'The pursuing partner' becomes user_name."""
        steps = ["The pursuing partner practices self-soothing"]
        result = personalize_action_steps(steps, "Sarah", "Raj")
        assert "Sarah" in result[0]
        assert "pursuing partner" not in result[0]

    def test_replaces_withdrawing_partner(self):
        """'The withdrawing partner' becomes partner_name."""
        steps = ["The withdrawing partner communicates return time"]
        result = personalize_action_steps(steps, "Sarah", "Raj")
        assert "Raj" in result[0]
        assert "withdrawing partner" not in result[0]

    def test_replaces_one_partner(self):
        """'One partner' becomes user_name."""
        steps = ["One partner shares their perspective first"]
        result = personalize_action_steps(steps, "Alice", "Bob")
        assert "Alice" in result[0]

    def test_replaces_the_other_partner(self):
        """'the other partner' becomes partner_name."""
        steps = ["and the other partner listens"]
        result = personalize_action_steps(steps, "Alice", "Bob")
        assert "Bob" in result[0]

    def test_replaces_partner_a_and_b(self):
        """'Partner A' and 'Partner B' are replaced."""
        steps = ["Partner A does X", "Partner B does Y"]
        result = personalize_action_steps(steps, "Sarah", "Raj")
        assert "Sarah" in result[0]
        assert "Raj" in result[1]

    def test_no_replacement_when_no_generic(self):
        """Steps without generic references remain unchanged."""
        steps = ["Schedule one daily 10-minute check-in"]
        result = personalize_action_steps(steps, "Sarah", "Raj")
        assert result[0] == "Schedule one daily 10-minute check-in"

    def test_empty_steps(self):
        """Empty list returns empty list."""
        assert personalize_action_steps([], "A", "B") == []

    def test_multiple_replacements_in_one_step(self):
        """Multiple generic references in same step are all replaced."""
        steps = ["One partner speaks while the other partner listens"]
        result = personalize_action_steps(steps, "Alice", "Bob")
        assert "Alice" in result[0]
        assert "Bob" in result[0]
        assert "One partner" not in result[0]
        assert "the other partner" not in result[0]


# ─────────────────────────────────────────────────────────────────────────────
# build_expected_outcome
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildExpectedOutcome:

    def test_low_severity_mentions_1_week(self):
        """Low severity outcomes mention 1 week."""
        result = build_expected_outcome("attachment_style", "low")
        assert "1 week" in result

    def test_medium_severity_mentions_2_weeks(self):
        """Medium severity outcomes mention 2 weeks."""
        result = build_expected_outcome("attachment_style", "medium")
        assert "2 week" in result

    def test_high_severity_mentions_3_4_weeks(self):
        """High severity outcomes mention 3-4 weeks."""
        result = build_expected_outcome("attachment_style", "high")
        assert "3" in result or "4" in result

    def test_all_dimensions_have_outcomes(self):
        """Every dimension has outcomes for all severities."""
        for dim in EXPECTED_OUTCOMES:
            for sev in ["low", "medium", "high"]:
                result = build_expected_outcome(dim, sev)
                assert len(result) > 20, f"Empty outcome for {dim}/{sev}"

    def test_unknown_dimension_uses_generic(self):
        """Unknown dimension falls back to generic outcome."""
        result = build_expected_outcome("nonexistent_dim", "medium")
        assert "2 week" in result
        assert len(result) > 20

    def test_unknown_severity_uses_medium(self):
        """Unknown severity falls back to medium."""
        result = build_expected_outcome("attachment_style", "extreme")
        # Falls through to medium since "extreme" not in dict
        assert len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases and integration
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_email_prefix_as_name(self):
        """Works correctly with email-prefix-style names."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "biswajeet2306", "mannkimicrostories", USER_TYPES, PARTNER_TYPES
        )
        assert "biswajeet2306" in result[0]["current_situation"]
        assert "mannkimicrostories" in result[0]["why_this_happens"]

    def test_very_long_names(self):
        """Handles long names without crashing."""
        long_name = "A" * 100
        result = build_current_situation("attachment_style", long_name, "anxious", "B", "avoidant")
        assert long_name in result

    def test_names_with_special_characters(self):
        """Names with special chars don't break regex."""
        result = personalize_action_steps(
            ["The pursuing partner does X"], "O'Brien", "José"
        )
        assert "O'Brien" in result[0]

    def test_empty_action_plan_in_plan(self):
        """Plan with empty action_plan doesn't crash."""
        plan = {**SAMPLE_PLAN, "action_plan": []}
        result = personalize_challenge_plans([plan], "A", "B", USER_TYPES, PARTNER_TYPES)
        assert result[0]["action_plan"] == []

    def test_missing_dimension_in_user_types(self):
        """Falls back to plan's user_a_type when dimension not in user_types dict."""
        result = personalize_challenge_plans(
            [SAMPLE_PLAN], "Sarah", "Raj", {}, {}  # empty type dicts
        )
        # Should use plan's user_a_type/user_b_type as fallback
        assert "Sarah" in result[0]["current_situation"]
