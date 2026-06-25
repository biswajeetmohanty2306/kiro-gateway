# -*- coding: utf-8 -*-
"""RelateAI Wisdom Library (F8E.7).

A collection of short, memorable reflections that give RelateAI its own
voice and personality. These are selected contextually and placed at the
end of coaching plans as a "one thought to carry with you" moment.

No scoring. No I/O. Pure content selection.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Wisdom entries by category
# ─────────────────────────────────────────────────────────────────────────────

WISDOM: Dict[str, List[str]] = {
    "attachment": [
        "Sometimes reassurance isn't asking for perfect words. It's simply asking to know we still matter.",
        "Needing closeness isn't weakness. Needing space isn't coldness. Both are just ways of feeling safe.",
        "The most secure thing a partner can say is: 'I'm not going anywhere — and you can take your time.'",
        "Distance doesn't always mean disconnection. Sometimes it means someone is finding their way back.",
        "Trust isn't built in grand gestures. It's built in small returns — coming back when you said you would.",
        "You don't have to understand why your partner needs what they need. You just have to believe them when they tell you.",
        "Two people reaching for safety in different directions can still end up in the same place — if they're patient enough.",
    ],
    "communication": [
        "The goal isn't speaking perfectly. The goal is helping the other person feel understood.",
        "Most arguments aren't about who's right. They're about who feels heard.",
        "Sometimes the bravest thing you can say is: 'I don't know how to explain this yet, but it matters to me.'",
        "Listening isn't waiting to respond. It's being genuinely curious about what your partner means.",
        "The question 'Do you want me to listen or help you solve this?' can prevent more fights than any apology.",
        "Clear doesn't have to mean harsh. Gentle doesn't have to mean unclear. You can be both.",
        "When someone says 'you don't understand,' they usually mean 'I don't feel heard yet.'",
    ],
    "conflict": [
        "Winning an argument often ends the conversation. Understanding each other begins a new one.",
        "Conflict isn't the enemy of love. Contempt is. As long as you fight with respect, you're still on the same team.",
        "Sometimes the hardest sentence is: 'You might be right about that.' And sometimes it changes everything.",
        "Silence after an argument doesn't mean the issue is resolved. It means someone is still carrying it alone.",
        "The goal of a disagreement isn't agreement. It's understanding why it matters so much to the other person.",
        "Repair matters more than prevention. Every couple fights. Healthy couples come back to each other afterward.",
        "Walking away isn't abandonment when you say: 'I need twenty minutes and then I'm coming back to you.'",
    ],
    "love_language": [
        "Love isn't only about what we give. It's also about learning how the other person receives it.",
        "Effort is invisible when it's in the wrong language. A full day of care can go unnoticed if it doesn't land where your partner actually feels it.",
        "You don't love someone the way you want to love them. You love them the way they need to be loved.",
        "Small daily deposits of love — in the right language — compound into something remarkable over time.",
        "It's not about doing more. It's about doing differently. Five minutes in the right language beats five hours in the wrong one.",
    ],
    "financial": [
        "Money conversations rarely begin with numbers. They usually begin with values.",
        "Financial peace in a relationship isn't about having the same instincts. It's about respecting each other's fears.",
        "A saver isn't controlling. A spender isn't irresponsible. They're both trying to feel safe — through different strategies.",
        "The most important money conversation isn't 'What can we afford?' It's 'What does financial safety mean to each of us?'",
        "Freedom and security aren't opposites. They're both possible — when you design the structure together.",
    ],
    "lifestyle": [
        "You don't have to love the same things. You have to love each other enough to show up for them.",
        "A relationship doesn't need two identical people. It needs two people who respect each other's rhythm.",
        "Adventure and rest are both forms of love. One is an invitation. The other is a sanctuary.",
        "The strongest couples aren't those who agree on everything. They're those who make room for each other's energy.",
        "Your partner's preference isn't a rejection of yours. It's just a different way of recharging.",
    ],
    "trust": [
        "Trust isn't given once. It's deposited daily — in small promises kept.",
        "Vulnerability isn't risky because the other person might hurt you. It's risky because they might truly see you. And that's also what makes it powerful.",
        "You earn someone's trust not by being perfect, but by being honest when you're not.",
        "Trust isn't the absence of doubt. It's choosing each other despite it.",
    ],
    "growth": [
        "Healthy relationships aren't built by never making mistakes. They're built by repairing them, again and again.",
        "The couples who last aren't the ones who never struggle. They're the ones who struggle together instead of apart.",
        "Growth in a relationship is rarely linear. Some weeks you'll feel like you've gone backward. That's normal. Keep going.",
        "Every pattern you name together is a pattern that loses power over you.",
        "You don't have to be a different person. You just have to be a slightly more aware version of who you already are.",
    ],
    "patience": [
        "Change takes longer than you think it should. But it's happening — even when you can't see it yet.",
        "The most loving thing you can offer your partner today is patience with who they're becoming.",
        "Progress isn't measured by the absence of old patterns. It's measured by how quickly you notice them.",
        "Consistency matters more than intensity. One small right thing every day beats one perfect week followed by nothing.",
    ],
    "connection": [
        "Intimacy isn't about perfect communication. It's about imperfect people choosing to stay curious about each other.",
        "The most romantic thing in a long relationship isn't passion. It's attention.",
        "Two people who keep choosing each other — even on hard days — are building something most people only wish for.",
        "Connection doesn't require constant closeness. It requires knowing: 'When I reach for you, you'll be there.'",
        "Sometimes love is sitting in the same room, doing different things, and still feeling completely together.",
    ],
    "forgiveness": [
        "Forgiveness isn't saying it didn't matter. It's saying it mattered — and you're choosing to move forward anyway.",
        "Holding onto resentment protects you from hurt. But it also protects you from closeness.",
        "You don't have to forgive all at once. You can forgive in layers — and still ask for things to be different going forward.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Relationship-aware introductions
# ─────────────────────────────────────────────────────────────────────────────

INTRODUCTIONS: Dict[str, str] = {
    "high": (
        "Before we begin — your relationship already has many healthy foundations. "
        "This report isn't here to fix something broken. "
        "It's here to help something good become even stronger. "
        "Even happy couples have misunderstandings. "
        "Small improvements today often become the strongest habits tomorrow."
    ),
    "medium": (
        "Like most couples, you already have real strengths as well as real challenges. "
        "Some of the patterns in this report may feel surprisingly familiar. "
        "That's okay — recognizing a pattern is often the first step toward changing it. "
        "Nothing here is a judgment. Everything here is an invitation."
    ),
    "low": (
        "If things have felt difficult recently — thank you for staying long enough "
        "to complete this together. That alone shows there is something worth understanding. "
        "This report won't solve everything overnight. "
        "But it may help both of you begin different conversations — "
        "the kind that lead somewhere better."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Closing reflections (dimension-aware)
# ─────────────────────────────────────────────────────────────────────────────

CLOSING_REFLECTIONS: Dict[str, str] = {
    "attachment_style": (
        "If both of you keep choosing to come back — even imperfectly, even slowly — "
        "you're building exactly the kind of trust that makes this pattern softer over time."
    ),
    "communication_style": (
        "You don't need to speak the same language perfectly. "
        "You just need to keep translating for each other — "
        "with patience, with humor, and with the belief that the other person means well."
    ),
    "conflict_style": (
        "Every disagreement you navigate without losing respect for each other "
        "is a deposit in your relationship's account. "
        "The goal was never zero conflict. It was always: conflict that brings you closer."
    ),
    "love_language": (
        "The love between you has never been the problem. "
        "It's always been there. "
        "You're simply learning to deliver it in a way the other person can feel."
    ),
    "financial_personality": (
        "Money will always be part of your life together. "
        "The goal isn't eliminating the difference — it's building a structure "
        "that lets both of you feel safe without either one feeling controlled."
    ),
    "lifestyle_type": (
        "You don't need to become the same person. "
        "You need to build a life that has room for both of you — "
        "adventure and stillness, people and quiet, movement and rest."
    ),
    "relationship_archetype": (
        "The way you each show up in this relationship is your strength, not your weakness. "
        "When you learn to honor both styles without feeling threatened, "
        "what once felt like tension becomes balance."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def get_introduction(overall_score: float) -> str:
    """
    Get a relationship-aware introduction based on the overall compatibility score.
    """
    if overall_score >= 80:
        return INTRODUCTIONS["high"]
    elif overall_score >= 50:
        return INTRODUCTIONS["medium"]
    else:
        return INTRODUCTIONS["low"]


def select_wisdom(
    dimension: str,
    severity: str,
    user_id: str = "",
    report_id: str = "",
) -> str:
    """
    Select a contextual wisdom quote.

    Uses a deterministic hash for consistent selection per report,
    but produces variety across different reports/users.
    """
    # Map dimension to primary wisdom category
    category_map = {
        "attachment_style": "attachment",
        "communication_style": "communication",
        "conflict_style": "conflict",
        "love_language": "love_language",
        "financial_personality": "financial",
        "lifestyle_type": "lifestyle",
        "relationship_archetype": "connection",
    }

    category = category_map.get(dimension, "growth")
    entries = WISDOM.get(category, WISDOM["growth"])

    if not entries:
        entries = WISDOM["growth"]

    # Deterministic selection based on content seed (ensures same report = same quote)
    seed = f"{user_id}:{report_id}:{dimension}:{severity}"
    hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    index = hash_val % len(entries)

    return entries[index]


def get_closing_reflection(dimension: str) -> str:
    """Get a dimension-specific closing reflection."""
    return CLOSING_REFLECTIONS.get(
        dimension,
        "If both of you keep choosing curiosity over assumptions, "
        "today's difficult conversations can become tomorrow's strongest foundation."
    )


def build_wisdom_closing(dimension: str, wisdom_quote: str) -> str:
    """
    Build the complete 'one thought to carry with you' section.

    Combines the selected wisdom quote with the dimension-specific closing.
    """
    reflection = get_closing_reflection(dimension)

    return (
        f"{wisdom_quote}\n\n"
        f"{reflection}"
    )
