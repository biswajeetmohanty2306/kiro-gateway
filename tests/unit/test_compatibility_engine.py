# -*- coding: utf-8 -*-
"""Unit tests for the compatibility engine (F5B).

Tests the pure scoring function against known matrix values,
strength adjustments, weighting, and edge cases.
"""

from __future__ import annotations

import pytest

from kiro.compatibility.engine import (
    CompatibilityResult,
    DimensionCompatibility,
    adjust_for_strength,
    compute_compatibility,
    score_to_label,
    severity_from_score,
    DIMENSION_ORDER,
)
from kiro.compatibility.matrices import lookup_score, DIMENSION_WEIGHTS, TOTAL_WEIGHT


# --- Helpers ---

def make_profile(types: dict[str, tuple[str, int]]) -> dict:
    """Build a minimal profile dimension_scores dict. types = {dim: (type, strength)}."""
    return {
        dim: {"type": t, "strength": s, "score": s, "sub_scores": {}}
        for dim, (t, s) in types.items()
    }


SECURE_PROFILE = make_profile({
    "attachment_style": ("secure", 85),
    "communication_style": ("direct", 80),
    "conflict_style": ("collaborative", 90),
    "love_language": ("touch", 70),
    "financial_personality": ("investor", 75),
    "lifestyle_type": ("adventurous", 80),
    "relationship_archetype": ("partner", 85),
})

ANXIOUS_AVOIDANT_PROFILE = make_profile({
    "attachment_style": ("anxious", 90),
    "communication_style": ("expressive", 85),
    "conflict_style": ("avoiding", 75),
    "love_language": ("words", 60),
    "financial_personality": ("spender", 80),
    "lifestyle_type": ("homebody", 78),
    "relationship_archetype": ("independent", 82),
})


# --- Tests: score_to_label ---

class TestScoreToLabel:
    def test_excellent(self):
        assert score_to_label(92) == "Excellent"
        assert score_to_label(85) == "Excellent"

    def test_good(self):
        assert score_to_label(84) == "Good"
        assert score_to_label(70) == "Good"

    def test_moderate(self):
        assert score_to_label(69) == "Moderate"
        assert score_to_label(55) == "Moderate"

    def test_challenging(self):
        assert score_to_label(54) == "Challenging"
        assert score_to_label(40) == "Challenging"

    def test_difficult(self):
        assert score_to_label(39) == "Difficult"
        assert score_to_label(25) == "Difficult"


# --- Tests: adjust_for_strength ---

class TestAdjustForStrength:
    def test_both_strong_adds_5(self):
        assert adjust_for_strength(70, 80, 90) == 75

    def test_both_strong_caps_at_98(self):
        assert adjust_for_strength(95, 80, 80) == 98

    def test_one_mild_subtracts_5(self):
        assert adjust_for_strength(70, 45, 80) == 65

    def test_one_mild_floors_at_25(self):
        assert adjust_for_strength(27, 30, 80) == 25

    def test_no_adjustment_mid_range(self):
        assert adjust_for_strength(60, 60, 70) == 60

    def test_both_mild_subtracts_5(self):
        assert adjust_for_strength(50, 40, 30) == 45


# --- Tests: lookup_score ---

class TestLookupScore:
    def test_secure_secure(self):
        assert lookup_score("attachment_style", "secure", "secure") == 92

    def test_anxious_avoidant(self):
        assert lookup_score("attachment_style", "anxious", "avoidant") == 35

    def test_symmetric(self):
        assert lookup_score("attachment_style", "avoidant", "anxious") == 35

    def test_direct_analytical(self):
        assert lookup_score("communication_style", "direct", "analytical") == 75
        assert lookup_score("communication_style", "analytical", "direct") == 75

    def test_avoiding_competing(self):
        assert lookup_score("conflict_style", "avoiding", "competing") == 35

    def test_saver_spender(self):
        assert lookup_score("financial_personality", "saver", "spender") == 38

    def test_touch_touch(self):
        assert lookup_score("love_language", "touch", "touch") == 88

    def test_adventurous_homebody(self):
        assert lookup_score("lifestyle_type", "adventurous", "homebody") == 38

    def test_nurturer_partner(self):
        assert lookup_score("relationship_archetype", "nurturer", "partner") == 85

    def test_unknown_pair_returns_default(self):
        assert lookup_score("attachment_style", "unknown", "secure") == 50

    def test_unknown_dimension_returns_default(self):
        assert lookup_score("nonexistent_dimension", "a", "b") == 50


# --- Tests: severity_from_score ---

class TestSeverityFromScore:
    def test_low(self):
        assert severity_from_score(55) == "low"
        assert severity_from_score(80) == "low"

    def test_medium(self):
        assert severity_from_score(40) == "medium"
        assert severity_from_score(54) == "medium"

    def test_high(self):
        assert severity_from_score(39) == "high"
        assert severity_from_score(25) == "high"


# --- Tests: compute_compatibility (full pipeline) ---

class TestComputeCompatibility:
    def test_identical_profiles_high_score(self):
        """Same types everywhere → high scores."""
        result = compute_compatibility(SECURE_PROFILE, SECURE_PROFILE)

        assert result.overall_score >= 75
        assert result.overall_label in ("Excellent", "Good")
        assert len(result.dimensions) == 7
        assert len(result.strengths) == 3
        assert len(result.challenges) == 3

    def test_opposite_profiles_lower_score(self):
        """Mismatched types → lower overall score."""
        result = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)

        assert result.overall_score < 70
        assert len(result.dimensions) == 7
        assert len(result.challenge_plans) == 3

    def test_symmetric_scoring(self):
        """A vs B == B vs A."""
        result_ab = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)
        result_ba = compute_compatibility(ANXIOUS_AVOIDANT_PROFILE, SECURE_PROFILE)

        assert result_ab.overall_score == result_ba.overall_score
        for dim in DIMENSION_ORDER:
            assert result_ab.dimensions[dim].score == result_ba.dimensions[dim].score

    def test_overall_score_clamped(self):
        """Overall score is between 25 and 98."""
        # Worst case: all difficult pairings
        worst_a = make_profile({
            "attachment_style": ("anxious", 90),
            "communication_style": ("analytical", 85),
            "conflict_style": ("avoiding", 80),
            "love_language": ("gifts", 70),
            "financial_personality": ("saver", 85),
            "lifestyle_type": ("adventurous", 80),
            "relationship_archetype": ("partner", 85),
        })
        worst_b = make_profile({
            "attachment_style": ("avoidant", 90),
            "communication_style": ("expressive", 85),
            "conflict_style": ("competing", 80),
            "love_language": ("time", 70),
            "financial_personality": ("spender", 85),
            "lifestyle_type": ("homebody", 80),
            "relationship_archetype": ("independent", 85),
        })
        result = compute_compatibility(worst_a, worst_b)

        assert result.overall_score >= 25
        assert result.overall_score <= 98

    def test_improvement_potential(self):
        """Improvement potential = 100 - avg of 3 lowest."""
        result = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)

        sorted_scores = sorted(d.score for d in result.dimensions.values())
        expected = round(100 - sum(sorted_scores[:3]) / 3, 2)

        assert result.improvement_potential == expected

    def test_strengths_are_top_3(self):
        """Strengths are the 3 highest-scoring dimensions."""
        result = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)

        strength_scores = [s.score for s in result.strengths]
        assert strength_scores == sorted(strength_scores, reverse=True)
        assert all(
            s.score >= c.score
            for s in result.strengths
            for c in result.challenges
        )

    def test_challenges_are_bottom_3(self):
        """Challenges are the 3 lowest-scoring dimensions."""
        result = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)

        challenge_scores = [c.score for c in result.challenges]
        # Challenges are the bottom 3 from sorted_dims (sorted desc), so they come in desc order
        all_scores = sorted([d.score for d in result.dimensions.values()])
        bottom_3 = all_scores[:3]
        assert set(challenge_scores) == set(bottom_3)

    def test_challenge_plans_populated(self):
        """Each challenge has a plan with required fields."""
        result = compute_compatibility(SECURE_PROFILE, ANXIOUS_AVOIDANT_PROFILE)

        assert len(result.challenge_plans) == 3
        for plan in result.challenge_plans:
            assert "dimension" in plan
            assert "severity" in plan
            assert "challenge_description" in plan
            assert len(plan["challenge_description"]) > 0
            assert "action_plan" in plan
            assert isinstance(plan["action_plan"], list)
            assert "weekly_exercise" in plan

    def test_dimension_weights_sum(self):
        """Total weight is 8.0."""
        assert TOTAL_WEIGHT == pytest.approx(8.0)

    def test_all_dimensions_present(self):
        """Result contains all 7 dimensions."""
        result = compute_compatibility(SECURE_PROFILE, SECURE_PROFILE)

        for dim in DIMENSION_ORDER:
            assert dim in result.dimensions
            d = result.dimensions[dim]
            assert d.dimension == dim
            assert d.dimension_name != ""
            assert 25 <= d.score <= 98
            assert d.label in ("Excellent", "Good", "Moderate", "Challenging", "Difficult")

    def test_specific_pairing_score(self):
        """Known pairing: anxious + avoidant attachment → base 35."""
        a = make_profile({"attachment_style": ("anxious", 90), **{d: ("secure", 75) for d in DIMENSION_ORDER if d != "attachment_style"}})
        b = make_profile({"attachment_style": ("avoidant", 85), **{d: ("secure", 75) for d in DIMENSION_ORDER if d != "attachment_style"}})

        result = compute_compatibility(a, b)
        # Both strong → +5 adjustment: 35 + 5 = 40
        assert result.dimensions["attachment_style"].score == 40
        assert result.dimensions["attachment_style"].base_score == 35
