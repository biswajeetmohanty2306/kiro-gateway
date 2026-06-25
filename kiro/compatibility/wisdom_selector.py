# -*- coding: utf-8 -*-
"""Wisdom Selector (F10).

Less is more. This module chooses ONE or TWO personality touches per report —
never more. Every addition must earn its place by reducing confusion, building
trust, creating hope, or encouraging action.

Voice: an experienced mentor who has spent years helping couples.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Observation Library — "How did RelateAI know that?"
# ─────────────────────────────────────────────────────────────────────────────

OBSERVATIONS: Dict[str, List[str]] = {
    "attachment_style": [
        "I wouldn't be surprised if both of you have walked away from the same conversation feeling misunderstood.",
        "One of you probably believes you're the only one trying. The other may quietly feel exactly the same.",
        "The silence between you isn't empty. It's full of things neither person knows how to say yet.",
        "When one person reaches and the other pulls back — both of you are trying to feel safe. Just in opposite directions.",
    ],
    "communication_style": [
        "It often isn't the words that hurt. It's what those words seem to mean.",
        "You may both be saying 'I love you' — just in languages the other doesn't naturally hear.",
        "The frustration you feel isn't about the topic. It's about not feeling understood while discussing it.",
    ],
    "conflict_style": [
        "Most couples think their arguments are about the subject. They're usually about whether both people feel heard.",
        "The silence after a fight isn't peace. It's just two people carrying the same weight alone.",
        "One of you probably thinks the other doesn't care. The other probably thinks they care too much to risk making it worse.",
    ],
    "love_language": [
        "Both of you have probably done kind things this week that the other didn't notice — not because they're ungrateful, but because it wasn't in their language.",
        "The effort has always been there. It's the translation that's been missing.",
    ],
    "financial_personality": [
        "Money arguments are almost never about money. They're about what money represents — safety for one, freedom for the other.",
        "Both of you are trying to protect the same future. You just disagree about how to get there.",
    ],
    "lifestyle_type": [
        "Neither of you chose how you recharge. It's not a preference you can negotiate away — it's wiring.",
        "The resentment you might feel isn't about the other person's choice. It's about feeling like your own needs don't count.",
    ],
    "relationship_archetype": [
        "The person who needs more togetherness isn't clingy. The person who needs more space isn't cold. You're just calibrated differently.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Analogy Library — short, memorable comparisons
# ─────────────────────────────────────────────────────────────────────────────

ANALOGIES: Dict[str, List[str]] = {
    "attachment_style": [
        "Think of it like two people on a tandem bike — one pedals faster when worried, the other brakes. Neither is wrong. They just need to agree on a pace.",
        "Trust is built like a savings account. Small daily deposits matter more than occasional grand gestures.",
    ],
    "communication_style": [
        "Relationships are a little like learning a new language. Both people may be speaking with love — but in different dialects.",
        "Imagine one person writes emails and the other sends voice notes. Same message, completely different experience for the receiver.",
    ],
    "conflict_style": [
        "Arguments are like fires. One person throws water. The other opens windows. Both are trying to help — both can feel like the other is making it worse.",
        "Think of disagreements as a thermostat. One person's comfortable temperature is the other person's too-hot or too-cold.",
    ],
    "love_language": [
        "Love languages work like currencies. You can be incredibly generous in dollars — but if your partner's economy runs on euros, they won't feel rich.",
    ],
    "financial_personality": [
        "Money in a relationship is like a steering wheel with two hands on it. The issue isn't the destination — it's who's turning and by how much.",
    ],
    "lifestyle_type": [
        "Think of energy like a phone battery. One person charges by going out. The other charges by staying in. Neither is broken — they just have different chargers.",
    ],
    "relationship_archetype": [
        "A relationship is like breathing. It needs both expansion and contraction. Too much togetherness suffocates. Too much independence disconnects.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Hope Library — earned, realistic, never false
# ─────────────────────────────────────────────────────────────────────────────

HOPE: Dict[str, List[str]] = {
    "low": [
        "This is genuinely one of the easiest patterns to shift. A little awareness goes a remarkably long way.",
        "Most couples who understand this difference find it stops causing friction within days.",
    ],
    "medium": [
        "The patterns in your relationship are real — but they're also patterns that respond well to consistent effort.",
        "Couples who commit to small daily practices usually notice meaningful change within two to three weeks.",
        "This isn't about becoming different people. It's about understanding the one you're already with.",
    ],
    "high": [
        "I won't pretend this is easy. But I've seen couples with this exact pattern learn to navigate it — and come out stronger.",
        "The difficulty here is real. So is the possibility of change. Both things are true at the same time.",
        "This pattern takes patience. But the couples who stay with it consistently — even imperfectly — report that something genuinely shifts.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Humility Library — coach acknowledges limits
# ─────────────────────────────────────────────────────────────────────────────

HUMILITY = [
    "If any part of this doesn't feel true for your relationship, keep what helps and leave the rest.",
    "I could be wrong about some of this. You know your relationship better than any assessment can.",
    "Take what resonates. Leave what doesn't. Trust your own experience.",
]


# ─────────────────────────────────────────────────────────────────────────────
# Selection logic — choose ONE or TWO touches, never more
# ─────────────────────────────────────────────────────────────────────────────

def select_wisdom_touches(
    dimension: str,
    severity: str,
    overall_score: float,
    user_id: str = "",
    report_id: str = "",
) -> dict:
    """
    Choose 1–2 personality touches for this report.

    Returns a dict with optional keys:
    - observation: str (insightful "how did they know?" moment)
    - analogy: str (short memorable comparison)
    - hope: str (earned encouragement)
    - humility: str (acknowledge limits)

    NEVER returns all of them. Less is more.
    """
    seed = f"{user_id}:{report_id}:{dimension}:{severity}"
    result = {}

    # Always include ONE primary touch based on severity
    if severity == "high":
        # High severity → observation (validation) + hope (realistic)
        result["observation"] = _pick(OBSERVATIONS.get(dimension, OBSERVATIONS["attachment_style"]), seed + "obs")
        result["hope"] = _pick(HOPE["high"], seed + "hope")
    elif severity == "low":
        # Low severity → analogy (light) only
        result["analogy"] = _pick(ANALOGIES.get(dimension, ANALOGIES["attachment_style"]), seed + "ana")
    else:
        # Medium → observation OR analogy (not both)
        choice = _hash_int(seed + "choice") % 2
        if choice == 0:
            result["observation"] = _pick(OBSERVATIONS.get(dimension, OBSERVATIONS["attachment_style"]), seed + "obs")
        else:
            result["analogy"] = _pick(ANALOGIES.get(dimension, ANALOGIES["attachment_style"]), seed + "ana")
        result["hope"] = _pick(HOPE["medium"], seed + "hope")

    # Occasionally add humility (20% of reports)
    if _hash_int(seed + "humility") % 5 == 0:
        result["humility"] = _pick(HUMILITY, seed + "hum")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pick(options: List[str], seed: str) -> str:
    """Deterministically pick one option."""
    if not options:
        return ""
    return options[_hash_int(seed) % len(options)]


def _hash_int(seed: str) -> int:
    """Deterministic hash to int."""
    return int(hashlib.md5(seed.encode()).hexdigest(), 16)
