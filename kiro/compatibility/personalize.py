# -*- coding: utf-8 -*-
"""Improvement plan personalization module (F8A).

Transforms generic improvement plans into personalized plans using real user
names and type-specific explanations. This module is a pure transformation
layer — it does no I/O, no database access, and no scoring.

Usage:
    personalized = personalize_challenge_plans(
        plans, user_name="Sarah", partner_name="Raj",
        user_types={"attachment_style": "anxious", ...},
        partner_types={"attachment_style": "avoidant", ...},
    )
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Type descriptions: what each type MEANS in plain English
# ─────────────────────────────────────────────────────────────────────────────

TYPE_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "attachment_style": {
        "secure": "feels naturally comfortable with closeness and independence",
        "anxious": "tends to seek reassurance and closeness in relationships",
        "avoidant": "values independence and needs space to feel comfortable",
        "fearful_avoidant": "oscillates between wanting closeness and needing distance",
    },
    "communication_style": {
        "direct": "prefers to communicate plainly and get to the point quickly",
        "diplomatic": "prefers to wrap messages in softness and reads between lines",
        "analytical": "processes information through logic and structured thinking",
        "expressive": "processes and shares through emotion and storytelling",
    },
    "conflict_style": {
        "collaborative": "wants to discuss issues together and find mutual solutions",
        "compromising": "seeks middle-ground solutions that partially satisfy both sides",
        "avoiding": "prefers to step away from conflict and process independently",
        "competing": "engages intensely and advocates strongly for their position",
    },
    "love_language": {
        "words": "feels most loved through verbal affirmation and appreciation",
        "acts": "feels most loved through helpful actions and practical support",
        "gifts": "feels most loved through thoughtful tokens and surprises",
        "touch": "feels most loved through physical affection and closeness",
        "time": "feels most loved through focused presence and undivided attention",
    },
    "financial_personality": {
        "saver": "prioritizes financial security and careful spending",
        "spender": "values experiences and quality of life through spending",
        "investor": "focuses on growing wealth and long-term financial goals",
        "balanced": "maintains a moderate approach to saving and spending",
    },
    "lifestyle_type": {
        "adventurous": "is energized by new experiences and activities outside the home",
        "homebody": "recharges through quiet time and comfortable home routines",
        "social": "is energized by people and social gatherings",
        "balanced": "enjoys a mix of activity and downtime",
    },
    "relationship_archetype": {
        "partner": "values shared identity and togetherness in the relationship",
        "nurturer": "expresses love through caregiving and support",
        "independent": "values maintained autonomy within the relationship",
        "explorer": "seeks growth, novelty, and personal development",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Why explanations: root cause by dimension (type-agnostic framing)
# ─────────────────────────────────────────────────────────────────────────────

WHY_TEMPLATES: Dict[str, str] = {
    "attachment_style": (
        "For {user_name}, connection and closeness feel like safety — so {user_name} {user_desc_short}. "
        "For {partner_name}, independence feels like safety — so {partner_name} {partner_desc_short}. "
        "Neither is wrong — you simply have different ways of feeling safe in relationships. "
        "Friction happens when one person's safety behavior triggers the other's discomfort."
    ),
    "communication_style": (
        "{user_name} naturally {user_desc_short}, while {partner_name} {partner_desc_short}. "
        "Neither approach is better — they're just different languages. "
        "Misunderstandings occur because each expects the other to communicate in their style."
    ),
    "conflict_style": (
        "When disagreements arise, {user_name} {user_desc_short}, "
        "while {partner_name} {partner_desc_short}. "
        "Neither response is wrong — both are valid attempts to handle difficult moments. "
        "Problems emerge when these styles clash and neither feels heard."
    ),
    "love_language": (
        "{user_name} {user_desc_short}, while {partner_name} {partner_desc_short}. "
        "Both of you ARE expressing love — just in different currencies. "
        "The gap isn't about effort; it's about translation."
    ),
    "financial_personality": (
        "{user_name} {user_desc_short}, while {partner_name} {partner_desc_short}. "
        "Neither approach is irresponsible — both reflect real emotional needs around money. "
        "Tension comes from judging the other's relationship with money by your own standards."
    ),
    "lifestyle_type": (
        "{user_name} {user_desc_short}, while {partner_name} {partner_desc_short}. "
        "These are stable preferences, not flaws. Neither needs to be 'fixed.' "
        "The challenge is finding a rhythm that respects both energy patterns."
    ),
    "relationship_archetype": (
        "{user_name} {user_desc_short}, while {partner_name} {partner_desc_short}. "
        "Both orientations are healthy. Neither is selfish or clingy. "
        "Friction arises when one person's need is read as a rejection of the other's."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Expected outcome templates by severity
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_OUTCOMES: Dict[str, Dict[str, str]] = {
    "attachment_style": {
        "low": "After 1 week of practice, both partners should notice slightly more ease during separations and reunions.",
        "medium": "After 2 weeks of consistent practice, you should notice fewer anxious-avoidant cycles and more predictable connection rhythms.",
        "high": "After 3–4 weeks of dedicated effort, both partners should experience noticeably fewer pursue-withdraw episodes and feel safer communicating needs directly.",
    },
    "communication_style": {
        "low": "After 1 week, conversations should flow more smoothly with fewer 'you don't get me' moments.",
        "medium": "After 2 weeks, both partners should feel more understood and experience fewer communication breakdowns.",
        "high": "After 3–4 weeks, both partners should be able to identify and adapt to each other's communication needs without explicit prompting.",
    },
    "conflict_style": {
        "low": "After 1 week, minor disagreements should resolve more quickly and with less frustration.",
        "medium": "After 2 weeks, conflicts should feel shorter and less intense, with both partners feeling heard.",
        "high": "After 3–4 weeks, at least one significant issue per week should reach actual resolution instead of being dropped or forced.",
    },
    "love_language": {
        "low": "After 1 week, both partners should feel noticeably more appreciated through intentional deposits in each other's language.",
        "medium": "After 2 weeks, both should report feeling 'more loved' without either partner doing more — just doing differently.",
        "high": "After 3–4 weeks, expressing love in your partner's language should start feeling natural rather than effortful.",
    },
    "financial_personality": {
        "low": "After 1 week, money conversations should carry less tension and more mutual respect.",
        "medium": "After 2 weeks, both partners should feel their financial values are respected, with fewer arguments about spending.",
        "high": "After 3–4 weeks, the agreed financial structure should be working smoothly with zero resentment-driven arguments.",
    },
    "lifestyle_type": {
        "low": "After 1 week, weekend planning should feel more collaborative and less like a negotiation.",
        "medium": "After 2 weeks, both partners should feel their energy needs are respected, with less guilt or frustration.",
        "high": "After 3–4 weeks, both partners should report genuine enjoyment during the other's preferred activities at least once.",
    },
    "relationship_archetype": {
        "low": "After 1 week, both partners should feel less tension around togetherness vs independence needs.",
        "medium": "After 2 weeks, both should feel their relational orientation is respected without the other feeling rejected.",
        "high": "After 3–4 weeks, a sustainable rhythm of together-time and independent-time should feel natural rather than negotiated.",
    },
}

# Generic fallback
GENERIC_OUTCOME: Dict[str, str] = {
    "low": "After 1 week of practice, you should notice small but meaningful improvements in how you navigate this area together.",
    "medium": "After 2 weeks of consistent effort, both partners should feel more understood and experience less friction in this area.",
    "high": "After 3–4 weeks of dedicated practice, significant improvement should be noticeable — fewer conflicts, more understanding, and a clearer path forward.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Dimension-specific closings for "Current Situation"
# ─────────────────────────────────────────────────────────────────────────────

_SITUATION_CLOSINGS: Dict[str, str] = {
    "attachment_style": "This can create a push-pull dynamic where reaching out triggers pulling away, and both of you end up feeling unsatisfied.",
    "communication_style": "This means the same conversation can land completely differently for each of you, leading to moments where neither feels understood.",
    "conflict_style": "When disagreements arise, your different instincts can make resolution feel harder than it needs to be.",
    "love_language": "You're both showing love — but in different currencies. Without translation, the effort can go unnoticed.",
    "financial_personality": "Money decisions can become charged because each of you sees the other's approach through the lens of your own values.",
    "lifestyle_type": "Weekends and free time can feel like a negotiation when your energy sources are different.",
    "relationship_archetype": "Your different orientations are both healthy, but without awareness they can feel like competing needs.",
    "_default": "This difference means you each bring different strengths, but it can also create moments where you feel out of sync.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Generic name replacements for action steps
# ─────────────────────────────────────────────────────────────────────────────

_GENERIC_PATTERNS = [
    (r"\bPartner A\b", "{user_name}"),
    (r"\bPartner B\b", "{partner_name}"),
    (r"\bOne partner\b", "{user_name}"),
    (r"\bThe other partner\b", "{partner_name}"),
    (r"\bone partner\b", "{user_name}"),
    (r"\bthe other partner\b", "{partner_name}"),
    (r"\bThe pursuing partner\b", "{user_name}"),
    (r"\bthe pursuing partner\b", "{user_name}"),
    (r"\bThe withdrawing partner\b", "{partner_name}"),
    (r"\bthe withdrawing partner\b", "{partner_name}"),
    (r"\bThe partner who reaches out more\b", "{user_name}"),
    (r"\bthe partner who reaches out more\b", "{user_name}"),
    (r"\bThe partner who needs space\b", "{partner_name}"),
    (r"\bthe partner who needs space\b", "{partner_name}"),
    (r"\bThe direct partner\b", "{user_name}"),
    (r"\bthe direct partner\b", "{user_name}"),
    (r"\bThe diplomatic partner\b", "{partner_name}"),
    (r"\bthe diplomatic partner\b", "{partner_name}"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def personalize_challenge_plans(
    plans: List[dict],
    user_name: str,
    partner_name: str,
    user_types: Dict[str, str],
    partner_types: Dict[str, str],
) -> List[dict]:
    """
    Transform generic challenge plans into personalized ones.

    Args:
        plans: Raw challenge_plans from compute_compatibility()
        user_name: Display name for user A (never empty — use email prefix as fallback)
        partner_name: Display name for user B
        user_types: {dimension: type} for user A (e.g., {"attachment_style": "anxious"})
        partner_types: {dimension: type} for user B

    Returns:
        List of enriched plan dicts with personalized content.
    """
    personalized = []
    for plan in plans:
        dimension = plan.get("dimension", "")
        severity = plan.get("severity", "medium")
        user_type = user_types.get(dimension, plan.get("user_a_type", "unknown"))
        partner_type = partner_types.get(dimension, plan.get("user_b_type", "unknown"))

        enriched = {
            **plan,
            "current_situation": build_current_situation(
                dimension, user_name, user_type, partner_name, partner_type
            ),
            "why_this_happens": build_why_section(
                dimension, user_name, user_type, partner_name, partner_type
            ),
            "action_plan": personalize_action_steps(
                plan.get("action_plan", []), user_name, partner_name
            ),
            "weekly_exercise": plan.get("weekly_exercise", ""),
            "expected_outcome": build_expected_outcome(dimension, severity),
        }
        personalized.append(enriched)

    return personalized


def build_current_situation(
    dimension: str,
    user_name: str,
    user_type: str,
    partner_name: str,
    partner_type: str,
) -> str:
    """
    Generate a personalized 2–4 sentence description of the current situation.
    """
    user_desc = _get_type_description(dimension, user_type)
    partner_desc = _get_type_description(dimension, partner_type)

    if user_type == partner_type:
        return (
            f"Both {user_name} and {partner_name} share a similar style in this area — "
            f"you both tend to {_verb_form(user_desc)}. "
            f"While this creates natural understanding, it can also amplify shared blind spots."
        )

    closing = _SITUATION_CLOSINGS.get(dimension, _SITUATION_CLOSINGS["_default"])
    return (
        f"{user_name} {user_desc}, while {partner_name} {partner_desc}. "
        f"{closing}"
    )


def build_why_section(
    dimension: str,
    user_name: str,
    user_type: str,
    partner_name: str,
    partner_type: str,
) -> str:
    """
    Generate a plain-English explanation of why this difference exists.
    """
    template = WHY_TEMPLATES.get(dimension)
    if not template:
        # Generic fallback
        user_desc = _get_type_description(dimension, user_type)
        partner_desc = _get_type_description(dimension, partner_type)
        return (
            f"{user_name} {user_desc}, while {partner_name} {partner_desc}. "
            f"Neither approach is wrong — they simply reflect different preferences. "
            f"Misunderstandings happen when each expects the other to see things the same way."
        )

    user_desc = _get_type_description(dimension, user_type)
    partner_desc = _get_type_description(dimension, partner_type)

    return template.format(
        user_name=user_name,
        partner_name=partner_name,
        user_desc_short=user_desc,
        partner_desc_short=partner_desc,
    )


def personalize_action_steps(
    steps: List[str],
    user_name: str,
    partner_name: str,
) -> List[str]:
    """
    Replace generic partner references with actual names in action steps.
    """
    personalized = []
    for step in steps:
        result = step
        for pattern, replacement in _GENERIC_PATTERNS:
            resolved = replacement.format(user_name=user_name, partner_name=partner_name)
            result = re.sub(pattern, resolved, result)
        personalized.append(result)
    return personalized


def build_expected_outcome(dimension: str, severity: str) -> str:
    """
    Generate an expected outcome statement based on dimension and severity.
    """
    dim_outcomes = EXPECTED_OUTCOMES.get(dimension)
    if dim_outcomes:
        return dim_outcomes.get(severity, dim_outcomes.get("medium", ""))

    return GENERIC_OUTCOME.get(severity, GENERIC_OUTCOME["medium"])


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_type_description(dimension: str, user_type: str) -> str:
    """Get the plain-English description for a type, or a sensible fallback."""
    dim_types = TYPE_DESCRIPTIONS.get(dimension, {})
    desc = dim_types.get(user_type)
    if desc:
        return desc
    # Fallback: humanize the type key
    return f"has a {user_type.replace('_', ' ')} style"


def _verb_form(description: str) -> str:
    """Strip leading verb helpers for 'both X and Y tend to...' phrasing."""
    # If description starts with common prefixes, strip for verb form
    for prefix in ("feels ", "tends to ", "prefers to ", "values ", "is "):
        if description.startswith(prefix):
            return description
    return description
