# -*- coding: utf-8 -*-
"""Human Coach — Public API (F8E.11).

The entry point for the narrative engine.
Pipeline: Reasoner → Narrative Builder → v3 JSON

This replaces the template-based coaching for migrated dimensions.
Non-migrated dimensions fall back to the existing coach.py pipeline.
"""

from __future__ import annotations

from typing import Optional

from .relationship_reasoner import reason_about_relationship
from .narrative_builder import (
    build_opening,
    build_validation,
    build_feelings,
    build_why,
    build_user_guidance,
    build_partner_guidance,
    build_together_guidance,
    build_weekly_challenge,
    build_first_step,
    build_closing,
)
from .wisdom import get_introduction, select_wisdom
from .coach_personality import get_transition, get_permission
from .wisdom_selector import select_wisdom_touches

# Dimensions that have been migrated to the narrative engine
MIGRATED_DIMENSIONS = {"attachment_style"}


def is_migrated(dimension: str) -> bool:
    """Check if a dimension uses the narrative engine."""
    return dimension in MIGRATED_DIMENSIONS


def generate_human_coaching(
    dimension: str,
    severity: str,
    user_name: str,
    partner_name: str,
    user_type: str,
    partner_type: str,
    overall_score: float = 60.0,
    user_id: str = "",
    report_id: str = "",
) -> Optional[dict]:
    """
    Generate a coaching plan using the narrative engine.

    Returns None if the dimension hasn't been migrated yet.
    Returns a v3-compatible dict if it has.

    The output shape is IDENTICAL to coach.py's generate_coaching_plan()
    so the frontend doesn't need to change.
    """
    if not is_migrated(dimension):
        return None

    # Step 1: Understand
    insight = reason_about_relationship(
        user_name, partner_name, user_type, partner_type, dimension, severity, overall_score
    )

    # Step 2: Select wisdom
    wisdom_quote = select_wisdom(dimension, severity, user_id, report_id)
    wisdom_touches = select_wisdom_touches(dimension, severity, overall_score, user_id, report_id)

    # Step 3: Build narrative
    return {
        "version": 3,
        "user_name": user_name,
        "partner_name": partner_name,
        "introduction": get_introduction(overall_score),
        "whats_happening": build_opening(insight, user_name, partner_name),
        "example_dialogue": [],  # Preserved from existing coach.py when available
        "example_closing": "",
        "feelings": build_feelings(insight, user_name, partner_name),
        "why_this_happens": build_why(insight, user_name, partner_name),
        "validation": build_validation(insight, user_name, partner_name),
        "difficulty": {
            "level": {"low": "easy", "medium": "moderate", "high": "challenging"}.get(severity, "moderate"),
            "explanation": insight.realistic_timeline,
            "confidence": "high" if severity in ("low", "medium") else "medium",
            "confidence_explanation": insight.opportunity,
        },
        "user_actions": build_user_guidance(insight, user_name, partner_name),
        "partner_actions": build_partner_guidance(insight, user_name, partner_name),
        "together_actions": build_together_guidance(insight, user_name, partner_name),
        "mistakes": _build_mistakes(insight, user_name, partner_name),
        "weekly_challenge": build_weekly_challenge(insight, user_name, partner_name),
        "first_step": build_first_step(insight, user_name, partner_name),
        "can_this_improve": _build_hope(insight, user_name, partner_name),
        "expected_outcome": _build_outcome(insight, user_name, partner_name),
        "wisdom": wisdom_quote,
        "wisdom_closing": build_closing(insight, user_name, partner_name, wisdom_quote),
        "wisdom_touches": wisdom_touches,
    }


def _build_mistakes(insight, user_name: str, partner_name: str) -> list:
    """Dimension-specific mistakes — phrased as patterns to watch for."""
    if insight.dimension == "attachment_style":
        return [
            f"Sending multiple messages when the first hasn't been answered yet",
            f"Taking space without communicating when you'll return",
            f"Reading silence as rejection rather than processing time",
            f"Saying 'you always' or 'you never' during the pattern",
            f"Trying to change how the other person is wired rather than working with it",
        ]
    return [
        "Expecting change overnight — patterns take weeks to shift",
        "Keeping score of who tries harder",
        "Having important conversations when tired or hungry",
    ]


def _build_hope(insight, user_name: str, partner_name: str) -> str:
    """Realistic encouragement — always yes, never false."""
    return (
        f"Yes — and often faster than people expect.\n\n"
        f"{insight.opportunity}\n\n"
        f"{insight.realistic_timeline}. The hardest part is the first week. "
        f"After that, the new rhythm starts to feel natural."
    )


def _build_outcome(insight, user_name: str, partner_name: str) -> str:
    """What to watch for in 2–4 weeks."""
    if insight.dimension == "attachment_style":
        return (
            f"After a few weeks of consistent practice, you'll likely notice: "
            f"fewer anxious check-ins from {user_name}, more spontaneous "
            f"connection from {partner_name}, and a shared feeling that the "
            f"relationship has a rhythm you can both count on."
        )
    return f"After 2–3 weeks, both {user_name} and {partner_name} should notice the pattern has less grip."
