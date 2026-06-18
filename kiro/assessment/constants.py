# -*- coding: utf-8 -*-
"""Assessment scoring constants (F2B).

Tie-break priority orders and dimension configuration.
"""

from __future__ import annotations

# Tie-break priority: when sub-scales are tied, the first in this list wins.
TIE_BREAK_ORDER: dict[str, list[str]] = {
    "attachment_style": ["secure", "anxious", "avoidant", "fearful_avoidant"],
    "communication_style": ["direct", "diplomatic", "analytical", "expressive"],
    "conflict_style": ["collaborative", "compromising", "avoiding", "competing"],
    "love_language": ["words", "acts", "gifts", "touch", "time"],
    "financial_personality": ["saver", "investor", "balanced", "spender"],
    "lifestyle_type": ["adventurous", "social", "balanced", "homebody"],
    "relationship_archetype": ["partner", "nurturer", "independent", "explorer"],
}

# The Love Language dimension uses count-based scoring, not weighted-sum.
LOVE_LANGUAGE_CATEGORY = "love_language"

# All valid love language keys.
LOVE_LANGUAGE_KEYS = ["words", "acts", "gifts", "touch", "time"]

# Number of Love Language questions (used for normalization).
LOVE_LANGUAGE_QUESTION_COUNT = 10
