# -*- coding: utf-8 -*-
"""Coach Personality (F9).

This module doesn't understand relationships. It understands PEOPLE.
It decides HOW to speak — what emotional mode to use, what transitions
feel natural, when to celebrate, when to comfort, when to challenge.

Voice: wise elder sibling, caring mentor, experienced coach.
Never: therapist, professor, chatbot, software.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Emotional Modes
# ─────────────────────────────────────────────────────────────────────────────

MODES = [
    "comfort", "encourage", "normalize", "reframe",
    "guide", "celebrate", "hope", "reflect", "reassure", "challenge",
]


def select_mode(context: str, severity: str, section: str) -> str:
    """
    Choose the emotional mode for a paragraph based on context.

    This is the coach's internal question: "What does this person need
    to hear right now?"
    """
    # Section-based defaults
    section_modes = {
        "opening": "normalize",
        "validation": "comfort",
        "why": "reframe",
        "user_action": "guide",
        "partner_action": "guide",
        "together": "encourage",
        "mistakes": "reassure",
        "challenge": "challenge",
        "first_step": "encourage",
        "hope": "hope",
        "outcome": "hope",
        "closing": "reflect",
    }

    # Severity adjustments
    if severity == "high":
        if section in ("opening", "validation"):
            return "comfort"
        if section == "hope":
            return "reassure"

    if severity == "low":
        if section == "opening":
            return "celebrate"
        if section == "hope":
            return "encourage"

    return section_modes.get(section, "guide")


# ─────────────────────────────────────────────────────────────────────────────
# Transition Library
# ─────────────────────────────────────────────────────────────────────────────

TRANSITIONS = {
    "to_actions": [
        "Now that we've talked about what's happening, let's look at a few things that usually help.",
        "With that understanding in mind, here are some ideas worth trying.",
        "So what can you actually do with this? Here's what tends to work.",
        "Understanding the pattern is the first step. Here's the next one.",
    ],
    "to_challenge": [
        "Rather than changing everything at once, I'd like you to try one small experiment this week.",
        "Here's something concrete to practice this week — just one thing.",
        "This week, try this. It's small enough to be easy, but meaningful enough to notice.",
        "One experiment for the week ahead. That's all.",
    ],
    "to_outcome": [
        "If you both practice this consistently, here's what I'd expect to change.",
        "Here's what to watch for over the coming weeks.",
        "Give it a few weeks of honest effort, and here's what usually shifts.",
        "Progress won't be perfectly linear — but here's what to look for.",
    ],
    "to_closing": [
        "One last thought before you go.",
        "I'll leave you with this.",
        "Before you close this, one thing worth remembering.",
        "Something to carry with you.",
    ],
}


def get_transition(target: str, seed: str = "") -> str:
    """Get a natural transition phrase. Varies based on seed for diversity."""
    options = TRANSITIONS.get(target, TRANSITIONS["to_actions"])
    index = _hash_index(seed + target, len(options))
    return options[index]


# ─────────────────────────────────────────────────────────────────────────────
# Celebration Library
# ─────────────────────────────────────────────────────────────────────────────

CELEBRATIONS = [
    "The fact that you're reading this together already says something hopeful.",
    "I'm glad neither of you has stopped trying.",
    "There's already something worth protecting here.",
    "Relationships improve because people stay curious — not because they're perfect.",
    "You're both still choosing each other. That matters more than you think.",
    "The willingness to understand is itself an act of love.",
    "Most couples never get this far. You're already ahead.",
]


def get_celebration(seed: str = "") -> str:
    """Pick a celebration that fits this couple's report."""
    index = _hash_index(seed + "celebrate", len(CELEBRATIONS))
    return CELEBRATIONS[index]


# ─────────────────────────────────────────────────────────────────────────────
# Reflection Library (gentle questions)
# ─────────────────────────────────────────────────────────────────────────────

REFLECTIONS = {
    "attachment_style": [
        "When was the last time this pattern showed up between you?",
        "Can you remember a recent moment where this happened?",
        "Does any part of this feel especially true right now?",
    ],
    "communication_style": [
        "Think of a recent conversation that felt frustrating. Does this help explain why?",
        "Which part of this sounds most familiar?",
    ],
    "conflict_style": [
        "When was your last disagreement that followed this pattern?",
        "Does this help explain what was really happening underneath?",
    ],
    "love_language": [
        "When did you last feel truly appreciated by each other?",
        "What does your partner do that makes you feel most loved?",
    ],
    "_default": [
        "Does this resonate with what you've been experiencing?",
        "Which part feels most true to your relationship right now?",
    ],
}


def get_reflection(dimension: str, seed: str = "") -> str:
    """Get one gentle reflection question — never interrogative."""
    options = REFLECTIONS.get(dimension, REFLECTIONS["_default"])
    index = _hash_index(seed + "reflect" + dimension, len(options))
    return options[index]


# ─────────────────────────────────────────────────────────────────────────────
# Permission Library (reduce pressure)
# ─────────────────────────────────────────────────────────────────────────────

PERMISSIONS = [
    "You don't have to do all of this. Even trying one idea this week is progress.",
    "You won't get everything right. Nobody does. That's not the goal.",
    "It's okay if this feels uncomfortable at first. New patterns always do.",
    "There's no deadline here. Move at the pace that feels honest.",
    "Some weeks will be better than others. That's completely normal.",
    "If you only manage one thing from this list, that's still something.",
]


def get_permission(seed: str = "") -> str:
    """Offer one pressure-reducing statement."""
    index = _hash_index(seed + "permission", len(PERMISSIONS))
    return PERMISSIONS[index]


# ─────────────────────────────────────────────────────────────────────────────
# Closing Library
# ─────────────────────────────────────────────────────────────────────────────

CLOSINGS = [
    "Take care of each other. That's always more important than winning.",
    "Remember, you're not trying to become perfect partners. You're trying to understand each other a little better than yesterday.",
    "The goal isn't fewer disagreements. The goal is recovering from them more gently.",
    "One conversation won't change a relationship. Hundreds of small conversations will.",
    "You don't have to figure this all out today. Just keep showing up.",
    "The couples who last aren't the ones who never struggle. They're the ones who keep choosing each other anyway.",
    "Be patient with each other. You're both learning.",
    "Every small effort compounds. Trust the process even when you can't see the progress.",
]


def get_closing(seed: str = "") -> str:
    """Get a unique closing thought for this report."""
    index = _hash_index(seed + "closing", len(CLOSINGS))
    return CLOSINGS[index]


# ─────────────────────────────────────────────────────────────────────────────
# Refinement — the public API
# ─────────────────────────────────────────────────────────────────────────────


def refine_paragraph(
    paragraph: str,
    context: str = "",
    emotion: str = "",
    severity: str = "medium",
    dimension: str = "",
    section: str = "",
    seed: str = "",
) -> str:
    """
    Refine a paragraph using coach personality.

    This doesn't rewrite content — it adds personality touches:
    - A mode-appropriate opening if the paragraph starts abruptly
    - A reflection question after explanations
    - A permission statement after action lists
    - Natural transitions between sections

    The paragraph's core meaning is preserved. Only the delivery changes.
    """
    mode = emotion or select_mode(context or section, severity, section)

    # For action sections: add permission at the end
    if section in ("user_action", "partner_action") and mode == "guide":
        return paragraph  # Actions are already well-written by narrative builder

    # For explanation sections: occasionally add a reflection
    if section == "why" and len(paragraph) > 100:
        reflection = get_reflection(dimension, seed)
        return f"{paragraph}\n\n{reflection}"

    # For opening: add celebration for low severity
    if section == "opening" and severity == "low":
        celebration = get_celebration(seed)
        return f"{celebration}\n\n{paragraph}"

    # For closing: use personality closing
    if section == "closing":
        return get_closing(seed)

    return paragraph


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _hash_index(seed: str, length: int) -> int:
    """Deterministic but varied selection based on seed."""
    if length <= 0:
        return 0
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return h % length
