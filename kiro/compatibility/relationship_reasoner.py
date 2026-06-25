# -*- coding: utf-8 -*-
"""Relationship Reasoner (F8E.11).

This module UNDERSTANDS. It does not write English.
It analyzes a couple's dynamic and produces structured insight
that the narrative builder will later convert to human language.

Think like a therapist observing a couple — not like a template engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RelationshipInsight:
    """What a wise mentor would understand about this couple before speaking."""

    # The core dynamic
    main_pattern: str  # What keeps happening between them
    user_need: str  # What the user is reaching for
    partner_need: str  # What the partner is reaching for

    # The emotional undercurrents
    user_hidden_fear: str  # What the user secretly worries about
    partner_hidden_fear: str  # What the partner secretly worries about
    user_hidden_strength: str  # What the user brings that they may not see
    partner_hidden_strength: str  # What the partner brings that they may not see

    # The mechanics
    conflict_trigger: str  # What sets off the pattern
    why_it_escalates: str  # Why it gets worse instead of better

    # The way forward
    opportunity: str  # What could shift things
    recommended_focus: str  # The ONE thing that matters most right now
    realistic_timeline: str  # How long meaningful change takes

    # Context
    severity: str  # "low", "medium", "high"
    dimension: str


# ─────────────────────────────────────────────────────────────────────────────
# Attachment Style reasoning
# ─────────────────────────────────────────────────────────────────────────────

def _reason_attachment(
    user_name: str, partner_name: str,
    user_type: str, partner_type: str, severity: str,
) -> RelationshipInsight:
    """Reason about an attachment-style dynamic."""

    if user_type == "anxious" and partner_type == "avoidant":
        return RelationshipInsight(
            main_pattern=(
                f"When {user_name} senses distance, they reach out — a message, "
                f"a question, a need to know things are okay. When {partner_name} "
                f"feels that reaching, they need a moment to breathe. The more "
                f"{user_name} reaches, the more {partner_name} needs space. "
                f"The more space {partner_name} takes, the more {user_name} reaches."
            ),
            user_need="To know the connection is still there — even during silence",
            partner_need="To have room to come back on their own terms — without pressure",
            user_hidden_fear=f"That silence means {partner_name} is pulling away for good",
            partner_hidden_fear=f"That they'll never have enough space to feel like themselves",
            user_hidden_strength=(
                f"{user_name} brings emotional attentiveness — they notice shifts "
                f"in the relationship that others might miss"
            ),
            partner_hidden_strength=(
                f"{partner_name} brings stability — their groundedness can become "
                f"an anchor once the pattern softens"
            ),
            conflict_trigger=(
                f"Usually starts with a small gap — {partner_name} is quiet for a bit, "
                f"or slow to respond — and {user_name} reads it as something being wrong"
            ),
            why_it_escalates=(
                f"Each person's natural response accidentally triggers the other's fear. "
                f"Reaching out feels like pressure. Taking space feels like rejection. "
                f"Neither intends harm — but both end up in their worst-case scenario."
            ),
            opportunity=(
                "Predictable, bounded connection. When both people know exactly "
                "when and how they'll reconnect, the urgency to pursue drops "
                "and the resistance to engage softens."
            ),
            recommended_focus=(
                "One daily ritual — short, predictable, and non-negotiable — "
                "that gives both people something to count on"
            ),
            realistic_timeline="Most couples notice meaningful change within 2–3 weeks of daily practice",
            severity=severity,
            dimension="attachment_style",
        )

    elif user_type == "avoidant" and partner_type == "anxious":
        # Reverse roles
        return _reason_attachment(partner_name, user_name, "anxious", "avoidant", severity)

    elif user_type == "avoidant" and partner_type == "avoidant":
        return RelationshipInsight(
            main_pattern=(
                f"Both {user_name} and {partner_name} are comfortable with independence. "
                f"The relationship feels peaceful — low drama, lots of respect for space. "
                f"But underneath that calm, important feelings may be going unshared. "
                f"Not because either person doesn't care — but because neither naturally "
                f"initiates emotional depth."
            ),
            user_need="To feel emotionally connected without being forced into vulnerability",
            partner_need="The same — connection that doesn't feel like an interrogation",
            user_hidden_fear="That the relationship is slowly becoming a comfortable roommate situation",
            partner_hidden_fear="That raising emotional topics will disrupt the peace they've built",
            user_hidden_strength=f"{user_name} creates a calm, non-demanding space",
            partner_hidden_strength=f"{partner_name} provides stability and consistency",
            conflict_trigger="Nothing dramatic — it's the slow accumulation of unspoken things",
            why_it_escalates="It doesn't escalate visibly. It erodes quietly. One day someone realizes they feel alone despite being in a relationship.",
            opportunity="Structured, low-intensity emotional check-ins that feel safe rather than intrusive",
            recommended_focus="One weekly ritual where both people share one honest feeling — small and bounded",
            realistic_timeline="Improvement appears within 2–3 weeks once the habit establishes",
            severity=severity,
            dimension="attachment_style",
        )

    elif user_type == "anxious" and partner_type == "anxious":
        return RelationshipInsight(
            main_pattern=(
                f"Both {user_name} and {partner_name} feel things deeply and quickly. "
                f"When either senses uncertainty in the relationship, worry arrives fast. "
                f"The challenge isn't that they don't love each other enough — "
                f"it's that they're both looking for reassurance at the same time."
            ),
            user_need="A steady base to return to when worry arrives",
            partner_need="The same — someone who can be calm when they can't be",
            user_hidden_fear="That their need for reassurance is 'too much'",
            partner_hidden_fear="The same — that their intensity will push the other away",
            user_hidden_strength=f"{user_name}'s emotional awareness catches problems early",
            partner_hidden_strength=f"{partner_name}'s willingness to engage means nothing stays buried",
            conflict_trigger="Small ambiguity — a delayed text, a distracted moment — escalates when both are activated",
            why_it_escalates="When both people are seeking reassurance simultaneously, neither can provide it. The anxiety amplifies in a loop.",
            opportunity="Individual self-regulation practices so at least one person can be steady when the other is spinning",
            recommended_focus="Each person develops one personal calming practice they can use independently",
            realistic_timeline="1–2 weeks to establish the habit, 3–4 weeks for it to become automatic",
            severity=severity,
            dimension="attachment_style",
        )

    # Default/fallback for other attachment pairings
    return RelationshipInsight(
        main_pattern=f"{user_name} and {partner_name} have different comfort levels with closeness and independence.",
        user_need="To feel the relationship is secure in the way that makes sense to them",
        partner_need="The same — expressed differently",
        user_hidden_fear="That their way of connecting isn't enough",
        partner_hidden_fear="That their way of connecting isn't understood",
        user_hidden_strength="Genuine care for the relationship",
        partner_hidden_strength="Genuine care expressed differently",
        conflict_trigger="Moments where their different needs collide",
        why_it_escalates="Each person's natural response accidentally triggers the other's insecurity",
        opportunity="Understanding that different doesn't mean wrong",
        recommended_focus="One daily moment of deliberate connection",
        realistic_timeline="Noticeable improvement within 2–3 weeks",
        severity=severity,
        dimension="attachment_style",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def reason_about_relationship(
    user_name: str,
    partner_name: str,
    user_type: str,
    partner_type: str,
    dimension: str,
    severity: str,
    overall_score: float = 60.0,
) -> RelationshipInsight:
    """
    Understand a couple's dynamic before deciding what to say.

    This is the therapist's internal thinking — not the words they'll speak.
    """
    if dimension == "attachment_style":
        return _reason_attachment(user_name, partner_name, user_type, partner_type, severity)

    # For dimensions not yet migrated, return a minimal insight
    return RelationshipInsight(
        main_pattern=f"{user_name} and {partner_name} approach this area differently.",
        user_need="To feel understood and respected in their approach",
        partner_need="The same — in their own way",
        user_hidden_fear="That their way isn't valued",
        partner_hidden_fear="That their way isn't understood",
        user_hidden_strength="Genuine investment in the relationship",
        partner_hidden_strength="Genuine investment expressed differently",
        conflict_trigger="Moments where different approaches collide",
        why_it_escalates="Each person interprets the other's difference as a problem rather than a preference",
        opportunity="Recognizing the pattern and choosing a different response",
        recommended_focus="One small experiment this week",
        realistic_timeline="Improvement often visible within 1–2 weeks",
        severity=severity,
        dimension=dimension,
    )
