# -*- coding: utf-8 -*-
"""Compatibility scoring matrices (F5B).

Each matrix maps (type_a, type_b) → base compatibility score (0–100).
Keys are sorted tuples (symmetric: order doesn't matter).
All values sourced from CompatibilityMatrix.md.
"""

from __future__ import annotations

ATTACHMENT_MATRIX: dict[tuple[str, str], int] = {
    ("secure", "secure"): 92,
    ("anxious", "secure"): 70,
    ("avoidant", "secure"): 65,
    ("fearful_avoidant", "secure"): 55,
    ("anxious", "anxious"): 55,
    ("anxious", "avoidant"): 35,
    ("anxious", "fearful_avoidant"): 40,
    ("avoidant", "avoidant"): 48,
    ("avoidant", "fearful_avoidant"): 42,
    ("fearful_avoidant", "fearful_avoidant"): 38,
}

COMMUNICATION_MATRIX: dict[tuple[str, str], int] = {
    ("direct", "direct"): 78,
    ("direct", "diplomatic"): 58,
    ("analytical", "direct"): 75,
    ("direct", "expressive"): 52,
    ("diplomatic", "diplomatic"): 80,
    ("analytical", "diplomatic"): 60,
    ("diplomatic", "expressive"): 76,
    ("analytical", "analytical"): 78,
    ("analytical", "expressive"): 45,
    ("expressive", "expressive"): 80,
}

CONFLICT_MATRIX: dict[tuple[str, str], int] = {
    ("collaborative", "collaborative"): 90,
    ("collaborative", "compromising"): 78,
    ("avoiding", "collaborative"): 48,
    ("collaborative", "competing"): 58,
    ("compromising", "compromising"): 75,
    ("avoiding", "compromising"): 55,
    ("competing", "compromising"): 58,
    ("avoiding", "avoiding"): 42,
    ("avoiding", "competing"): 35,
    ("competing", "competing"): 42,
}

LOVE_LANGUAGE_MATRIX: dict[tuple[str, str], int] = {
    ("words", "words"): 85,
    ("acts", "words"): 60,
    ("gifts", "words"): 58,
    ("touch", "words"): 62,
    ("time", "words"): 65,
    ("acts", "acts"): 85,
    ("acts", "gifts"): 62,
    ("acts", "touch"): 58,
    ("acts", "time"): 65,
    ("gifts", "gifts"): 85,
    ("gifts", "touch"): 55,
    ("gifts", "time"): 55,
    ("touch", "touch"): 88,
    ("time", "touch"): 68,
    ("time", "time"): 88,
}

FINANCIAL_MATRIX: dict[tuple[str, str], int] = {
    ("saver", "saver"): 82,
    ("saver", "spender"): 38,
    ("investor", "saver"): 72,
    ("balanced", "saver"): 70,
    ("spender", "spender"): 70,
    ("investor", "spender"): 58,
    ("balanced", "spender"): 68,
    ("investor", "investor"): 85,
    ("balanced", "investor"): 72,
    ("balanced", "balanced"): 75,
}

LIFESTYLE_MATRIX: dict[tuple[str, str], int] = {
    ("adventurous", "adventurous"): 80,
    ("adventurous", "homebody"): 38,
    ("adventurous", "balanced"): 72,
    ("adventurous", "social"): 78,
    ("homebody", "homebody"): 82,
    ("balanced", "homebody"): 72,
    ("homebody", "social"): 42,
    ("balanced", "balanced"): 78,
    ("balanced", "social"): 70,
    ("social", "social"): 80,
}

ARCHETYPE_MATRIX: dict[tuple[str, str], int] = {
    ("partner", "partner"): 82,
    ("independent", "partner"): 48,
    ("nurturer", "partner"): 85,
    ("explorer", "partner"): 52,
    ("independent", "independent"): 78,
    ("independent", "nurturer"): 55,
    ("explorer", "independent"): 75,
    ("nurturer", "nurturer"): 65,
    ("explorer", "nurturer"): 62,
    ("explorer", "explorer"): 75,
}

# All matrices indexed by dimension key
MATRICES: dict[str, dict[tuple[str, str], int]] = {
    "attachment_style": ATTACHMENT_MATRIX,
    "communication_style": COMMUNICATION_MATRIX,
    "conflict_style": CONFLICT_MATRIX,
    "love_language": LOVE_LANGUAGE_MATRIX,
    "financial_personality": FINANCIAL_MATRIX,
    "lifestyle_type": LIFESTYLE_MATRIX,
    "relationship_archetype": ARCHETYPE_MATRIX,
}

# Dimension weights for overall score calculation
DIMENSION_WEIGHTS: dict[str, float] = {
    "attachment_style": 1.5,
    "communication_style": 1.3,
    "conflict_style": 1.3,
    "love_language": 1.0,
    "financial_personality": 1.2,
    "lifestyle_type": 0.9,
    "relationship_archetype": 0.8,
}

TOTAL_WEIGHT: float = sum(DIMENSION_WEIGHTS.values())  # 8.0


def lookup_score(dimension: str, type_a: str, type_b: str) -> int:
    """
    Look up the base compatibility score for a type pairing.
    Symmetric: order doesn't matter (key is sorted tuple).
    Returns 50 as default if the pairing is not found.
    """
    matrix = MATRICES.get(dimension)
    if not matrix:
        return 50

    key = tuple(sorted([type_a, type_b]))
    return matrix.get(key, 50)
