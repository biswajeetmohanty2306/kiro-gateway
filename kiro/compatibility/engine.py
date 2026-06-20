# -*- coding: utf-8 -*-
"""Compatibility scoring engine (F5B).

Pure function: two profile dimension_scores → full compatibility report.
No database, no I/O, no side effects. Same inputs → same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .matrices import DIMENSION_WEIGHTS, TOTAL_WEIGHT, lookup_score
from .recommendations import get_recommendation

DIMENSION_ORDER = [
    "attachment_style",
    "communication_style",
    "conflict_style",
    "love_language",
    "financial_personality",
    "lifestyle_type",
    "relationship_archetype",
]

DIMENSION_NAMES = {
    "attachment_style": "Attachment Style",
    "communication_style": "Communication Style",
    "conflict_style": "Conflict Style",
    "love_language": "Love Language",
    "financial_personality": "Financial Personality",
    "lifestyle_type": "Lifestyle Type",
    "relationship_archetype": "Relationship Archetype",
}


@dataclass
class DimensionCompatibility:
    """Compatibility result for one dimension."""
    dimension: str
    dimension_name: str
    score: int
    base_score: int
    label: str
    user_a_type: str
    user_b_type: str
    recommendation: str


@dataclass
class CompatibilityResult:
    """Complete compatibility report output."""
    overall_score: float
    overall_label: str
    improvement_potential: float
    dimensions: Dict[str, DimensionCompatibility]
    strengths: List[DimensionCompatibility]
    challenges: List[DimensionCompatibility]
    challenge_plans: List[dict]


def score_to_label(score: int) -> str:
    """Map a 0–100 score to a human-readable label."""
    if score >= 85:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 55:
        return "Moderate"
    elif score >= 40:
        return "Challenging"
    else:
        return "Difficult"


def adjust_for_strength(base_score: int, strength_a: int, strength_b: int) -> int:
    """
    Adjust base score by ±5 based on how strongly each user expresses their type.
    - Both strong (≥76): +5 (high confidence in the pairing)
    - One mild (≤50): -5 (less confident, type might shift)
    """
    if strength_a >= 76 and strength_b >= 76:
        return min(base_score + 5, 98)
    elif strength_a <= 50 or strength_b <= 50:
        return max(base_score - 5, 25)
    return base_score


def severity_from_score(score: int) -> str:
    """Derive severity level from compatibility score."""
    if score >= 55:
        return "low"
    elif score >= 40:
        return "medium"
    else:
        return "high"


def compute_compatibility(
    profile_a_dimensions: Dict[str, dict],
    profile_b_dimensions: Dict[str, dict],
) -> CompatibilityResult:
    """
    Pure compatibility scoring function.

    Args:
        profile_a_dimensions: User A's dimension_scores JSONB (7 dimensions,
            each with "type" and "strength" fields).
        profile_b_dimensions: User B's dimension_scores JSONB.

    Returns:
        CompatibilityResult with overall score, per-dimension breakdown,
        top 3 strengths, bottom 3 challenges, and improvement plans.
    """
    dimensions: Dict[str, DimensionCompatibility] = {}

    for dim_key in DIMENSION_ORDER:
        dim_a = profile_a_dimensions.get(dim_key, {})
        dim_b = profile_b_dimensions.get(dim_key, {})

        type_a = dim_a.get("type", "unknown")
        type_b = dim_b.get("type", "unknown")
        strength_a = dim_a.get("strength", 50)
        strength_b = dim_b.get("strength", 50)

        # Step 1: Matrix lookup
        base_score = lookup_score(dim_key, type_a, type_b)

        # Step 2: Strength adjustment
        adjusted_score = adjust_for_strength(base_score, strength_a, strength_b)

        # Step 3: Label
        label = score_to_label(adjusted_score)

        # Step 4: Build recommendation text
        severity = severity_from_score(adjusted_score)
        rec = get_recommendation(dim_key, type_a, type_b, severity)
        recommendation_text = rec.get("challenge_description", "")

        dimensions[dim_key] = DimensionCompatibility(
            dimension=dim_key,
            dimension_name=DIMENSION_NAMES.get(dim_key, dim_key),
            score=adjusted_score,
            base_score=base_score,
            label=label,
            user_a_type=type_a,
            user_b_type=type_b,
            recommendation=recommendation_text,
        )

    # Step 5: Weighted overall score
    weighted_sum = sum(
        dimensions[d].score * DIMENSION_WEIGHTS[d]
        for d in DIMENSION_ORDER
        if d in dimensions
    )
    overall = weighted_sum / TOTAL_WEIGHT
    overall = max(25.0, min(98.0, round(overall, 2)))

    # Step 6: Improvement potential (100 - avg of 3 lowest)
    sorted_scores = sorted(d.score for d in dimensions.values())
    bottom_3_avg = sum(sorted_scores[:3]) / 3 if len(sorted_scores) >= 3 else 50
    improvement_potential = round(100 - bottom_3_avg, 2)

    # Step 7: Strengths (top 3) and Challenges (bottom 3)
    sorted_dims = sorted(dimensions.values(), key=lambda d: d.score, reverse=True)
    strengths = sorted_dims[:3]
    challenges = sorted_dims[-3:]

    # Step 8: Build improvement plans for challenges
    challenge_plans = []
    for challenge in challenges:
        severity = severity_from_score(challenge.score)
        rec = get_recommendation(
            challenge.dimension, challenge.user_a_type, challenge.user_b_type, severity
        )
        challenge_plans.append({
            "dimension": challenge.dimension,
            "dimension_name": challenge.dimension_name,
            "severity": severity,
            "score": challenge.score,
            "user_a_type": challenge.user_a_type,
            "user_b_type": challenge.user_b_type,
            "challenge_description": rec.get("challenge_description", ""),
            "action_plan": rec.get("action_plan", []),
            "weekly_exercise": rec.get("weekly_exercise", ""),
        })

    return CompatibilityResult(
        overall_score=overall,
        overall_label=score_to_label(round(overall)),
        improvement_potential=improvement_potential,
        dimensions=dimensions,
        strengths=strengths,
        challenges=challenges,
        challenge_plans=challenge_plans,
    )
