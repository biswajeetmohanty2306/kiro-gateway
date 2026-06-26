# -*- coding: utf-8 -*-
"""Journey Insights Engine (J4).

Pure deterministic trend analysis based on weekly reflection history.
No AI, no external services — simple pattern detection from scale answers.

Input: list of reflection payloads (most recent first, as returned by get_history).
Output: a single Insight dict or None if insufficient data.

Architecture:
  - Analyzes only scale-type answers (numeric 1–5)
  - Converts yes/no answers to numeric (yes=5, no=1)
  - Ignores open-ended text answers
  - Computes trend direction using simple linear slope
  - Always supportive wording — never judgmental
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_MIN_REFLECTIONS = 3  # Minimum history required to generate an insight

# Question categories for insight messaging
_SAFETY_IDS = {"safety_1", "safety_2", "safety_3"}
_CONNECTION_IDS = {"conn_1", "conn_2", "conn_3", "conn_4", "conn_5", "conn_6"}

# Trend thresholds (slope per week)
_IMPROVING_THRESHOLD = 0.15   # Average score increasing by 0.15+ per week
_DECLINING_THRESHOLD = -0.15  # Average score decreasing by 0.15+ per week

# ─────────────────────────────────────────────────────────────────────────────
# Insight Messages (always supportive)
# ─────────────────────────────────────────────────────────────────────────────

_MESSAGES = {
    "safety_improving": [
        "Over the last few weeks, you've consistently reported feeling safer with each other.",
        "Emotional safety between you seems to be growing. That's a meaningful foundation.",
        "You're both creating more space for vulnerability. That takes real trust.",
    ],
    "safety_stable": [
        "Emotional safety between you has been steady. That stability is something to value.",
        "You've maintained a consistent sense of safety with each other. That's not nothing.",
    ],
    "connection_improving": [
        "Your sense of connection seems to be getting stronger each week.",
        "The way you're showing up for each other is becoming more consistent.",
        "Connection is growing. Small moments of attention add up over time.",
    ],
    "connection_stable": [
        "Your connection has been steady. Consistency like that builds trust over time.",
        "You've maintained a solid sense of togetherness. That's worth noticing.",
    ],
    "overall_improving": [
        "Things seem to be moving in a good direction between you.",
        "Week by week, your reflections show a gentle upward pattern.",
        "You're both investing, and it shows in how you describe your weeks together.",
    ],
    "overall_stable": [
        "Things between you have been consistent. Stability is its own kind of strength.",
        "Your reflections show a steady rhythm. That reliability matters.",
    ],
    "consistency": [
        "You've checked in {count} weeks in a row. That consistency builds understanding over time.",
        "Showing up every week is its own form of commitment. You've done it {count} times now.",
    ],
    "insufficient": [
        "Keep checking in each week. We'll begin spotting patterns soon.",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def generate_insight(reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a single journey insight from reflection history.

    Args:
        reflections: List of reflection entries (most recent first).
                     Each entry has: {week_number, responses: [{question_id, answer}]}

    Returns:
        {trend, confidence, message} or a placeholder message if insufficient data.
    """
    if len(reflections) < _MIN_REFLECTIONS:
        return {
            "trend": "insufficient",
            "confidence": 0.0,
            "message": _MESSAGES["insufficient"][0],
        }

    # Extract numeric scores per week (chronological order — oldest first)
    weekly_scores = _extract_weekly_scores(list(reversed(reflections)))

    if len(weekly_scores) < _MIN_REFLECTIONS:
        return {
            "trend": "insufficient",
            "confidence": 0.0,
            "message": _MESSAGES["insufficient"][0],
        }

    # Analyze by category
    safety_insight = _analyze_category(weekly_scores, _SAFETY_IDS, "safety")
    connection_insight = _analyze_category(weekly_scores, _CONNECTION_IDS, "connection")
    overall_insight = _analyze_overall(weekly_scores)
    consistency_insight = _analyze_consistency(reflections)

    # Pick the best insight (priority: improving > consistency > stable)
    candidates = [safety_insight, connection_insight, overall_insight, consistency_insight]
    candidates = [c for c in candidates if c is not None]

    if not candidates:
        return overall_insight or {
            "trend": "stable",
            "confidence": 0.5,
            "message": _MESSAGES["overall_stable"][0],
        }

    # Prefer improving trends, then consistency, then stable
    improving = [c for c in candidates if c["trend"] == "improving"]
    if improving:
        return max(improving, key=lambda c: c["confidence"])

    consistency = [c for c in candidates if c["trend"] == "consistency"]
    if consistency:
        return consistency[0]

    stable = [c for c in candidates if c["trend"] == "stable"]
    if stable:
        return max(stable, key=lambda c: c["confidence"])

    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Internal Analysis
# ─────────────────────────────────────────────────────────────────────────────


def _extract_weekly_scores(reflections: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    """Extract numeric scores from each reflection (chronological order).

    Returns list of dicts: [{question_id: score, ...}, ...]
    Converts: scale answers → float, yes → 5.0, no → 1.0
    Skips open-ended answers.
    """
    weekly = []
    for entry in reflections:
        scores: Dict[str, float] = {}
        responses = entry.get("responses", [])

        # Handle v1 payload format
        if isinstance(responses, dict):
            responses = responses.get("answers", [])

        for resp in responses:
            qid = resp.get("question_id", "")
            answer = resp.get("answer", "")

            # Skip open-ended
            if qid.startswith("open_"):
                continue

            # Convert to numeric
            score = _answer_to_score(answer)
            if score is not None:
                scores[qid] = score

        if scores:
            weekly.append(scores)

    return weekly


def _answer_to_score(answer: str) -> Optional[float]:
    """Convert an answer string to a numeric score."""
    # Scale answer (1–5)
    try:
        val = float(answer)
        if 1.0 <= val <= 5.0:
            return val
    except (ValueError, TypeError):
        pass

    # Yes/No
    lower = answer.strip().lower()
    if lower == "yes":
        return 5.0
    if lower == "no":
        return 1.0

    return None


def _analyze_category(
    weekly_scores: List[Dict[str, float]],
    question_ids: set,
    category: str,
) -> Optional[Dict[str, Any]]:
    """Analyze trend for a specific question category (safety or connection)."""
    # Extract averages per week for this category
    averages = []
    for week in weekly_scores:
        cat_scores = [v for k, v in week.items() if k in question_ids]
        if cat_scores:
            averages.append(sum(cat_scores) / len(cat_scores))

    if len(averages) < _MIN_REFLECTIONS:
        return None

    # Use last 4–6 weeks for trend (or all if fewer)
    window = averages[-6:]
    slope = _compute_slope(window)
    confidence = _slope_to_confidence(slope, window)

    if slope >= _IMPROVING_THRESHOLD:
        trend = "improving"
        messages = _MESSAGES.get(f"{category}_improving", _MESSAGES["overall_improving"])
    elif slope <= _DECLINING_THRESHOLD:
        # Never negative messaging — frame as stable with encouragement
        trend = "stable"
        messages = _MESSAGES.get(f"{category}_stable", _MESSAGES["overall_stable"])
    else:
        trend = "stable"
        messages = _MESSAGES.get(f"{category}_stable", _MESSAGES["overall_stable"])

    # Select message based on data length for variety
    msg_index = len(averages) % len(messages)
    return {
        "trend": trend,
        "confidence": round(confidence, 2),
        "message": messages[msg_index],
    }


def _analyze_overall(weekly_scores: List[Dict[str, float]]) -> Optional[Dict[str, Any]]:
    """Analyze overall trend across all numeric answers."""
    averages = []
    for week in weekly_scores:
        all_scores = list(week.values())
        if all_scores:
            averages.append(sum(all_scores) / len(all_scores))

    if len(averages) < _MIN_REFLECTIONS:
        return None

    window = averages[-6:]
    slope = _compute_slope(window)
    confidence = _slope_to_confidence(slope, window)

    if slope >= _IMPROVING_THRESHOLD:
        trend = "improving"
        messages = _MESSAGES["overall_improving"]
    else:
        trend = "stable"
        messages = _MESSAGES["overall_stable"]

    msg_index = len(averages) % len(messages)
    return {
        "trend": trend,
        "confidence": round(confidence, 2),
        "message": messages[msg_index],
    }


def _analyze_consistency(reflections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Detect reflection consistency (consecutive weeks)."""
    if len(reflections) < 3:
        return None

    # Check if the last N reflections are consecutive weeks
    week_numbers = [r.get("week_number", 0) for r in reflections]
    # Most recent first — check descending sequence
    streak = 1
    for i in range(1, len(week_numbers)):
        if week_numbers[i - 1] - week_numbers[i] == 1:
            streak += 1
        else:
            break

    if streak >= 3:
        messages = _MESSAGES["consistency"]
        msg = messages[streak % len(messages)].format(count=streak)
        return {
            "trend": "consistency",
            "confidence": round(min(0.95, 0.6 + (streak * 0.05)), 2),
            "message": msg,
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Math Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _compute_slope(values: List[float]) -> float:
    """Compute simple linear regression slope for a series of values.

    Uses least-squares method. Returns slope per unit (per week).
    """
    n = len(values)
    if n < 2:
        return 0.0

    # x = 0, 1, 2, ..., n-1
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0

    return numerator / denominator


def _slope_to_confidence(slope: float, values: List[float]) -> float:
    """Convert slope magnitude and consistency into a confidence score (0–1).

    Higher slope → higher confidence.
    Lower variance → higher confidence.
    """
    if not values:
        return 0.0

    # Base confidence from slope magnitude
    abs_slope = abs(slope)
    slope_conf = min(1.0, abs_slope / 0.5)  # maxes at slope of 0.5/week

    # Variance penalty — inconsistent data reduces confidence
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    # Normalize variance (max expected variance for 1-5 scale is ~4)
    variance_penalty = min(1.0, variance / 2.0)
    consistency_bonus = 1.0 - (variance_penalty * 0.3)

    return max(0.0, min(1.0, slope_conf * consistency_bonus))
