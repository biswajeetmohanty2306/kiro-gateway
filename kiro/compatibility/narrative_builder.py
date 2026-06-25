# -*- coding: utf-8 -*-
"""Narrative Builder (F8E.11).

Converts RelationshipInsight into natural human language.
Every function receives names directly — no role labels ever exist.
No regex. No replacements. Language is generated correctly from the start.

This module speaks. The reasoner understood. Now we express that understanding.
"""

from __future__ import annotations

from .relationship_reasoner import RelationshipInsight
from .wisdom import get_introduction, select_wisdom, get_closing_reflection
from .coach_personality import (
    get_transition,
    get_celebration,
    get_reflection,
    get_permission,
    get_closing,
    refine_paragraph,
)


def build_opening(insight: RelationshipInsight, user_name: str, partner_name: str) -> str:
    """The first thing a coach would say — recognition and normalization."""
    seed = f"{user_name}:{partner_name}:{insight.dimension}"

    # For low severity, lead with celebration
    if insight.severity == "low":
        celebration = get_celebration(seed)
        return (
            f"{celebration}\n\n"
            f"I want to share something I notice about you and {partner_name}.\n\n"
            f"{insight.main_pattern}\n\n"
            f"This isn't something to worry about — "
            f"it's simply something that becomes easier once you both see it clearly."
        )

    # For high severity, lead with comfort
    if insight.severity == "high":
        return (
            f"I want to share something I notice about you and {partner_name}. "
            f"I know this might not be easy to read — but understanding it "
            f"is genuinely the first step toward things feeling different.\n\n"
            f"{insight.main_pattern}\n\n"
            f"This pattern is common, and it responds well to consistent effort. "
            f"Neither of you created it on purpose."
        )

    # Medium — normalize
    return (
        f"I want to share something I notice about you and {partner_name}.\n\n"
        f"{insight.main_pattern}\n\n"
        f"This isn't unusual. Many couples experience something similar. "
        f"What matters is that you're both here, trying to understand it."
    )


def build_validation(insight: RelationshipInsight, user_name: str, partner_name: str) -> str:
    """Disarm defensiveness before giving any advice."""
    return (
        f"Here's what's important to understand:\n\n"
        f"{user_name} needs {insight.user_need.lower()}.\n"
        f"{partner_name} needs {insight.partner_need.lower()}.\n\n"
        f"Neither need is wrong. Neither need is excessive. "
        f"They're both completely valid ways of seeking safety and connection. "
        f"The friction isn't about someone being too much or too little — "
        f"it's about two real needs colliding in moments when both of you "
        f"are just trying to feel okay."
    )


def build_feelings(insight: RelationshipInsight, user_name: str, partner_name: str) -> dict:
    """What each person may be experiencing underneath the surface."""
    return {
        "user": [
            insight.user_hidden_fear,
            f"Wanting {insight.user_need.lower()}",
            insight.user_hidden_strength,
        ],
        "partner": [
            insight.partner_hidden_fear,
            f"Wanting {insight.partner_need.lower()}",
            insight.partner_hidden_strength,
        ],
    }


def build_why(insight: RelationshipInsight, user_name: str, partner_name: str) -> str:
    """Explain the mechanism simply — why this keeps happening."""
    seed = f"{user_name}:{partner_name}:{insight.dimension}:why"
    reflection = get_reflection(insight.dimension, seed)

    return (
        f"{insight.conflict_trigger}.\n\n"
        f"{insight.why_it_escalates}\n\n"
        f"Neither of you is doing this on purpose. "
        f"It's an automatic response — and automatic responses can be changed "
        f"once you both see them clearly.\n\n"
        f"{reflection}"
    )


def build_user_guidance(
    insight: RelationshipInsight, user_name: str, partner_name: str
) -> list:
    """Specific, empathetic guidance for the user — explains WHY before WHAT."""

    if insight.dimension == "attachment_style":
        if "reaches" in insight.main_pattern and user_name in insight.main_pattern.split("reaches")[0]:
            # User is the one who reaches out (anxious-type behavior)
            return [
                (
                    f"{user_name}, when you feel the urge to send a follow-up message or check in again, "
                    f"try pausing for just five minutes first.\n\n"
                    f"During that pause, ask yourself one question: "
                    f"'What do I actually need right now?'\n\n"
                    f"Often the need is simpler than the anxiety makes it feel. "
                    f"And that five-minute pause gives {partner_name} the breathing room "
                    f"that makes them more likely to come to you naturally."
                ),
                (
                    f"Find one calming activity that works for you — a short walk, "
                    f"a few deep breaths, a song you love — and practice it at least once "
                    f"a day, even when you're not feeling activated.\n\n"
                    f"Building that muscle when things are calm makes it available "
                    f"when things feel urgent."
                ),
                (
                    f"When {partner_name} takes space, try telling yourself: "
                    f"'Space is not rejection. They're finding their way back.'\n\n"
                    f"This simple reminder can interrupt the spiral before it begins."
                ),
            ]
        else:
            # User is the one who needs space (avoidant-type behavior)
            return [
                (
                    f"{user_name}, when you need space, say it in one short sentence "
                    f"with a specific return time: 'I need thirty minutes — I'll come "
                    f"find you at seven.'\n\n"
                    f"This one sentence transforms your withdrawal from something "
                    f"that feels like abandonment into something that feels like "
                    f"a bounded pause. It costs you nothing — and it changes everything "
                    f"for {partner_name}."
                ),
                (
                    f"Try initiating one small moment of connection each day — "
                    f"without being asked. A touch. A message. Sitting nearby.\n\n"
                    f"When you're the one who reaches out first, it breaks the pattern "
                    f"where only {partner_name} is reaching. That single shift carries "
                    f"enormous weight."
                ),
                (
                    f"When {partner_name} reaches out and the timing isn't ideal, "
                    f"acknowledge before withdrawing: 'I hear you — give me twenty "
                    f"minutes and I'm all yours.'\n\n"
                    f"Acknowledgment is not engagement. It's just letting them know "
                    f"you haven't disappeared."
                ),
            ]

    # Fallback for other dimensions (not yet migrated)
    return [
        f"{user_name}, the most helpful thing you can do this week is simply "
        f"notice when the pattern starts — without trying to fix it immediately. "
        f"Awareness comes before change."
    ]


def build_partner_guidance(
    insight: RelationshipInsight, user_name: str, partner_name: str
) -> list:
    """Specific, empathetic guidance for the partner."""

    if insight.dimension == "attachment_style":
        if "reaches" in insight.main_pattern and user_name in insight.main_pattern.split("reaches")[0]:
            # Partner is the one who needs space
            return [
                (
                    f"{partner_name}, when you need space, say it in one short sentence "
                    f"with a return time: 'I need thirty minutes — I'll be back at seven.'\n\n"
                    f"Then actually return. That follow-through builds more trust than "
                    f"any words could."
                ),
                (
                    f"Try reaching out to {user_name} once a day — even something small. "
                    f"A message. A touch. A moment of eye contact.\n\n"
                    f"When you're the one who initiates, it tells {user_name}'s nervous "
                    f"system: 'You don't have to chase. I'm coming to you.'"
                ),
                (
                    f"When {user_name} reaches out and the timing feels off, "
                    f"try acknowledging before stepping back: "
                    f"'I hear you. Give me a moment and I'm yours.'\n\n"
                    f"That acknowledgment prevents the spiral."
                ),
            ]
        else:
            # Partner is the one reaching (anxious-type)
            return [
                (
                    f"{partner_name}, when worry shows up and you want to reach out, "
                    f"try pausing for five minutes first.\n\n"
                    f"Ask yourself: 'What do I actually need right now?'\n\n"
                    f"That pause creates space for {user_name} to come to you naturally."
                ),
                (
                    f"Build one personal calming practice — something that works for you "
                    f"specifically. Use it daily, even when things feel fine.\n\n"
                    f"When the anxious moment arrives, you'll already have the muscle."
                ),
            ]

    return [
        f"{partner_name}, notice when the pattern starts this week. "
        f"You don't have to change anything yet — just observe."
    ]


def build_together_guidance(
    insight: RelationshipInsight, user_name: str, partner_name: str
) -> list:
    """What they can do as a team — rituals and shared agreements."""

    if insight.dimension == "attachment_style":
        return [
            (
                f"Choose one time each evening — the same time, every day — "
                f"and sit together for ten minutes.\n\n"
                f"No phones. No problem-solving. Just: 'How was your day?' "
                f"and 'What do you appreciate about me today?'\n\n"
                f"This gives {user_name} predictable connection. "
                f"It gives {partner_name} a bounded commitment. "
                f"Both of you get what you need in one simple ritual."
            ),
            (
                f"Create a shared signal for when the pattern starts: "
                f"something like 'We're doing the thing again.'\n\n"
                f"Naming it together — without blame — takes away its power. "
                f"It becomes something you notice rather than something that controls you."
            ),
        ]

    return [
        f"This week, sit together for ten minutes and share one thing "
        f"you each noticed about this pattern. No fixing — just noticing together."
    ]


def build_weekly_challenge(
    insight: RelationshipInsight, user_name: str, partner_name: str
) -> dict:
    """A concrete, trackable challenge for this week."""

    if insight.dimension == "attachment_style":
        return {
            "name": "The Evening Anchor",
            "description": (
                f"Every evening at your agreed time, sit together for ten minutes. "
                f"Each share one thing from your day and one thing you appreciate "
                f"about the other. No problem-solving — just listening and acknowledging.\n\n"
                f"This single ritual addresses both needs at once: "
                f"{user_name} gets reliable connection, "
                f"{partner_name} gets a defined boundary."
            ),
            "duration": "10 minutes per day",
            "frequency": "Every evening",
            "success_criteria": "Complete the check-in at least 5 out of 7 days",
            "tracking": "A simple checkmark on your phone calendar each day you complete it",
        }

    return {
        "name": "The Pattern Notice",
        "description": "This week, simply notice when the pattern appears. Don't try to fix it yet — just observe.",
        "duration": "5 minutes reflection",
        "frequency": "Daily",
        "success_criteria": "Notice the pattern at least 3 times this week",
        "tracking": "A brief note in your phone when you notice it happening",
    }


def build_first_step(
    insight: RelationshipInsight, user_name: str, partner_name: str
) -> dict:
    """One tiny thing they can do right now — under 5 minutes."""

    if insight.dimension == "attachment_style":
        return {
            "user_action": (
                f"Send {partner_name} one short message right now — something you "
                f"genuinely appreciate about them. Keep it to one sentence. "
                f"Don't ask for a reply."
            ),
            "partner_action": (
                f"When you see the message, reply with one thing you appreciate "
                f"about {user_name}. Keep it equally simple."
            ),
            "time_required": "2 minutes",
            "why_it_works": (
                "It creates one micro-moment of positive connection "
                "without any pressure to perform or respond at length."
            ),
        }

    return {
        "user_action": f"Tell {partner_name} one specific thing you noticed and appreciated today.",
        "partner_action": f"Respond with one thing you appreciate about {user_name}.",
        "time_required": "2 minutes",
        "why_it_works": "Starting with appreciation creates emotional safety.",
    }


def build_closing(
    insight: RelationshipInsight, user_name: str, partner_name: str,
    wisdom_quote: str,
) -> str:
    """The final thought — what they carry with them after closing the report."""
    seed = f"{user_name}:{partner_name}:{insight.dimension}:close"
    personality_close = get_closing(seed)
    reflection = get_closing_reflection(insight.dimension)

    return f"{wisdom_quote}\n\n{reflection}\n\n{personality_close}"
