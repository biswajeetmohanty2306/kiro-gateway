# -*- coding: utf-8 -*-
"""Unit tests for the AI Relationship Coach Context Builder (J7-C)."""

from __future__ import annotations

from kiro.coach.context_builder import build_relationship_context
from kiro.coach.types import RelationshipContext


# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaults:
    """All missing inputs produce sensible defaults."""

    def test_no_arguments(self):
        """Empty call returns valid context with defaults."""
        ctx = build_relationship_context()
        assert isinstance(ctx, RelationshipContext)
        assert ctx.user_name == "User"
        assert ctx.partner_name == "Partner"
        assert ctx.overall_score == 0.0
        assert ctx.top_strengths == []
        assert ctx.top_challenges == []
        assert ctx.dimension_summaries == {}
        assert ctx.journey_phase == "EARLY"
        assert ctx.current_week == 0
        assert ctx.total_reflections == 0
        assert ctx.recent_insight is None
        assert ctx.weekly_sync_status is None
        assert ctx.active_challenges == []
        assert ctx.completed_plans == 0

    def test_none_names_default(self):
        """None names produce 'User' and 'Partner'."""
        ctx = build_relationship_context(user_name=None, partner_name=None)
        assert ctx.user_name == "User"
        assert ctx.partner_name == "Partner"

    def test_empty_string_names(self):
        """Empty string names produce 'User' and 'Partner'."""
        ctx = build_relationship_context(user_name="", partner_name="  ")
        assert ctx.user_name == "User"
        assert ctx.partner_name == "Partner"

    def test_none_score(self):
        """None score defaults to 0.0."""
        ctx = build_relationship_context(overall_score=None)
        assert ctx.overall_score == 0.0

    def test_none_journey_values(self):
        """None journey values default to EARLY/0/0."""
        ctx = build_relationship_context(
            journey_phase=None, current_week=None, total_reflections=None
        )
        assert ctx.journey_phase == "EARLY"
        assert ctx.current_week == 0
        assert ctx.total_reflections == 0


# ─────────────────────────────────────────────────────────────────────────────
# Identity
# ─────────────────────────────────────────────────────────────────────────────


class TestIdentity:
    """Name normalization."""

    def test_normal_names(self):
        """Normal names pass through."""
        ctx = build_relationship_context(user_name="Alice", partner_name="Bob")
        assert ctx.user_name == "Alice"
        assert ctx.partner_name == "Bob"

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed."""
        ctx = build_relationship_context(user_name="  Alice  ", partner_name=" Bob ")
        assert ctx.user_name == "Alice"
        assert ctx.partner_name == "Bob"


# ─────────────────────────────────────────────────────────────────────────────
# Compatibility
# ─────────────────────────────────────────────────────────────────────────────


SAMPLE_DIMENSIONS = {
    "attachment_style": {"score": 85, "label": "Good", "recommendation": "Strong emotional bond."},
    "communication_style": {"score": 72, "label": "Good", "recommendation": "Mostly aligned."},
    "conflict_style": {"score": 60, "label": "Moderate", "recommendation": "Room to grow."},
    "love_language": {"score": 55, "label": "Moderate", "recommendation": "Different expressions."},
    "financial_personality": {"score": 45, "label": "Challenging", "recommendation": "Needs attention."},
    "lifestyle_type": {"score": 40, "label": "Challenging", "recommendation": "Different rhythms."},
    "relationship_archetype": {"score": 35, "label": "Difficult", "recommendation": "Significant gap."},
}


class TestCompatibility:
    """Score, strengths, challenges, and summary extraction."""

    def test_score_normalization(self):
        """Score is clamped to 0–100."""
        ctx = build_relationship_context(overall_score=72.5)
        assert ctx.overall_score == 72.5

    def test_score_clamped_high(self):
        """Score above 100 is clamped."""
        ctx = build_relationship_context(overall_score=150.0)
        assert ctx.overall_score == 100.0

    def test_score_clamped_low(self):
        """Negative score is clamped to 0."""
        ctx = build_relationship_context(overall_score=-10.0)
        assert ctx.overall_score == 0.0

    def test_strengths_from_dimensions(self):
        """Top 3 highest-scoring dimensions become strengths."""
        ctx = build_relationship_context(dimension_scores=SAMPLE_DIMENSIONS)
        assert len(ctx.top_strengths) == 3
        assert "Attachment Style" in ctx.top_strengths
        assert "Communication Style" in ctx.top_strengths
        assert "Conflict Style" in ctx.top_strengths

    def test_challenges_from_dimensions(self):
        """Bottom 3 lowest-scoring dimensions become challenges."""
        ctx = build_relationship_context(dimension_scores=SAMPLE_DIMENSIONS)
        assert len(ctx.top_challenges) == 3
        assert "Relationship Archetype" in ctx.top_challenges
        assert "Lifestyle Type" in ctx.top_challenges
        assert "Financial Personality" in ctx.top_challenges

    def test_dimension_summaries(self):
        """Each dimension gets a summary from its recommendation."""
        ctx = build_relationship_context(dimension_scores=SAMPLE_DIMENSIONS)
        assert "Attachment Style" in ctx.dimension_summaries
        assert ctx.dimension_summaries["Attachment Style"] == "Strong emotional bond."

    def test_no_dimensions(self):
        """Empty dimensions produce empty collections."""
        ctx = build_relationship_context(dimension_scores=None)
        assert ctx.top_strengths == []
        assert ctx.top_challenges == []
        assert ctx.dimension_summaries == {}

    def test_empty_dimensions_dict(self):
        """Empty dict produces empty collections."""
        ctx = build_relationship_context(dimension_scores={})
        assert ctx.top_strengths == []
        assert ctx.top_challenges == []

    def test_missing_recommendation_fallback(self):
        """Dimensions without recommendation show score."""
        dims = {"test_dim": {"score": 65}}
        ctx = build_relationship_context(dimension_scores=dims)
        assert "Test Dim" in ctx.dimension_summaries
        assert "65" in ctx.dimension_summaries["Test Dim"]


# ─────────────────────────────────────────────────────────────────────────────
# Journey
# ─────────────────────────────────────────────────────────────────────────────


class TestJourney:
    """Journey phase and progress normalization."""

    def test_valid_phases(self):
        """All valid phases pass through."""
        for phase in ("EARLY", "BUILDING", "GROWING", "ESTABLISHED"):
            ctx = build_relationship_context(journey_phase=phase)
            assert ctx.journey_phase == phase

    def test_invalid_phase_defaults(self):
        """Invalid phase falls back to EARLY."""
        ctx = build_relationship_context(journey_phase="INVALID")
        assert ctx.journey_phase == "EARLY"

    def test_phase_case_insensitive(self):
        """Phase is normalized to uppercase."""
        ctx = build_relationship_context(journey_phase="growing")
        assert ctx.journey_phase == "GROWING"

    def test_negative_week_clamped(self):
        """Negative week is clamped to 0."""
        ctx = build_relationship_context(current_week=-5)
        assert ctx.current_week == 0

    def test_negative_reflections_clamped(self):
        """Negative reflections count is clamped to 0."""
        ctx = build_relationship_context(total_reflections=-1)
        assert ctx.total_reflections == 0

    def test_positive_values_pass_through(self):
        """Positive values are preserved."""
        ctx = build_relationship_context(current_week=8, total_reflections=5)
        assert ctx.current_week == 8
        assert ctx.total_reflections == 5

    def test_insight_preserved(self):
        """Non-empty insight is preserved."""
        ctx = build_relationship_context(recent_insight="Safety improving.")
        assert ctx.recent_insight == "Safety improving."

    def test_empty_insight_becomes_none(self):
        """Empty string insight becomes None."""
        ctx = build_relationship_context(recent_insight="")
        assert ctx.recent_insight is None

    def test_sync_status_preserved(self):
        """Non-empty sync status is preserved."""
        ctx = build_relationship_context(weekly_sync_status="GROWING")
        assert ctx.weekly_sync_status == "GROWING"


# ─────────────────────────────────────────────────────────────────────────────
# Improvement Plans
# ─────────────────────────────────────────────────────────────────────────────


class TestPlans:
    """Improvement plan extraction."""

    def test_no_plans(self):
        """None plans produce empty list and 0 completed."""
        ctx = build_relationship_context(improvement_plans=None)
        assert ctx.active_challenges == []
        assert ctx.completed_plans == 0

    def test_empty_plans(self):
        """Empty list produces empty challenges."""
        ctx = build_relationship_context(improvement_plans=[])
        assert ctx.active_challenges == []
        assert ctx.completed_plans == 0

    def test_active_plans_extracted(self):
        """Active (non-completed) plans become challenges."""
        plans = [
            {"dimension": "attachment_style", "severity": "high", "challenge_description": "The pursuit-distance cycle", "completed": False},
            {"dimension": "conflict_style", "severity": "medium", "challenge_description": "Rising tension", "completed": False},
        ]
        ctx = build_relationship_context(improvement_plans=plans)
        assert len(ctx.active_challenges) == 2
        assert "The pursuit-distance cycle" in ctx.active_challenges
        assert "Rising tension" in ctx.active_challenges

    def test_completed_plans_counted(self):
        """Completed plans increment the counter."""
        plans = [
            {"dimension": "a", "challenge_description": "Done", "completed": True},
            {"dimension": "b", "challenge_description": "Also done", "completed": True},
            {"dimension": "c", "challenge_description": "Active", "completed": False},
        ]
        ctx = build_relationship_context(improvement_plans=plans)
        assert ctx.completed_plans == 2
        assert len(ctx.active_challenges) == 1

    def test_plan_without_description_uses_dimension(self):
        """Plans without description fallback to dimension name."""
        plans = [{"dimension": "love_language", "completed": False}]
        ctx = build_relationship_context(improvement_plans=plans)
        assert ctx.active_challenges == ["Love Language challenge"]

    def test_max_active_plans_capped(self):
        """Active challenges are capped at 5."""
        plans = [
            {"dimension": f"dim_{i}", "challenge_description": f"Challenge {i}", "completed": False}
            for i in range(10)
        ]
        ctx = build_relationship_context(improvement_plans=plans)
        assert len(ctx.active_challenges) == 5

    def test_invalid_plan_skipped(self):
        """Non-dict entries in plans list are skipped."""
        plans = [None, "bad", 42, {"dimension": "x", "challenge_description": "Valid", "completed": False}]
        ctx = build_relationship_context(improvement_plans=plans)
        assert len(ctx.active_challenges) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Immutability & Determinism
# ─────────────────────────────────────────────────────────────────────────────


class TestImmutability:
    """Output is immutable. Inputs are never mutated."""

    def test_output_is_frozen(self):
        """RelationshipContext is frozen (immutable)."""
        ctx = build_relationship_context(user_name="Alice")
        try:
            ctx.user_name = "Bob"  # type: ignore
            assert False, "Should have raised"
        except (AttributeError, TypeError):
            pass

    def test_input_dict_not_mutated(self):
        """Original dimension_scores dict is not mutated."""
        dims = {"attachment_style": {"score": 80, "recommendation": "Good"}}
        original_keys = set(dims.keys())
        build_relationship_context(dimension_scores=dims)
        assert set(dims.keys()) == original_keys

    def test_input_plans_not_mutated(self):
        """Original plans list is not mutated."""
        plans = [{"dimension": "x", "challenge_description": "Y", "completed": False}]
        original_len = len(plans)
        build_relationship_context(improvement_plans=plans)
        assert len(plans) == original_len

    def test_deterministic(self):
        """Same inputs always produce same output."""
        kwargs = dict(
            user_name="Alice",
            partner_name="Bob",
            overall_score=72.5,
            dimension_scores=SAMPLE_DIMENSIONS,
            journey_phase="BUILDING",
            current_week=5,
            total_reflections=4,
            recent_insight="Improving.",
            weekly_sync_status="SYNCED",
            improvement_plans=[{"dimension": "x", "challenge_description": "Test", "completed": False}],
        )
        ctx1 = build_relationship_context(**kwargs)
        ctx2 = build_relationship_context(**kwargs)
        assert ctx1 == ctx2
