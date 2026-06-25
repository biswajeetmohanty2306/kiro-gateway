# -*- coding: utf-8 -*-
"""Relationship Reflection (RXD-3.1).

Generates one personalized mentor-style reflection per report.
Speaks equally to both partners. Never uses psychology terminology.
Feels handwritten by someone who genuinely understands people.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List


def generate_reflection(
    overall_score: float,
    user_name: str,
    partner_name: str,
    top_strength_dimension: str = "",
    top_challenge_dimension: str = "",
    seed: str = "",
) -> dict:
    """
    Generate a personalized relationship reflection.

    Returns:
        {"title": str, "reflection": str, "tone": str}
    """
    if overall_score >= 80:
        return _build_high(user_name, partner_name, top_strength_dimension, seed)
    elif overall_score >= 50:
        return _build_medium(user_name, partner_name, top_strength_dimension, top_challenge_dimension, seed)
    else:
        return _build_low(user_name, partner_name, top_challenge_dimension, seed)


# ─────────────────────────────────────────────────────────────────────────────
# High compatibility (80+)
# ─────────────────────────────────────────────────────────────────────────────

_HIGH_TEMPLATES = [
    (
        "The first thing that stood out wasn't what's different between {user_name} and "
        "{partner_name} — it was how much seems to work naturally.\n\n"
        "You've built something most couples wish they had: {strength_obs}. "
        "That doesn't happen by accident. It happens because both of you show up.\n\n"
        "The ideas below aren't here to fix something broken. "
        "They're here to help something already good become even more intentional. "
        "Sometimes the strongest relationships benefit most from small refinements — "
        "because they have the foundation to build on."
    ),
    (
        "After looking at both of your answers, something became clear almost "
        "immediately: there's genuine care running through this relationship.\n\n"
        "{user_name} and {partner_name} don't just tolerate each other's differences — "
        "you've found ways to make them work. {strength_obs}.\n\n"
        "What follows isn't a repair manual. It's a set of small ideas for "
        "making the good parts even more consistent. You already have the hard part covered."
    ),
]

_HIGH_STRENGTHS: Dict[str, str] = {
    "attachment_style": "a sense of safety that lets both of you be yourselves",
    "communication_style": "a way of talking to each other that usually lands well",
    "conflict_style": "an ability to disagree without losing respect for each other",
    "love_language": "a natural awareness of what makes each other feel valued",
    "financial_personality": "an alignment around how you think about money together",
    "lifestyle_type": "a shared rhythm that gives both of you what you need",
    "relationship_archetype": "a balance between togetherness and independence that works",
}


def _build_high(user_name: str, partner_name: str, strength_dim: str, seed: str) -> dict:
    strength_obs = _HIGH_STRENGTHS.get(strength_dim, "a foundation of mutual respect and genuine effort")
    template = _HIGH_TEMPLATES[_h(seed + "high") % len(_HIGH_TEMPLATES)]
    return {
        "title": "What we see in your relationship",
        "reflection": template.format(
            user_name=user_name, partner_name=partner_name, strength_obs=strength_obs
        ),
        "tone": "celebratory",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Medium compatibility (50–79)
# ─────────────────────────────────────────────────────────────────────────────

_MEDIUM_TEMPLATES = [
    (
        "As I looked through both of your answers, one thing stood out: "
        "this relationship has real strengths alongside real challenges. "
        "That's not unusual — it's human.\n\n"
        "What's working: {strength_obs}. That's not nothing. "
        "Many couples never build that.\n\n"
        "Where there's room to grow: {challenge_obs}. "
        "This isn't a verdict — it's an opportunity. "
        "Most couples who understand their pattern find it becomes easier to navigate, "
        "not harder."
    ),
    (
        "Here's what I notice about {user_name} and {partner_name}: "
        "you're both invested. You wouldn't be here otherwise.\n\n"
        "Your relationship already has {strength_obs}. "
        "The area that could use attention is {challenge_obs}.\n\n"
        "That kind of challenge doesn't mean something is wrong with either of you. "
        "It means you approach one area differently — "
        "and understanding that difference is usually the beginning of things getting easier."
    ),
]

_MEDIUM_STRENGTHS: Dict[str, str] = {
    "attachment_style": "a genuine desire to stay connected",
    "communication_style": "a willingness to keep talking even when it's hard",
    "conflict_style": "the ability to care about each other even during disagreements",
    "love_language": "real effort to show love — even if it sometimes gets lost in translation",
    "financial_personality": "shared goals even when you disagree on the details",
    "lifestyle_type": "mutual respect for each other's preferences",
    "relationship_archetype": "genuine investment from both sides",
}

_MEDIUM_CHALLENGES: Dict[str, str] = {
    "attachment_style": "the moments when one of you needs closeness and the other needs space",
    "communication_style": "the gap between what's meant and what's heard",
    "conflict_style": "what happens when tension rises and your instincts pull in different directions",
    "love_language": "making sure the love you're giving actually lands where it needs to",
    "financial_personality": "the emotional weight that money decisions carry for each of you",
    "lifestyle_type": "finding a rhythm that genuinely works for both energy levels",
    "relationship_archetype": "balancing individual needs with shared ones",
}


def _build_medium(user_name: str, partner_name: str, strength_dim: str, challenge_dim: str, seed: str) -> dict:
    strength_obs = _MEDIUM_STRENGTHS.get(strength_dim, "genuine investment from both sides")
    challenge_obs = _MEDIUM_CHALLENGES.get(challenge_dim, "one area where you approach things differently")
    template = _MEDIUM_TEMPLATES[_h(seed + "med") % len(_MEDIUM_TEMPLATES)]
    return {
        "title": "What we see in your relationship",
        "reflection": template.format(
            user_name=user_name, partner_name=partner_name,
            strength_obs=strength_obs, challenge_obs=challenge_obs,
        ),
        "tone": "balanced",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Low compatibility (<50)
# ─────────────────────────────────────────────────────────────────────────────

_LOW_TEMPLATES = [
    (
        "I want to be honest with you: "
        "the patterns I see between {user_name} and {partner_name} suggest "
        "that things have probably felt difficult recently.\n\n"
        "That's hard. And the fact that you're both still here — "
        "still willing to look at this together — says something real about "
        "what exists between you.\n\n"
        "The area that seems to create the most friction is "
        "{challenge_obs}. That doesn't mean your relationship is broken. "
        "It means one part of it needs more attention than it's been getting.\n\n"
        "I can't promise that everything in this report will feel right. "
        "But if it helps you understand even one thing more clearly, "
        "that's a meaningful starting point."
    ),
    (
        "Before we go further, I want to acknowledge something: "
        "relationships that feel challenging take courage to examine.\n\n"
        "The main friction point seems to be {challenge_obs}. "
        "That's a real challenge — I won't minimize it.\n\n"
        "But here's what I also see: neither {user_name} nor {partner_name} "
        "has walked away. That willingness to stay and try to understand "
        "is itself a form of care. Not every couple has that.\n\n"
        "The suggestions below are small steps. Take them one at a time. "
        "Progress here is slow — but it's real when it happens."
    ),
]


def _build_low(user_name: str, partner_name: str, challenge_dim: str, seed: str) -> dict:
    challenge_obs = _MEDIUM_CHALLENGES.get(challenge_dim, "the way tensions build without resolution")
    template = _LOW_TEMPLATES[_h(seed + "low") % len(_LOW_TEMPLATES)]
    return {
        "title": "What we see in your relationship",
        "reflection": template.format(
            user_name=user_name, partner_name=partner_name, challenge_obs=challenge_obs
        ),
        "tone": "gentle",
    }


def _h(seed: str) -> int:
    return int(hashlib.md5(seed.encode()).hexdigest(), 16)
