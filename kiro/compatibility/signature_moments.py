# -*- coding: utf-8 -*-
"""Signature Moments (RXD-3).

Creates the moments users remember after they close the app.
Every function here produces content that feels handwritten,
not generated. Warm. Observant. Compassionate. Never dramatic.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1: Relationship Reflection templates
# ─────────────────────────────────────────────────────────────────────────────

_REFLECTIONS: Dict[str, Dict[str, str]] = {
    "attachment_style": {
        "high": (
            "The first thing that stood out wasn't your differences — "
            "it was how much both of you seem to care, even if you show it in opposite ways. "
            "{user_name} reaches toward connection. {partner_name} reaches toward calm. "
            "Both of those instincts come from the same place: wanting the relationship to be okay.\n\n"
            "Your strength is that neither of you has given up trying. "
            "The pattern between you is strong — but so is the care underneath it. "
            "The opportunity here is learning to signal safety to each other in ways that actually land. "
            "When that happens, the urgency softens on both sides.\n\n"
            "Couples with your pattern often surprise themselves by how quickly things shift "
            "once they find a daily rhythm they can both count on."
        ),
        "medium": (
            "Looking at both of your answers, something interesting emerged. "
            "You both value the relationship — but you each protect it differently. "
            "One of you leans in. The other steps back. "
            "Neither approach is wrong. They're just different strategies for feeling safe.\n\n"
            "What's already working: you're both engaged enough to be here. "
            "The growth edge is finding a signal system — a way to say 'I need a moment' "
            "that doesn't feel like 'I'm leaving.' Small adjustments there tend to make a real difference."
        ),
        "low": (
            "Here's what I see between {user_name} and {partner_name}: "
            "a relationship with genuine warmth at its center. "
            "The differences between you are real but manageable — "
            "and you already handle most of them well.\n\n"
            "The opportunity isn't to fix something broken. "
            "It's to make something good even more intentional. "
            "Sometimes the happiest couples benefit most from small refinements "
            "because they have the foundation to build on."
        ),
    },
    "communication_style": {
        "high": (
            "As I looked at both of your answers, one thing stood out almost immediately: "
            "you're both trying to connect — but your conversations keep landing differently "
            "than either of you intends.\n\n"
            "{user_name} communicates one way. {partner_name} communicates another. "
            "The love is there in both directions. What's missing is translation.\n\n"
            "The encouraging thing about communication differences is that they respond faster "
            "to awareness than almost any other pattern. Once you both see the gap, "
            "bridging it often feels surprisingly natural."
        ),
        "medium": (
            "Something I noticed: both of you have been expressing care — "
            "just in slightly different languages. "
            "The frustration you may sometimes feel isn't about lack of effort. "
            "It's about delivery.\n\n"
            "Your strength: genuine intention on both sides. "
            "The growth opportunity: learning to translate rather than repeat louder."
        ),
        "low": (
            "You two communicate well. Not perfectly — nobody does — "
            "but with enough mutual respect that most conversations reach understanding eventually.\n\n"
            "The small refinements below aren't about fixing a problem. "
            "They're about making good conversations even more consistent."
        ),
    },
    "conflict_style": {
        "high": (
            "I want to be honest about something: "
            "the pattern I see in how you handle disagreements is one of the more challenging ones. "
            "Not because either of you is doing something wrong — "
            "but because your instincts in conflict pull you in opposite directions.\n\n"
            "Here's what gives me confidence: "
            "the most important predictor of improvement isn't how you fight. "
            "It's whether both people are willing to try something different. "
            "And both of you are here."
        ),
        "medium": (
            "Your disagreements probably follow a pattern — "
            "one you've both noticed but haven't been able to change yet.\n\n"
            "The good news: conflict patterns respond well to structure. "
            "Not more willpower. Not more self-control. Just clearer agreements about "
            "how you'll handle things when the temperature rises."
        ),
        "low": (
            "Your conflict style is genuinely healthy. You may disagree — all couples do — "
            "but you navigate it without losing respect for each other.\n\n"
            "The suggestions below are refinements, not repairs."
        ),
    },
}

_GENERIC_REFLECTION = (
    "After looking at both of your answers carefully, "
    "something became clear: this relationship has real strengths "
    "alongside real challenges. That's not unusual — it's human.\n\n"
    "What stands out most is that both {user_name} and {partner_name} "
    "are invested. You wouldn't be here otherwise. "
    "The patterns below are opportunities, not verdicts. "
    "Take them one at a time."
)


def generate_reflection(
    dimension: str, severity: str,
    user_name: str, partner_name: str,
    seed: str = "",
) -> str:
    """Generate the personalized relationship reflection."""
    dim_reflections = _REFLECTIONS.get(dimension, {})
    template = dim_reflections.get(severity, _GENERIC_REFLECTION)
    return template.format(user_name=user_name, partner_name=partner_name)


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2: Signature Closings
# ─────────────────────────────────────────────────────────────────────────────

CLOSINGS = [
    "Understanding doesn't solve every problem. But it changes how two people face those problems together.",
    "Relationships rarely change overnight. They usually change one conversation at a time.",
    "The goal isn't to become perfect partners. It's to become partners who understand each other a little better than yesterday.",
    "The strongest relationships aren't the ones without friction. They're the ones that repair it gently.",
    "What you choose to do with this understanding matters more than the understanding itself.",
    "Progress isn't always visible day to day. But it compounds quietly in the background.",
    "Two people who keep choosing curiosity over assumptions are building something rare.",
    "You don't have to agree on everything. You just have to keep trying to understand.",
    "Love rarely fails because of differences. It fails when people stop being curious about each other.",
    "The conversations you have this week matter more than any score.",
]


def get_signature_closing(seed: str = "") -> str:
    """Select one unique closing for this report."""
    return CLOSINGS[_hash(seed + "closing") % len(CLOSINGS)]


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3: Today's Reflection Question
# ─────────────────────────────────────────────────────────────────────────────

REFLECTION_QUESTIONS: Dict[str, List[str]] = {
    "attachment_style": [
        "What part of today's report felt most familiar?",
        "When was the last time you both felt completely at ease together?",
    ],
    "communication_style": [
        "Which suggestion feels easiest to try this week?",
        "What do you think your partner would say after reading this?",
    ],
    "conflict_style": [
        "What usually happens in the first thirty seconds of a disagreement between you?",
        "Which part of this felt most true?",
    ],
    "_default": [
        "What part of today's report felt most familiar?",
        "What do you think your partner would say after reading this?",
        "Which suggestion feels easiest to try this week?",
        "What's one thing you'd like to understand better about each other?",
    ],
}


def get_reflection_question(dimension: str, seed: str = "") -> str:
    """Get one gentle reflection question."""
    options = REFLECTION_QUESTIONS.get(dimension, REFLECTION_QUESTIONS["_default"])
    return options[_hash(seed + "question" + dimension) % len(options)]


# ─────────────────────────────────────────────────────────────────────────────
# Feature 4: Tiny Next Step
# ─────────────────────────────────────────────────────────────────────────────

NEXT_STEPS: Dict[str, List[str]] = {
    "attachment_style": [
        "Before today ends, tell your partner one thing you appreciated about them this week.",
        "Tonight, sit together for five minutes without phones and ask: 'How are you feeling about us?'",
    ],
    "communication_style": [
        "The next time you share something important, start with: 'I need you to listen' or 'I need your help solving this.'",
        "Before bed tonight, tell your partner one specific thing they said today that meant something to you.",
    ],
    "conflict_style": [
        "The next time tension rises, try saying one sentence before anything else: 'I want to understand your side.'",
        "Tonight, ask your partner: 'Is there anything small that's been on your mind lately?' Then just listen.",
    ],
    "_default": [
        "Before today ends, tell your partner one specific thing you appreciated about them.",
        "Spend five minutes together without phones and ask how each of you has been feeling.",
        "Tonight, ask your partner: 'What made you feel most supported recently?' Then just listen.",
    ],
}


def get_tiny_next_step(dimension: str, seed: str = "") -> str:
    """Get one actionable step that takes under 5 minutes."""
    options = NEXT_STEPS.get(dimension, NEXT_STEPS["_default"])
    return options[_hash(seed + "nextstep" + dimension) % len(options)]


# ─────────────────────────────────────────────────────────────────────────────
# Feature 5: Rememberable Quotes (50 originals)
# ─────────────────────────────────────────────────────────────────────────────

QUOTES = [
    "Curiosity is often a better starting point than certainty.",
    "Feeling heard is sometimes more healing than being agreed with.",
    "The strongest relationships aren't conflict-free. They're repair-rich.",
    "The words people choose often hide the feelings they struggle to express.",
    "Most arguments aren't about the topic. They're about whether both people feel seen.",
    "Love doesn't require understanding everything. It requires trying to.",
    "The gap between intention and impact is where most misunderstandings live.",
    "Two people reaching for safety in different directions can still meet in the middle.",
    "Silence between partners isn't always empty. Sometimes it's full of things neither knows how to say.",
    "The most powerful thing you can say to someone you love is: 'Tell me more about that.'",
    "Connection isn't about agreeing. It's about caring enough to stay curious.",
    "Small repairs matter more than grand gestures.",
    "The person you love is not the person you fully understand. They're the person you keep trying to understand.",
    "Patience with someone you love is never wasted.",
    "A good relationship isn't one without problems. It's one where both people show up to face them.",
    "Change happens in the moments when you choose differently than you usually would.",
    "Understanding your partner doesn't mean you have to agree with them.",
    "The goal isn't to stop having difficult conversations. It's to have them more gently.",
    "What your partner needs most from you is probably simpler than you think.",
    "Trust isn't built in one moment. It's built in hundreds of small ones.",
    "The difference between a good week and a hard week is often just one honest conversation.",
    "Your partner is not a puzzle to solve. They're a person to understand.",
    "Love is patient partly because change is slow.",
    "The courage to be vulnerable is almost always rewarded — eventually.",
    "Every couple has a pattern. The aware ones name it. The strong ones navigate it together.",
    "Being right rarely makes someone feel close to you.",
    "When you're both struggling, remember: you're on the same team.",
    "Growth looks different for every couple. Compare yours only to your past selves.",
    "Sometimes the kindest thing you can do is simply stay present.",
    "A relationship doesn't need two identical people. It needs two people willing to learn.",
    "What matters isn't how you got into the pattern. It's whether you're willing to try something different.",
    "Hope in a relationship doesn't require certainty. It only requires willingness.",
    "The conversations you avoid often carry the most potential.",
    "Gentleness is not weakness. In relationships, it's often the strongest choice.",
    "You don't have to fix everything today. You just have to show up honestly.",
    "The way you listen to someone often tells them more than what you say back.",
    "A shared understanding is worth more than a thousand solved arguments.",
    "Sometimes progress is simply noticing the old pattern earlier than before.",
    "The best thing about awareness is that it makes choice possible.",
    "Two people who refuse to give up on understanding each other are building something worth protecting.",
    "Perfection isn't the goal. Presence is.",
    "Most people don't want advice. They want to know someone genuinely listened.",
    "The space between two people grows smaller every time one of them is brave enough to say what's real.",
    "Relationships are built in ordinary moments — not extraordinary ones.",
    "What you practice daily matters more than what you promise occasionally.",
    "Your partner is doing their best with what they understand today.",
    "Every pattern you name together loses a little of its power.",
    "Love is choosing each other again — especially on the days it doesn't come easy.",
    "The couples who last aren't the ones who never struggle. They're the ones who never stop trying.",
    "What you're building together is more important than what you're going through right now.",
]


def get_rememberable_quote(dimension: str, severity: str, seed: str = "") -> str:
    """Select one contextually appropriate quote."""
    return QUOTES[_hash(seed + "quote" + dimension + severity) % len(QUOTES)]


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _hash(seed: str) -> int:
    return int(hashlib.md5(seed.encode()).hexdigest(), 16)
