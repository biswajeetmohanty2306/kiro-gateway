# -*- coding: utf-8 -*-
"""Pure scoring engine (F2B).

This module is a PURE FUNCTION — no database, no I/O, no side effects.
Given answers + question metadata, it produces dimension scores and profile types.

Scoring algorithm:
1. Group answers by dimension (category)
2. For standard dimensions: compute weighted sub-scale sums, normalize to 0–100
3. For Love Language: count-based scoring (selected language gets +1)
4. Determine primary type per dimension via highest sub-score + tie-breaking
5. Compute overall assessment score (average of 7 dimension scores)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .constants import (
    LOVE_LANGUAGE_CATEGORY,
    LOVE_LANGUAGE_KEYS,
    LOVE_LANGUAGE_QUESTION_COUNT,
    TIE_BREAK_ORDER,
)


@dataclass
class DimensionResult:
    """Scoring result for one dimension."""

    score: int  # overall dimension score (0–100)
    type: str  # primary type (tie-broken)
    strength: int  # primary type's sub-score (0–100)
    sub_scores: Dict[str, int]  # all sub-scale scores


@dataclass
class ScoringResult:
    """Complete scoring output."""

    overall_score: float  # average of 7 dimension scores
    dimensions: Dict[str, DimensionResult]  # keyed by category


def score_assessment(
    answers: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
) -> ScoringResult:
    """
    Pure scoring function: compute all dimension scores from answers + questions.

    Args:
        answers: list of dicts with keys: question_id, score, selected_option_index
        questions: list of dicts with keys: id, category, sub_scale, weight, answer_options

    Returns:
        ScoringResult with overall_score and per-dimension breakdown.
    """
    # Build question lookup
    question_map: Dict[str, Dict[str, Any]] = {q["id"]: q for q in questions}

    # Separate love language answers from standard answers
    standard_answers: Dict[str, List[tuple]] = {}  # category -> [(sub_scale, weight, score)]
    love_language_answers: List[Dict[str, Any]] = []

    for answer in answers:
        q = question_map[answer["question_id"]]
        category = q["category"]

        if category == LOVE_LANGUAGE_CATEGORY:
            love_language_answers.append(answer)
        else:
            if category not in standard_answers:
                standard_answers[category] = []
            standard_answers[category].append((
                q["sub_scale"],
                float(q["weight"]),
                int(answer["score"]),
            ))

    # Score standard dimensions
    dimensions: Dict[str, DimensionResult] = {}

    for category, answer_tuples in standard_answers.items():
        result = _score_standard_dimension(category, answer_tuples)
        dimensions[category] = result

    # Score Love Language dimension
    if love_language_answers:
        ll_result = _score_love_language(love_language_answers, question_map)
        dimensions[LOVE_LANGUAGE_CATEGORY] = ll_result

    # Overall assessment score = average of dimension scores
    if dimensions:
        overall = round(
            sum(d.score for d in dimensions.values()) / len(dimensions), 2
        )
    else:
        overall = 0.0

    return ScoringResult(overall_score=overall, dimensions=dimensions)


def _score_standard_dimension(
    category: str,
    answer_tuples: List[tuple],
) -> DimensionResult:
    """
    Score a standard (non-Love-Language) dimension.

    answer_tuples: list of (sub_scale, weight, score) for each answer in this dimension.
    """
    # Accumulate weighted sums and total weights per sub-scale
    sub_scale_data: Dict[str, Dict[str, float]] = {}

    for sub_scale, weight, score in answer_tuples:
        if sub_scale not in sub_scale_data:
            sub_scale_data[sub_scale] = {"weighted_sum": 0.0, "total_weight": 0.0}
        sub_scale_data[sub_scale]["weighted_sum"] += score * weight
        sub_scale_data[sub_scale]["total_weight"] += weight

    # Normalize each sub-scale to 0–100
    sub_scores: Dict[str, int] = {}

    for sub_scale, data in sub_scale_data.items():
        total_weight = data["total_weight"]
        if total_weight == 0:
            sub_scores[sub_scale] = 0
            continue

        weighted_sum = data["weighted_sum"]
        min_possible = total_weight * 1.0  # every question scored 1
        max_possible = total_weight * 5.0  # every question scored 5
        denominator = max_possible - min_possible

        if denominator == 0:
            sub_scores[sub_scale] = 0
            continue

        normalized = (weighted_sum - min_possible) / denominator * 100.0
        sub_scores[sub_scale] = round(normalized)

    # Determine primary type (highest sub-score, tie-broken)
    primary_type = _determine_primary_type(sub_scores, category)
    strength = sub_scores.get(primary_type, 0)

    # Dimension score = average of all sub-scale scores
    if sub_scores:
        dim_score = round(sum(sub_scores.values()) / len(sub_scores))
    else:
        dim_score = 0

    return DimensionResult(
        score=dim_score,
        type=primary_type,
        strength=strength,
        sub_scores=sub_scores,
    )


def _score_love_language(
    answers: List[Dict[str, Any]],
    question_map: Dict[str, Dict[str, Any]],
) -> DimensionResult:
    """
    Score the Love Language dimension using count-based model.

    Each answer's selected option has a 'language' field. Count selections per language.
    Normalize: count × 10 (for 10 questions → max count per language is 10).
    """
    counts: Dict[str, int] = {lang: 0 for lang in LOVE_LANGUAGE_KEYS}

    for answer in answers:
        q = question_map[answer["question_id"]]
        options = q["answer_options"]

        # Handle options as list of dicts (may be already parsed or raw)
        if isinstance(options, str):
            import json
            options = json.loads(options)

        selected_index = int(answer["selected_option_index"])
        selected_option = options[selected_index]

        language = selected_option.get("language")
        if language and language in counts:
            counts[language] += 1

    # Normalize: count × (100 / total_questions)
    multiplier = 100.0 / LOVE_LANGUAGE_QUESTION_COUNT if LOVE_LANGUAGE_QUESTION_COUNT > 0 else 0
    sub_scores: Dict[str, int] = {
        lang: round(count * multiplier) for lang, count in counts.items()
    }

    # Primary type
    primary_type = _determine_primary_type(sub_scores, LOVE_LANGUAGE_CATEGORY)
    strength = sub_scores.get(primary_type, 0)

    # Dimension score for Love Language = the primary language's score (max of sub-scores)
    dim_score = max(sub_scores.values()) if sub_scores else 0

    return DimensionResult(
        score=dim_score,
        type=primary_type,
        strength=strength,
        sub_scores=sub_scores,
    )


def _determine_primary_type(sub_scores: Dict[str, int], category: str) -> str:
    """
    Determine primary type from sub-scores with deterministic tie-breaking.

    Returns the sub-scale with the highest score. On tie, the first in
    TIE_BREAK_ORDER for this category wins.
    """
    if not sub_scores:
        # Fallback: return first in priority order
        priority = TIE_BREAK_ORDER.get(category, [])
        return priority[0] if priority else "unknown"

    max_score = max(sub_scores.values())
    tied = [k for k, v in sub_scores.items() if v == max_score]

    if len(tied) == 1:
        return tied[0]

    # Tie-break: first in priority order
    priority = TIE_BREAK_ORDER.get(category, [])
    for type_name in priority:
        if type_name in tied:
            return type_name

    # Fallback (shouldn't happen with valid data)
    return tied[0]
