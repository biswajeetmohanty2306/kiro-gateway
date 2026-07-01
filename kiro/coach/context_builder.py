# -*- coding: utf-8 -*-
"""AI Relationship Coach Context Builder (J7-C).

Transforms raw relationship data into strongly typed RelationshipContext
objects consumed by the Prompt Engine.

Pure module:
  - No SQL, no async, no FastAPI, no HTTP, no I/O
  - Deterministic: same inputs always produce same outputs
  - Never mutates inputs
  - Provides sensible defaults for all missing data

Public API:
  build_relationship_context(...) → RelationshipContext
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .types import RelationshipContext


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_VALID_PHASES = frozenset({"EARLY", "BUILDING", "GROWING", "ESTABLISHED"})
_DEFAULT_PHASE = "EARLY"

_DIMENSION_DISPLAY_NAMES: Dict[str, str] = {
    "attachment_style": "Attachment Style",
    "communication_style": "Communication Style",
    "conflict_style": "Conflict Style",
    "love_language": "Love Language",
    "financial_personality": "Financial Personality",
    "lifestyle_type": "Lifestyle Type",
    "relationship_archetype": "Relationship Archetype",
}

_MAX_STRENGTHS = 3
_MAX_CHALLENGES = 3
_MAX_ACTIVE_PLANS = 5


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def build_relationship_context(
    user_name: Optional[str] = None,
    partner_name: Optional[str] = None,
    overall_score: Optional[float] = None,
    dimension_scores: Optional[Dict[str, Dict]] = None,
    journey_phase: Optional[str] = None,
    current_week: Optional[int] = None,
    total_reflections: Optional[int] = None,
    recent_insight: Optional[str] = None,
    weekly_sync_status: Optional[str] = None,
    improvement_plans: Optional[List[Dict]] = None,
) -> RelationshipContext:
    """Build a RelationshipContext from raw data sources.

    All parameters are optional. Missing data produces sensible defaults
    rather than errors. The resulting context is immutable.

    Args:
        user_name: Display name of the current user.
        partner_name: Display name of the partner.
        overall_score: Compatibility score (0–100).
        dimension_scores: Dict of dimension_key → {score, label, recommendation, ...}.
        journey_phase: One of EARLY, BUILDING, GROWING, ESTABLISHED.
        current_week: Current journey week number.
        total_reflections: Number of completed reflections.
        recent_insight: Latest insight message from the insights engine.
        weekly_sync_status: Latest sync status (SYNCED, GROWING, MISALIGNED, etc.).
        improvement_plans: List of plan dicts with dimension, severity, challenge_description.

    Returns:
        A frozen RelationshipContext dataclass.
    """
    identity_user, identity_partner = _build_identity(user_name, partner_name)
    score, strengths, challenges, summaries = _build_compatibility(overall_score, dimension_scores)
    phase, week, reflections = _build_journey(journey_phase, current_week, total_reflections)
    active, completed = _build_plans(improvement_plans)

    return RelationshipContext(
        user_name=identity_user,
        partner_name=identity_partner,
        overall_score=score,
        top_strengths=strengths,
        top_challenges=challenges,
        dimension_summaries=summaries,
        journey_phase=phase,
        current_week=week,
        total_reflections=reflections,
        recent_insight=recent_insight if recent_insight else None,
        weekly_sync_status=weekly_sync_status if weekly_sync_status else None,
        active_challenges=active,
        completed_plans=completed,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Private Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_identity(
    user_name: Optional[str],
    partner_name: Optional[str],
) -> tuple:
    """Extract and normalize display names."""
    u = (user_name or "").strip() or "User"
    p = (partner_name or "").strip() or "Partner"
    return u, p


def _build_compatibility(
    overall_score: Optional[float],
    dimension_scores: Optional[Dict[str, Dict]],
) -> tuple:
    """Extract score, strengths, challenges, and dimension summaries."""
    score = _normalize_score(overall_score)

    if not dimension_scores:
        return score, [], [], {}

    # Sort dimensions by score descending
    scored_dims = []
    for dim_key, dim_data in dimension_scores.items():
        if isinstance(dim_data, dict):
            dim_score = dim_data.get("score", 50)
            scored_dims.append((dim_key, dim_score, dim_data))

    scored_dims.sort(key=lambda x: x[1], reverse=True)

    # Top strengths and challenges
    strengths = [
        _dimension_display_name(d[0]) for d in scored_dims[:_MAX_STRENGTHS]
    ]
    challenges = [
        _dimension_display_name(d[0]) for d in scored_dims[-_MAX_CHALLENGES:]
    ]

    # Dimension summaries
    summaries = {}
    for dim_key, dim_score, dim_data in scored_dims:
        display = _dimension_display_name(dim_key)
        recommendation = dim_data.get("recommendation", "")
        if recommendation:
            summaries[display] = recommendation
        else:
            summaries[display] = f"Score: {dim_score}"

    return score, strengths, challenges, summaries


def _build_journey(
    journey_phase: Optional[str],
    current_week: Optional[int],
    total_reflections: Optional[int],
) -> tuple:
    """Normalize journey state values."""
    phase = _normalize_phase(journey_phase)
    week = max(0, current_week) if current_week is not None else 0
    reflections = max(0, total_reflections) if total_reflections is not None else 0
    return phase, week, reflections


def _build_plans(
    improvement_plans: Optional[List[Dict]],
) -> tuple:
    """Extract active challenges and completed count from improvement plans."""
    if not improvement_plans:
        return [], 0

    active: List[str] = []
    completed = 0

    for plan in improvement_plans:
        if not isinstance(plan, dict):
            continue

        is_completed = plan.get("completed", False)
        if is_completed:
            completed += 1
        else:
            description = _normalize_plan(plan)
            if description and len(active) < _MAX_ACTIVE_PLANS:
                active.append(description)

    return active, completed


def _normalize_score(score: Optional[float]) -> float:
    """Normalize compatibility score to valid range."""
    if score is None:
        return 0.0
    return max(0.0, min(100.0, float(score)))


def _normalize_phase(phase: Optional[str]) -> str:
    """Normalize journey phase to a valid value."""
    if not phase:
        return _DEFAULT_PHASE
    upper = phase.strip().upper()
    return upper if upper in _VALID_PHASES else _DEFAULT_PHASE


def _normalize_plan(plan: Dict) -> str:
    """Extract a human-readable description from a plan dict."""
    description = plan.get("challenge_description", "")
    if description and isinstance(description, str):
        return description.strip()

    # Fallback: use dimension name
    dimension = plan.get("dimension", "")
    if dimension:
        return f"{_dimension_display_name(dimension)} challenge"

    return ""


def _dimension_display_name(dim_key: str) -> str:
    """Convert a dimension key to a human-readable name."""
    return _DIMENSION_DISPLAY_NAMES.get(dim_key, dim_key.replace("_", " ").title())
