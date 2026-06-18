# -*- coding: utf-8 -*-
"""Type metadata for profile display (F3).

Static data: labels, descriptions, dimension display names.
These are computed at response time, not stored in the database.
"""

from __future__ import annotations

# --- Dimension display names ---

DIMENSION_DISPLAY_NAMES: dict[str, str] = {
    "attachment_style": "Attachment Style",
    "communication_style": "Communication Style",
    "conflict_style": "Conflict Style",
    "love_language": "Love Language",
    "financial_personality": "Financial Personality",
    "lifestyle_type": "Lifestyle Type",
    "relationship_archetype": "Relationship Archetype",
}

# Presentation order (fixed)
DIMENSION_ORDER: list[str] = [
    "attachment_style",
    "communication_style",
    "conflict_style",
    "love_language",
    "financial_personality",
    "lifestyle_type",
    "relationship_archetype",
]

# --- Type labels (human-readable) ---

TYPE_LABELS: dict[str, dict[str, str]] = {
    "attachment_style": {
        "secure": "Secure",
        "anxious": "Anxious",
        "avoidant": "Avoidant",
        "fearful_avoidant": "Fearful-Avoidant",
    },
    "communication_style": {
        "direct": "Direct",
        "diplomatic": "Diplomatic",
        "analytical": "Analytical",
        "expressive": "Expressive",
    },
    "conflict_style": {
        "collaborative": "Collaborative",
        "compromising": "Compromising",
        "avoiding": "Avoiding",
        "competing": "Competing",
    },
    "love_language": {
        "words": "Words of Affirmation",
        "acts": "Acts of Service",
        "gifts": "Receiving Gifts",
        "touch": "Physical Touch",
        "time": "Quality Time",
    },
    "financial_personality": {
        "saver": "Saver",
        "spender": "Spender",
        "investor": "Investor",
        "balanced": "Balanced",
    },
    "lifestyle_type": {
        "adventurous": "Adventurous",
        "homebody": "Homebody",
        "balanced": "Balanced",
        "social": "Social",
    },
    "relationship_archetype": {
        "partner": "Partner",
        "independent": "Independent",
        "nurturer": "Nurturer",
        "explorer": "Explorer",
    },
}

# --- Type descriptions (one sentence each) ---

TYPE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "attachment_style": {
        "secure": "You're comfortable with emotional closeness and give space naturally.",
        "anxious": "You value deep connection and are attuned to shifts in closeness.",
        "avoidant": "You prize independence and process emotions through space and self-reliance.",
        "fearful_avoidant": "You desire closeness but approach it with caution, balancing vulnerability and self-protection.",
    },
    "communication_style": {
        "direct": "You say what you mean and value clarity over cushioning.",
        "diplomatic": "You consider others' feelings and value harmony in how you communicate.",
        "analytical": "You think before speaking and prioritize logic and thoroughness.",
        "expressive": "You share openly and value emotional connection through words.",
    },
    "conflict_style": {
        "collaborative": "You stay engaged until both people feel heard and satisfied.",
        "compromising": "You value practical fairness and find middle ground efficiently.",
        "avoiding": "You need space to process and prefer to revisit when things are calm.",
        "competing": "You stand firmly behind your convictions and bring energy to disagreements.",
    },
    "love_language": {
        "words": "You feel most loved when your partner expresses appreciation verbally.",
        "acts": "You feel most loved when your partner takes action to lighten your load.",
        "gifts": "You feel most loved through thoughtful gestures and symbols of care.",
        "touch": "You feel most loved through physical closeness and affection.",
        "time": "You feel most loved through focused, undivided attention together.",
    },
    "financial_personality": {
        "saver": "You prioritize financial security and find comfort in a solid cushion.",
        "spender": "You see money as a tool for experiences and quality of life.",
        "investor": "You think strategically about growing your resources over time.",
        "balanced": "You take a flexible approach to money without strong pull in any direction.",
    },
    "lifestyle_type": {
        "adventurous": "You're energized by novelty and seek new experiences regularly.",
        "homebody": "You recharge in familiar, comfortable environments you've made your own.",
        "balanced": "You adapt easily between activity and rest depending on your energy.",
        "social": "You're energized by people and thrive with an active social life.",
    },
    "relationship_archetype": {
        "partner": "You find deep meaning in building a shared life and identity together.",
        "independent": "You maintain a rich personal world while choosing to share it with someone.",
        "nurturer": "You find fulfillment in caring for your partner and making their life better.",
        "explorer": "You bring growth, curiosity, and forward momentum into the relationship.",
    },
}


# --- Strength labels ---

def get_strength_label(strength: int) -> str:
    """Map a 0–100 strength score to a human-readable label."""
    if strength >= 76:
        return "Strong"
    elif strength >= 51:
        return "Moderate"
    elif strength >= 26:
        return "Mild"
    else:
        return "Emerging"


def get_type_label(dimension: str, type_key: str) -> str:
    """Get the display label for a type key."""
    return TYPE_LABELS.get(dimension, {}).get(type_key, type_key.replace("_", " ").title())


def get_type_description(dimension: str, type_key: str) -> str:
    """Get the one-sentence description for a type."""
    return TYPE_DESCRIPTIONS.get(dimension, {}).get(type_key, "")
