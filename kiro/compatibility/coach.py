# -*- coding: utf-8 -*-
"""Empathetic coaching layer (F8E Phase 1).

Generates the full 14-section coaching plan from raw compatibility data.
This module is a pure transformation layer — no I/O, no database, no scoring.

The output feels like a trusted relationship coach speaking directly to
two specific people, not a report or diagnosis.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .personalize import (
    _get_type_description,
    build_why_section,
    build_expected_outcome,
    TYPE_DESCRIPTIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: What's Happening Between You
# ─────────────────────────────────────────────────────────────────────────────

WHATS_HAPPENING: Dict[str, Dict[frozenset, str]] = {
    "attachment_style": {
        frozenset({"anxious", "avoidant"}): (
            "There's a pattern between you that you've probably both noticed "
            "but haven't been able to name. {user_name} tends to reach toward "
            "connection — a message, a question, a need to check in. "
            "{partner_name} tends to need a moment to themselves first. "
            "The more {user_name} reaches out, the more {partner_name} needs "
            "quiet. And the more quiet {partner_name} takes, the more "
            "{user_name} reaches out. It's a cycle neither of you created on purpose."
        ),
        frozenset({"avoidant", "avoidant"}): (
            "You've built something peaceful together — low conflict, lots of "
            "respect for each other's independence. But underneath that calm, "
            "there might be important things going unsaid. Feelings that don't "
            "get shared. Needs that don't get voiced. Not because you don't care, "
            "but because neither of you naturally initiates emotional depth."
        ),
    },
}

WHATS_HAPPENING["attachment_style"][frozenset({"anxious", "anxious"})] = (
    "You both feel things deeply when it comes to your connection. "
    "When either of you senses distance — even briefly — worry shows up fast. "
    "The challenge isn't that you don't love each other enough. "
    "It's that you're both looking to each other for reassurance at the same time, "
    "and sometimes neither person has a steady base to offer it from."
)
WHATS_HAPPENING["attachment_style"][frozenset({"fearful_avoidant", "fearful_avoidant"})] = (
    "Your connection has an intensity that can feel wonderful when you're in sync — "
    "but confusing when you're not. Both of you sometimes want closeness and sometimes "
    "need distance, but rarely at the same time. When one reaches out, the other might "
    "be pulling inward. It's not rejection. It's just different timing."
)

WHATS_HAPPENING["communication_style"] = {
    frozenset({"analytical", "expressive"}): (
        "When something comes up between you, {user_name} and {partner_name} process it "
        "through completely different channels. One of you thinks it through with logic "
        "first; the other needs to talk it out with feeling. When {user_name} offers "
        "a solution, {partner_name} might feel unheard. When {partner_name} shares "
        "feelings, {user_name} might feel confused about what to do. You're both trying "
        "to help — just in different languages."
    ),
    frozenset({"direct", "diplomatic"}): (
        "{user_name} says what they mean plainly. {partner_name} wraps messages in "
        "softness. Neither approach is wrong, but it can feel like you're speaking "
        "different languages. {user_name} might seem too blunt sometimes. "
        "{partner_name} might seem unclear. The truth is: you both mean well, "
        "you just deliver it differently."
    ),
    frozenset({"direct", "expressive"}): (
        "{user_name} likes to get to the point. {partner_name} likes to share the full "
        "story with all the emotions attached. When {user_name} wraps up quickly, "
        "{partner_name} can feel cut off. When {partner_name} takes time to get there, "
        "{user_name} can feel stuck in a conversation that doesn't seem to land."
    ),
}

WHATS_HAPPENING["conflict_style"] = {
    frozenset({"avoiding", "competing"}): (
        "When tension arises, you both have strong but opposite instincts. "
        "{partner_name} engages — voice gets louder, energy rises, there's an urgency "
        "to resolve it now. {user_name} retreats — needs quiet, needs space, needs "
        "the temperature to come down before talking. The louder one gets, the "
        "quieter the other becomes. Neither of you is getting what you need."
    ),
    frozenset({"avoiding", "avoiding"}): (
        "You've probably never had a big blowout argument. That might sound nice, "
        "but the flip side is that important things stay buried. Small frustrations "
        "don't get raised. Needs go unspoken. Not because you don't care, but because "
        "neither of you naturally initiates difficult conversations."
    ),
    frozenset({"competing", "competing"}): (
        "When you disagree, both of you fight to be heard. Arguments can feel like "
        "debates where winning matters more than resolving. You're both passionate, "
        "both care deeply — but the intensity can leave you both exhausted and "
        "neither feeling truly understood."
    ),
    frozenset({"avoiding", "collaborative"}): (
        "One of you wants to sit down and work through problems together right now. "
        "The other needs to step away and think first. The one who wants to talk feels "
        "shut out. The one who needs space feels chased. You're both trying to "
        "handle things well — just on completely different timelines."
    ),
}

WHATS_HAPPENING["love_language"] = {
    frozenset({"words", "time"}): (
        "{user_name} shows love through words — compliments, appreciation, verbal "
        "reassurance. {partner_name} shows love through presence — being there, "
        "putting the phone down, giving undivided attention. Both of you are "
        "expressing care every day. The challenge is that each of you gives love "
        "in the way YOU would want to receive it, not the way the other needs it."
    ),
    frozenset({"words", "touch"}): (
        "{user_name} lights up when they hear words of appreciation. "
        "{partner_name} feels most connected through physical closeness. "
        "You're both reaching for each other — one through language, the other "
        "through proximity. The love is there. It just needs a better translator."
    ),
    frozenset({"acts", "gifts"}): (
        "{user_name} shows love by doing helpful things — taking care of tasks, "
        "making life easier. {partner_name} shows love through thoughtful tokens "
        "and surprises. Both approaches are genuine expressions of care. "
        "The friction comes when practical effort feels unromantic, or when "
        "gifts feel unnecessary compared to help."
    ),
}

WHATS_HAPPENING["financial_personality"] = {
    frozenset({"saver", "spender"}): (
        "Money conversations between you probably carry more weight than they should. "
        "{user_name} finds peace in knowing there's money set aside for the future. "
        "{partner_name} finds joy in using money to enjoy life now. Neither of you "
        "is being careless — you just have different emotional relationships with "
        "financial security. Every purchase can feel like a values clash."
    ),
    frozenset({"investor", "spender"}): (
        "{user_name} wants every dollar working toward a goal. "
        "{partner_name} wants to enjoy what you've both earned right now. "
        "The planner feels the spender is careless. The spender feels the planner "
        "is denying them a life worth living. In truth, you both have a point."
    ),
}

WHATS_HAPPENING["lifestyle_type"] = {
    frozenset({"adventurous", "homebody"}): (
        "Every weekend might feel like a quiet negotiation. {user_name} is "
        "energized by getting out — new places, new experiences, movement. "
        "{partner_name} recharges in quiet, comfortable spaces. Neither is wrong. "
        "But without a system, one person always feels like they're compromising."
    ),
    frozenset({"homebody", "social"}): (
        "{partner_name} is energized by people — gatherings, dinners, events. "
        "{user_name} is drained by them and needs quiet to recover. "
        "Free time becomes a tug-of-war between 'let's have people over' "
        "and 'can we just be alone tonight?'"
    ),
}

WHATS_HAPPENING["relationship_archetype"] = {
    frozenset({"independent", "partner"}): (
        "{partner_name} wants a strong shared identity — doing things together, "
        "planning together, being a unit. {user_name} needs room to be themselves — "
        "their own hobbies, their own friends, their own time. "
        "The togetherness person can feel rejected. The independent person can "
        "feel trapped. But underneath, both of you are just trying to be "
        "fully yourselves within this relationship."
    ),
    frozenset({"explorer", "partner"}): (
        "{user_name} is constantly growing — reading, trying new things, evolving. "
        "{partner_name} wants to go deeper into what you already have together. "
        "The explorer can seem restless. The depth partner can seem rigid. "
        "In truth, you bring different gifts to the relationship."
    ),
    frozenset({"independent", "nurturer"}): (
        "{partner_name} shows love through caring — helping, checking in, "
        "anticipating needs. {user_name} values doing things independently. "
        "The nurturer feels rejected when help is declined. The independent "
        "one feels smothered when help is constant. Both mean well."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Real-Life Example Dialogues
# ─────────────────────────────────────────────────────────────────────────────

EXAMPLE_DIALOGUES: Dict[str, Dict[frozenset, dict]] = {
    "attachment_style": {
        frozenset({"anxious", "avoidant"}): {
            "lines": [
                ("user", "Hey, are you upset with me? You've been quiet all evening."),
                ("partner", "No, I just need some time to decompress."),
                ("user", "But when you go quiet I don't know what's happening."),
                ("partner", "I know. When I feel pressured to talk I just shut down more."),
                ("user", "I just need to know we're okay."),
                ("partner", "We are. I just need to get there in my own time."),
            ],
            "closing": (
                "Neither person is trying to hurt the other here. "
                "{user_name} is reaching for reassurance. {partner_name} is reaching for calm. "
                "Both are valid needs — they just collide in moments like this."
            ),
        },
        frozenset({"avoidant", "avoidant"}): {
            "lines": [
                ("user", "How was your day?"),
                ("partner", "Fine. Yours?"),
                ("user", "Fine."),
                ("partner", "..."),
                ("user", "Want to watch something?"),
                ("partner", "Sure."),
            ],
            "closing": (
                "On the surface this looks peaceful. But underneath, "
                "both of you might be wondering: 'Is this all there is?' "
                "The comfort is real — but so is the quiet wish for something deeper."
            ),
        },
    },
    "communication_style": {
        frozenset({"direct", "diplomatic"}): {
            "lines": [
                ("user", "I think we should cancel the dinner with your parents this weekend."),
                ("partner", "Well... I mean, it's just that they've been looking forward to it..."),
                ("user", "Just say what you actually want."),
                ("partner", "I'm trying to! I just... I think maybe we could find a way to make it work?"),
                ("user", "So you want to go. Just say that."),
                ("partner", "Why does everything have to be so black and white with you?"),
            ],
            "closing": (
                "{user_name} is trying to be clear. {partner_name} is trying to be kind. "
                "Both are good intentions that happen to frustrate each other."
            ),
        },
    },
    "conflict_style": {
        frozenset({"avoiding", "competing"}): {
            "lines": [
                ("partner", "We need to talk about what happened yesterday."),
                ("user", "Can we do this later? I'm not ready."),
                ("partner", "You always say later! Later never comes!"),
                ("user", "..."),
                ("partner", "See? You're doing it right now. You just disappear."),
                ("user", "I can't think when you're this intense."),
            ],
            "closing": (
                "{partner_name} isn't trying to overwhelm. {user_name} isn't trying to "
                "dismiss. One needs the conversation to happen. The other needs the "
                "temperature to drop first. Both are legitimate."
            ),
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Feelings by type
# ─────────────────────────────────────────────────────────────────────────────

FEELINGS_BY_TYPE: Dict[tuple, List[str]] = {
    ("attachment_style", "anxious"): [
        "Worried when there's silence — 'Are we okay?'",
        "Hurt when space is taken without explanation",
        "Relieved when connection is reestablished",
        "Frustrated that reaching out sometimes pushes the other away",
    ],
    ("attachment_style", "avoidant"): [
        "Overwhelmed when there's pressure to respond immediately",
        "Guilty for needing space — 'Am I being cold?'",
        "Relieved when given room to come back on their own terms",
        "Frustrated that needing quiet is read as rejection",
    ],
    ("attachment_style", "fearful_avoidant"): [
        "Confused by their own shifting needs — closeness one moment, space the next",
        "Worried that their inconsistency hurts the other person",
        "Relieved in moments of genuine synchronization",
        "Frustrated by the unpredictability of their own feelings",
    ],
    ("attachment_style", "secure"): [
        "Calm in most relational situations",
        "Occasionally confused by a partner's intensity or distance",
        "Patient but sometimes unsure how to help",
        "Wishing the other could relax into the relationship more",
    ],
    ("communication_style", "direct"): [
        "Frustrated when conversations take too long to reach the point",
        "Confused when the other person seems to hint instead of say",
        "Relieved when expectations are stated clearly",
        "Sometimes unaware that their bluntness lands hard",
    ],
    ("communication_style", "diplomatic"): [
        "Hurt when the other person's words feel harsh or abrupt",
        "Anxious about saying something that might cause conflict",
        "Relieved when conversations feel gentle and safe",
        "Frustrated when directness is valued over their carefulness",
    ],
    ("communication_style", "analytical"): [
        "Confused when emotions take over a conversation",
        "Wanting to help but unsure what's needed when feelings are shared",
        "Frustrated when solutions are rejected",
        "Relieved when problems are structured and solvable",
    ],
    ("communication_style", "expressive"): [
        "Unheard when the other person jumps to solutions",
        "Needing to talk through feelings before reaching conclusions",
        "Frustrated when emotional sharing is cut short",
        "Relieved when someone truly listens without fixing",
    ],
    ("conflict_style", "avoiding"): [
        "Overwhelmed when conflict intensity rises",
        "Needing to think before responding — not avoiding forever",
        "Guilty for being unable to engage in the moment",
        "Relieved when things calm down enough to think clearly",
    ],
    ("conflict_style", "competing"): [
        "Urgent need to be heard and understood RIGHT NOW",
        "Frustrated when the other person shuts down",
        "Scared that silence means the issue will never be resolved",
        "Exhausted after intense disagreements",
    ],
    ("conflict_style", "collaborative"): [
        "Wanting to work through things together as a team",
        "Frustrated when the other person won't engage",
        "Optimistic that talking will make things better",
        "Hurt when collaborative efforts are met with withdrawal",
    ],
    ("conflict_style", "compromising"): [
        "Willing to meet halfway on most things",
        "Frustrated when the other person won't bend at all",
        "Relieved when a middle ground is found",
        "Sometimes feeling like they give more than they receive",
    ],
    # Love Language
    ("love_language", "words"): [
        "Lit up by specific compliments — the more detailed, the better",
        "Quietly hurt when effort goes unacknowledged verbally",
        "Needing to hear 'I love you' and 'I appreciate you' to feel secure",
        "Sometimes wondering if the other person notices what they do",
    ],
    ("love_language", "touch"): [
        "Feeling most connected through physical closeness — a hand on the back, a long hug",
        "Noticing when physical affection decreases and wondering why",
        "Craving proximity even when no words are needed",
        "Sometimes feeling rejected when their partner isn't physically affectionate",
    ],
    ("love_language", "time"): [
        "Feeling most loved when they have their partner's undivided attention",
        "Hurt when phones or distractions compete during together-time",
        "Needing presence more than words or gifts",
        "Sometimes feeling invisible when quality time isn't prioritized",
    ],
    ("love_language", "acts"): [
        "Feeling cared for when their partner handles things without being asked",
        "Noticing every small helpful gesture as a sign of love",
        "Frustrated when they carry more of the load alone",
        "Interpreting lack of help as lack of caring — even when that's not true",
    ],
    ("love_language", "gifts"): [
        "Touched deeply by thoughtful tokens — it's about the thought, not the price",
        "Feeling forgotten when occasions pass without acknowledgment",
        "Seeing gifts as proof that someone was thinking about them",
        "Sometimes hurt when practical needs are prioritized over sentimental ones",
    ],
    # Financial
    ("financial_personality", "saver"): [
        "Anxious when spending feels uncontrolled",
        "Finding security in knowing there's money set aside",
        "Frustrated when their partner seems unconcerned about the future",
        "Wanting acknowledgment that their saving protects both of them",
    ],
    ("financial_personality", "spender"): [
        "Feeling restricted when told to cut back",
        "Believing life is meant to be enjoyed now, not only saved for later",
        "Frustrated when every purchase becomes a negotiation",
        "Wanting freedom to enjoy what they've earned without guilt",
    ],
    ("financial_personality", "investor"): [
        "Excited about building toward future goals together",
        "Frustrated when short-term spending undermines long-term plans",
        "Needing their planning to be valued as an act of love",
        "Sometimes forgetting that present enjoyment matters too",
    ],
    ("financial_personality", "balanced"): [
        "Comfortable with moderate spending and saving",
        "Confused when their partner has strong reactions about money",
        "Wishing money were a simpler, less emotional topic",
        "Trying to keep the peace between saving and spending",
    ],
    # Lifestyle
    ("lifestyle_type", "adventurous"): [
        "Energized by new experiences and feeling trapped by routine",
        "Frustrated when weekends pass without anything happening",
        "Needing novelty to feel alive — not because home isn't enough",
        "Worried about missing out on life while being too comfortable",
    ],
    ("lifestyle_type", "homebody"): [
        "Drained by too many plans and needing quiet to recharge",
        "Feeling guilty for not being more adventurous",
        "Finding deep comfort in familiar routines and spaces",
        "Needing their home-time to be respected, not just tolerated",
    ],
    ("lifestyle_type", "social"): [
        "Energized by people and feeling isolated without social connection",
        "Hurt when their partner doesn't want to join social events",
        "Needing community beyond just the two of them",
        "Sometimes forgetting their partner recharges differently",
    ],
    ("lifestyle_type", "balanced"): [
        "Comfortable with variety but not extreme in either direction",
        "Sometimes confused by their partner's strong preference",
        "Wanting flexibility — some weeks active, some weeks quiet",
        "Trying to accommodate without losing their own rhythm",
    ],
    # Relationship Archetype
    ("relationship_archetype", "partner"): [
        "Feeling most connected when doing things together as a unit",
        "Hurt when their partner chooses solo time over couple time",
        "Needing shared experiences to feel secure in the relationship",
        "Sometimes worrying that independence means growing apart",
    ],
    ("relationship_archetype", "independent"): [
        "Needing space to be themselves without feeling guilty about it",
        "Feeling trapped when too much togetherness is expected",
        "Loving their partner deeply but also loving their own life",
        "Sometimes confused about why their partner reads space as rejection",
    ],
    ("relationship_archetype", "nurturer"): [
        "Showing love through caring and wanting it to be received",
        "Hurt when their help is declined or unappreciated",
        "Needing to feel needed — it's how they express love",
        "Sometimes overwhelming their partner without meaning to",
    ],
    ("relationship_archetype", "explorer"): [
        "Driven to grow and discover — personally and together",
        "Frustrated when the relationship feels stagnant",
        "Needing their growth to be seen as an asset, not a threat",
        "Sometimes forgetting to go deep before going wide",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Validation templates
# ─────────────────────────────────────────────────────────────────────────────

VALIDATION_TEMPLATES: Dict[str, str] = {
    "attachment_style": (
        "This isn't about one person being too much and the other being too little. "
        "{user_name}'s need for connection is real and healthy. "
        "{partner_name}'s need for space is real and healthy. "
        "You're both trying to feel safe — you just have different routes to get there. "
        "The friction isn't a character flaw in either of you. "
        "It's a timing mismatch that can absolutely be managed."
    ),
    "communication_style": (
        "Neither of you is communicating wrong. {user_name} and {partner_name} "
        "simply speak different emotional languages. One isn't more mature than the other. "
        "One isn't more caring. You both want to be understood — "
        "you just express and receive understanding differently. "
        "That's not a problem. That's something you can learn to bridge."
    ),
    "conflict_style": (
        "There's no right way to handle disagreements. {user_name}'s instinct and "
        "{partner_name}'s instinct are both attempts to protect the relationship. "
        "One protects by engaging. The other protects by not making things worse. "
        "Neither is avoidance of love. Neither is aggression. "
        "They're both care — expressed through different nervous systems."
    ),
    "love_language": (
        "You are both showing love. Every single day. "
        "The issue has never been effort — it's been translation. "
        "{user_name} gives love the way {user_name} would want to receive it. "
        "{partner_name} does the same. The gap isn't about caring less. "
        "It's about learning to give in the other person's language."
    ),
    "financial_personality": (
        "Neither of you is irresponsible with money. {user_name} and {partner_name} "
        "simply have different emotional relationships with financial security. "
        "One finds peace in saving. The other finds joy in experiencing. "
        "Both are valid. Both serve a purpose. "
        "The goal isn't to make you the same — it's to make the difference workable."
    ),
    "lifestyle_type": (
        "Neither of you is wrong about how you want to spend your time. "
        "{user_name} recharges one way. {partner_name} recharges another. "
        "These aren't choices — they're wiring. You didn't choose your energy patterns "
        "any more than you chose your height. The goal is respect and rhythm, "
        "not conversion."
    ),
    "relationship_archetype": (
        "The way {user_name} approaches the relationship and the way {partner_name} "
        "approaches it are both healthy and valid. Neither is more committed. "
        "Neither is more loving. You just orient differently toward togetherness "
        "and individuality. That's not a flaw to fix — it's a difference to navigate."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: Difficulty & Confidence
# ─────────────────────────────────────────────────────────────────────────────

DIFFICULTY_LOOKUP: Dict[str, Dict[str, dict]] = {
    "attachment_style": {
        "low": {
            "level": "easy",
            "explanation": "Small adjustments to daily habits are all that's needed here.",
            "confidence": "high",
            "confidence_explanation": "You already have a solid foundation. A little awareness goes a long way.",
        },
        "medium": {
            "level": "moderate",
            "explanation": "This requires consistent daily effort, but nothing extreme. The challenge is about timing and communication, not changing who you are.",
            "confidence": "high",
            "confidence_explanation": "Both of you want connection. You're just reaching for it differently. That's very fixable.",
        },
        "high": {
            "level": "challenging",
            "explanation": "This is a deep pattern that will take patience and sustained effort. Progress is real but gradual.",
            "confidence": "medium",
            "confidence_explanation": "Couples with this pattern can and do improve — but it takes commitment from both sides and at least 3-4 weeks of consistent practice.",
        },
    },
    "communication_style": {
        "low": {"level": "easy", "explanation": "A few simple agreements will smooth most of this out.", "confidence": "high", "confidence_explanation": "Communication differences respond fastest to awareness. Once you see the pattern, you can adapt quickly."},
        "medium": {"level": "moderate", "explanation": "This takes practice — translating between styles requires ongoing attention.", "confidence": "high", "confidence_explanation": "Communication is the most improvable dimension. Most couples see meaningful change within 1-2 weeks."},
        "high": {"level": "challenging", "explanation": "Deep communication gaps take time and patience to bridge.", "confidence": "medium-high", "confidence_explanation": "It's very doable, but requires both partners actively practicing new habits."},
    },
    "conflict_style": {
        "low": {"level": "easy", "explanation": "Minor adjustments to how you handle disagreements.", "confidence": "high", "confidence_explanation": "You already handle conflict reasonably well. Small tweaks will make it smoother."},
        "medium": {"level": "moderate", "explanation": "Changing conflict patterns requires rewiring automatic reactions. It's not easy, but it's very doable.", "confidence": "medium-high", "confidence_explanation": "Both of you care about resolution. That shared desire is the foundation for change."},
        "high": {"level": "challenging", "explanation": "Deep conflict patterns are some of the hardest to shift. They involve automatic nervous system responses.", "confidence": "medium", "confidence_explanation": "Real improvement is possible with commitment. External support (a book, a course, a counselor) may accelerate progress."},
    },
}

# Fallback for dimensions not explicitly listed
_DEFAULT_DIFFICULTY = {
    "low": {"level": "easy", "explanation": "Small awareness shifts will help here.", "confidence": "high", "confidence_explanation": "This is very manageable with a little effort."},
    "medium": {"level": "moderate", "explanation": "Consistent effort over 2-3 weeks will show results.", "confidence": "high", "confidence_explanation": "Most couples see improvement once they understand the pattern."},
    "high": {"level": "challenging", "explanation": "This requires sustained commitment but is absolutely achievable.", "confidence": "medium", "confidence_explanation": "Improvement takes time here, but couples who stick with it consistently report meaningful change."},
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10: Mistakes to avoid
# ─────────────────────────────────────────────────────────────────────────────

MISTAKES: Dict[str, Dict[frozenset, List[str]]] = {
    "attachment_style": {
        frozenset({"anxious", "avoidant"}): [
            "Demanding immediate reassurance when your partner needs space",
            "Taking space without saying when you'll return",
            "Interpreting silence as anger or rejection",
            "Sending multiple follow-up messages when one hasn't been answered",
            "Trying to 'fix' each other's natural comfort level with closeness",
        ],
        frozenset({"avoidant", "avoidant"}): [
            "Assuming everything is fine because nobody is complaining",
            "Letting weeks pass without a real emotional check-in",
            "Using busyness as a reason to avoid vulnerability",
            "Waiting for the other person to initiate — they're waiting too",
        ],
    },
    "communication_style": {
        frozenset({"direct", "diplomatic"}): [
            "Interpreting softness as dishonesty",
            "Interpreting bluntness as cruelty",
            "Finishing your partner's sentences out of impatience",
            "Saying 'just say what you mean' — it shuts the other person down",
            "Rolling your eyes at how the other communicates",
        ],
        frozenset({"analytical", "expressive"}): [
            "Offering solutions when your partner just needs to vent",
            "Getting louder or more emotional to 'make them feel'",
            "Dismissing feelings as irrational",
            "Refusing to engage with logic because it 'doesn't feel right'",
        ],
    },
    "conflict_style": {
        frozenset({"avoiding", "competing"}): [
            "Raising your voice to force engagement",
            "Walking away without saying when you'll return",
            "Bringing up past arguments during current disagreements",
            "Using silence as punishment rather than genuine space-taking",
            "Saying 'we need to talk' with no context — it creates dread",
        ],
        frozenset({"avoiding", "avoiding"}): [
            "Assuming that if nobody mentions it, it's resolved",
            "Letting resentment build until it explodes unexpectedly",
            "Avoiding topics because 'it's not worth the fight'",
            "Using humor to deflect from real concerns",
        ],
    },
}

# Generic mistakes by severity
GENERIC_MISTAKES: Dict[str, List[str]] = {
    "low": [
        "Ignoring small differences until they become big frustrations",
        "Assuming your way is the 'normal' way",
        "Forgetting to acknowledge what's already working well",
    ],
    "medium": [
        "Expecting change overnight — habits take weeks to shift",
        "Keeping score of who tries harder",
        "Having important conversations when tired, hungry, or rushed",
        "Bringing up the difference during arguments instead of calm moments",
    ],
    "high": [
        "Trying to change who your partner fundamentally is",
        "Using this information as ammunition during fights",
        "Giving up after one bad week — setbacks are normal",
        "Comparing your relationship to others",
        "Waiting for your partner to change first before you start",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12: First Step Today
# ─────────────────────────────────────────────────────────────────────────────

FIRST_STEPS: Dict[str, Dict[frozenset, dict]] = {
    "attachment_style": {
        frozenset({"anxious", "avoidant"}): {
            "user_action": "Send one short message telling {partner_name} something you appreciated about them today. Keep it to one sentence. Don't ask for a response.",
            "partner_action": "When you see the message, reply with one thing you appreciated about {user_name} this week. Keep it simple — no pressure to have a conversation.",
            "time_required": "2 minutes total",
            "why_it_works": "It creates one micro-moment of connection without any pressure to respond at length.",
        },
        frozenset({"avoidant", "avoidant"}): {
            "user_action": "Tell {partner_name} one true thing about how you're feeling today — even if it's small. 'I felt happy when you made coffee this morning.'",
            "partner_action": "When {user_name} shares, respond with 'Thank you for telling me' and one thing you're feeling too.",
            "time_required": "3 minutes",
            "why_it_works": "It breaks the habit of keeping everything surface-level with the smallest possible step.",
        },
    },
    "communication_style": {
        frozenset({"direct", "diplomatic"}): {
            "user_action": "Before your next request or opinion, add one softening sentence first: 'This isn't urgent but...' or 'I want to check something with you...'",
            "partner_action": "Before the end of today, say one clear, direct sentence about something you need: 'I'd like us to...' No wrapping needed.",
            "time_required": "1 minute each",
            "why_it_works": "It's one tiny experiment in the other person's language. Low risk, high learning.",
        },
    },
    "conflict_style": {
        frozenset({"avoiding", "competing"}): {
            "user_action": "Think of one small thing that's been on your mind. Write it in a text to {partner_name}: 'Small thing — [X] has been on my mind. No rush to discuss.'",
            "partner_action": "When you see the text, reply ONLY with: 'Thanks for telling me. I'll think about it.' Don't expand, don't escalate. Just acknowledge.",
            "time_required": "2 minutes",
            "why_it_works": "It proves that raising a concern doesn't have to mean a big confrontation.",
        },
    },
}

GENERIC_FIRST_STEP: dict = {
    "user_action": "Tell {partner_name} one specific thing you appreciate about them today. Be concrete — not 'you're great' but 'I noticed when you did X and it meant a lot.'",
    "partner_action": "Respond with one thing you appreciate about {user_name}. Match their specificity.",
    "time_required": "2 minutes",
    "why_it_works": "Starting with appreciation creates emotional safety before working on challenges.",
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13: Can This Improve?
# ─────────────────────────────────────────────────────────────────────────────

CAN_IMPROVE: Dict[str, str] = {
    "attachment_style": (
        "Yes — and often faster than couples expect. The push-pull pattern responds "
        "well to predictability. When both partners know there's a guaranteed daily "
        "connection point, the urgency to pursue decreases and the resistance to "
        "engage softens. Most couples notice meaningful change within 2–3 weeks of "
        "consistent daily practice."
    ),
    "communication_style": (
        "Yes — and this is one of the fastest areas to improve. Once you understand "
        "that you're speaking different languages (not ignoring each other), the "
        "frustration drops immediately. Learning to signal 'listen mode' vs 'solve mode' "
        "typically changes the quality of conversations within days."
    ),
    "conflict_style": (
        "Yes — though it takes a bit more patience. Conflict responses are deeply "
        "wired and automatic. But they CAN be overridden with practice. The key is "
        "creating a shared protocol BEFORE conflict happens, so you don't have to "
        "think clearly in heated moments. Most couples find the first few weeks hardest, "
        "then the new pattern starts feeling natural."
    ),
    "love_language": (
        "Yes — and this is often the quickest fix. Love language differences aren't "
        "deep incompatibilities. They're simply translation gaps. Once you know what "
        "your partner actually needs to feel loved, providing it is usually easy and "
        "even enjoyable. Results often show within the first week."
    ),
    "financial_personality": (
        "Yes — especially with clear structure. When money conversations have "
        "agreed rules (separate personal funds, joint meeting, no-judgment thresholds), "
        "the emotional charge around money drops significantly. The underlying values "
        "don't change, but the friction does."
    ),
    "lifestyle_type": (
        "Yes — with mutual respect and clear agreements. Lifestyle differences don't "
        "go away, but the resentment around them absolutely can. When both partners "
        "feel their preferences are honored (not just tolerated), the negotiation "
        "becomes collaborative rather than competitive."
    ),
    "relationship_archetype": (
        "Yes — when both partners feel their orientation is valued rather than "
        "threatened. The togetherness partner needs to know their partner CHOOSES "
        "to be there. The independent partner needs to know they're not being "
        "swallowed up. Once both needs are explicitly named and protected, the "
        "tension tends to ease significantly."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────


def generate_coaching_plan(
    dimension: str,
    severity: str,
    user_name: str,
    partner_name: str,
    user_type: str,
    partner_type: str,
    action_steps: List[str],
    weekly_exercise: str,
) -> dict:
    """
    Generate the full v3 coaching plan for one dimension.

    Args:
        dimension: e.g., "attachment_style"
        severity: "low", "medium", "high"
        user_name: Display name for user
        partner_name: Display name for partner
        user_type: e.g., "anxious"
        partner_type: e.g., "avoidant"
        action_steps: Already-personalized action step strings
        weekly_exercise: Exercise text from recommendations

    Returns:
        Dict with version=3 and all 14 sections populated.
    """
    key = frozenset({user_type, partner_type})

    user_actions, partner_actions, together_actions = split_actions(
        action_steps, user_name, partner_name, user_type, partner_type
    )

    return {
        "version": 3,
        "whats_happening": _resolve_whats_happening(dimension, key, user_name, partner_name),
        "example_dialogue": _resolve_dialogue(dimension, key, user_name, partner_name),
        "example_closing": _resolve_dialogue_closing(dimension, key, user_name, partner_name),
        "feelings": {
            "user": FEELINGS_BY_TYPE.get((dimension, user_type), _generic_feelings("user")),
            "partner": FEELINGS_BY_TYPE.get((dimension, partner_type), _generic_feelings("partner")),
        },
        "why_this_happens": build_why_section(dimension, user_name, user_type, partner_name, partner_type),
        "validation": _resolve_validation(dimension, user_name, partner_name),
        "difficulty": _resolve_difficulty(dimension, severity),
        "user_actions": user_actions,
        "partner_actions": partner_actions,
        "together_actions": together_actions,
        "mistakes": _resolve_mistakes(dimension, key, severity),
        "weekly_challenge": format_challenge(weekly_exercise),
        "first_step": _resolve_first_step(dimension, key, user_name, partner_name),
        "can_this_improve": CAN_IMPROVE.get(dimension, CAN_IMPROVE.get("attachment_style", "")),
        "expected_outcome": build_expected_outcome(dimension, severity),
    }


def split_actions(
    steps: List[str], user_name: str, partner_name: str,
    user_type: str = "", partner_type: str = "",
) -> tuple:
    """
    Split a combined action list into (user_actions, partner_actions, together_actions).

    Uses comprehensive pattern matching including:
    - Direct name prefix ("Sarah: do X")
    - Name in body (only one name present)
    - Role-based descriptors ("the quieter partner", "the direct partner")
    - Type-mapped descriptors based on user_type/partner_type
    """
    user_actions = []
    partner_actions = []
    together_actions = []

    together_markers = [
        "together", "both", "schedule", "create a shared", "create a signal",
        "agree on", "hold a", "plan one shared", "name the underlying",
    ]

    # Build type-to-role mapping for descriptor-based splitting
    # Maps descriptors that mean "this is the user" or "this is the partner"
    user_descriptors = _build_descriptors_for_type(user_type)
    partner_descriptors = _build_descriptors_for_type(partner_type)

    for step in steps:
        lower = step.lower()

        # 1. Direct name prefix
        if lower.startswith(user_name.lower()) or lower.startswith(f"{user_name.lower()}:"):
            user_actions.append(step)
        elif lower.startswith(partner_name.lower()) or lower.startswith(f"{partner_name.lower()}:"):
            partner_actions.append(step)

        # 2. Together markers
        elif any(marker in lower for marker in together_markers):
            together_actions.append(step)

        # 3. Name appears in body (only one)
        elif user_name.lower() in lower and partner_name.lower() not in lower:
            user_actions.append(step)
        elif partner_name.lower() in lower and user_name.lower() not in lower:
            partner_actions.append(step)

        # 4. Role/descriptor matching — only if ONE role matches (not both)
        elif _matches_descriptors(lower, user_descriptors) and not _matches_descriptors(lower, partner_descriptors):
            user_actions.append(step)
        elif _matches_descriptors(lower, partner_descriptors) and not _matches_descriptors(lower, user_descriptors):
            partner_actions.append(step)
        elif _matches_descriptors(lower, user_descriptors) and _matches_descriptors(lower, partner_descriptors):
            # Both roles mentioned — it's a shared step
            together_actions.append(step)

        # 5. Fallback: distribute alternating to user/partner if both empty
        else:
            together_actions.append(step)

    # If user or partner sections are still empty, redistribute from together
    if not user_actions and not partner_actions and len(together_actions) >= 3:
        # Assign first step to user, second to partner, rest stays together
        user_actions.append(together_actions.pop(0))
        partner_actions.append(together_actions.pop(0))
    elif not user_actions and len(together_actions) >= 2:
        user_actions.append(together_actions.pop(0))
    elif not partner_actions and len(together_actions) >= 2:
        partner_actions.append(together_actions.pop(0))

    return user_actions, partner_actions, together_actions


# Descriptor phrases that map to specific types
_TYPE_DESCRIPTORS: Dict[str, List[str]] = {
    # Attachment
    "anxious": ["the pursuing partner", "the partner who reaches out", "the partner who seeks reassurance", "partner who reaches out more"],
    "avoidant": ["the withdrawing partner", "the partner who needs space", "the quieter partner", "partner who needs space"],
    "fearful_avoidant": ["the partner who oscillates", "the partner who switches"],
    # Communication
    "direct": ["the direct partner", "the blunt partner", "the efficient partner"],
    "diplomatic": ["the diplomatic partner", "the gentle partner", "the soft partner"],
    "analytical": ["the logical partner", "the analytical partner", "the practical partner"],
    "expressive": ["the expressive partner", "the emotional partner", "the more expressive partner", "the storyteller"],
    # Conflict
    "avoiding": ["the quieter partner", "the quiet partner", "the partner who retreats", "the partner who needs space"],
    "competing": ["the more intense partner", "the louder partner", "the partner who engages"],
    "collaborative": ["the partner who wants to talk", "the talker", "the talking partner"],
    "compromising": ["the partner who compromises"],
    # Financial
    "saver": ["the saver", "the saving partner", "the partner who saves"],
    "spender": ["the spender", "the spending partner", "the partner who spends"],
    "investor": ["the investor", "the future-focused partner", "the planning partner", "the future-planner", "the planner"],
    # Lifestyle
    "adventurous": ["the adventure partner", "the adventurous partner", "the active partner"],
    "homebody": ["the homebody", "the home partner", "the quiet partner", "homebody makes home", "homebody partner"],
    "social": ["the social partner"],
    # Love language
    "words": ["the words partner", "the verbal partner"],
    "touch": ["the touch partner", "the physical partner"],
    "time": ["the time partner", "the presence partner"],
    "acts": ["the acts partner", "the practical partner"],
    "gifts": ["the gifts partner"],
    # Archetype
    "partner": ["the togetherness partner", "the depth partner"],
    "independent": ["the independent partner", "the autonomy partner"],
    "nurturer": ["the caring partner", "the nurturing partner"],
    "explorer": ["the explorer", "the growth partner"],
}


def _build_descriptors_for_type(user_type: str) -> List[str]:
    """Get all descriptor phrases that identify this type."""
    return _TYPE_DESCRIPTORS.get(user_type, [])


def _matches_descriptors(text: str, descriptors: List[str]) -> bool:
    """Check if any descriptor phrase appears in the text."""
    for desc in descriptors:
        if desc in text:
            return True
    return False


def format_challenge(exercise_text: str) -> dict:
    """
    Parse a weekly exercise string into a structured challenge object.

    Extracts name, duration, and tracking from the text.
    """
    # Try to extract name (text before first —)
    name = "This Week's Challenge"
    if "—" in exercise_text:
        name = exercise_text.split("—")[0].strip()
        if name.startswith("The "):
            pass  # keep it
    elif ":" in exercise_text[:50]:
        name = exercise_text.split(":")[0].strip()

    # Extract duration
    duration = "10-15 minutes"
    duration_match = re.search(r"[Tt]ime:?\s*(.+?)(?:\.|$)", exercise_text)
    if duration_match:
        duration = duration_match.group(1).strip().rstrip(".")
    elif "minutes" in exercise_text.lower():
        min_match = re.search(r"(\d+)\s*minutes?", exercise_text.lower())
        if min_match:
            duration = f"{min_match.group(1)} minutes"

    # Extract tracking/success criteria
    tracking = "Notice whether you completed it and how it felt."
    track_match = re.search(r"[Tt]rack:?\s*(.+?)(?:\.|$)", exercise_text)
    if track_match:
        tracking = track_match.group(1).strip().rstrip(".")

    return {
        "name": name,
        "description": exercise_text,
        "duration": duration,
        "frequency": "Once this week" if "once" in exercise_text.lower() else "Daily",
        "success_criteria": tracking,
        "tracking": tracking,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_whats_happening(dimension: str, key: frozenset, user_name: str, partner_name: str) -> str:
    """Get the 'what's happening' text, with name substitution."""
    dim_entries = WHATS_HAPPENING.get(dimension, {})
    template = dim_entries.get(key)
    if not template:
        # Generic fallback
        user_desc = _get_type_description(dimension, list(key)[0] if key else "unknown")
        partner_desc = _get_type_description(dimension, list(key)[1] if len(key) > 1 else "unknown")
        template = (
            "There's a difference in how {user_name} and {partner_name} approach this area. "
            "{user_name} " + user_desc + ", while {partner_name} " + partner_desc + ". "
            "This isn't a flaw in either of you — it's just a difference in wiring "
            "that shows up in everyday moments."
        )
    return template.format(user_name=user_name, partner_name=partner_name)


def _resolve_dialogue(dimension: str, key: frozenset, user_name: str, partner_name: str) -> List[dict]:
    """Get dialogue lines with resolved speaker names."""
    dim_dialogues = EXAMPLE_DIALOGUES.get(dimension, {})
    entry = dim_dialogues.get(key)
    if not entry:
        return []
    result = []
    for speaker, line in entry["lines"]:
        resolved_name = user_name if speaker == "user" else partner_name
        result.append({"speaker": resolved_name, "line": line})
    return result


def _resolve_dialogue_closing(dimension: str, key: frozenset, user_name: str, partner_name: str) -> str:
    """Get the compassionate closing after dialogue."""
    dim_dialogues = EXAMPLE_DIALOGUES.get(dimension, {})
    entry = dim_dialogues.get(key)
    if not entry:
        return ""
    return entry["closing"].format(user_name=user_name, partner_name=partner_name)


def _resolve_validation(dimension: str, user_name: str, partner_name: str) -> str:
    """Get dimension-specific validation text."""
    template = VALIDATION_TEMPLATES.get(dimension, VALIDATION_TEMPLATES.get("attachment_style", ""))
    return template.format(user_name=user_name, partner_name=partner_name)


def _resolve_difficulty(dimension: str, severity: str) -> dict:
    """Get difficulty/confidence assessment."""
    dim_lookup = DIFFICULTY_LOOKUP.get(dimension, _DEFAULT_DIFFICULTY)
    return dim_lookup.get(severity, dim_lookup.get("medium", _DEFAULT_DIFFICULTY["medium"]))


def _resolve_mistakes(dimension: str, key: frozenset, severity: str) -> List[str]:
    """Get dimension-specific mistakes or generic fallback."""
    dim_mistakes = MISTAKES.get(dimension, {})
    specific = dim_mistakes.get(key)
    if specific:
        return specific
    return GENERIC_MISTAKES.get(severity, GENERIC_MISTAKES["medium"])


def _resolve_first_step(dimension: str, key: frozenset, user_name: str, partner_name: str) -> dict:
    """Get personalized first step."""
    dim_steps = FIRST_STEPS.get(dimension, {})
    entry = dim_steps.get(key, GENERIC_FIRST_STEP)
    return {
        "user_action": entry["user_action"].format(user_name=user_name, partner_name=partner_name),
        "partner_action": entry["partner_action"].format(user_name=user_name, partner_name=partner_name),
        "time_required": entry["time_required"],
        "why_it_works": entry["why_it_works"],
    }


def _generic_feelings(role: str) -> List[str]:
    """Fallback feelings when dimension/type not in lookup."""
    if role == "user":
        return [
            "Wanting to be understood",
            "Unsure why things feel harder than they should",
            "Caring about the relationship but not sure what to change",
        ]
    return [
        "Wanting to be accepted as they are",
        "Uncertain about what the other person needs",
        "Caring deeply but expressing it differently",
    ]
