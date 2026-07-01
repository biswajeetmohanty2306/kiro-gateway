# -*- coding: utf-8 -*-
"""AI Relationship Coach Safety Engine (J7-E).

Deterministic rule-based content filtering for coach conversations.
Decides whether a user message can be processed safely.

Pure module:
  - No SQL, no async, no FastAPI, no HTTP, no I/O
  - No ML, no embeddings, no moderation APIs
  - Deterministic: same input always produces same decision
  - Never mutates inputs

Public API:
  evaluate_message(user_message, relationship_context) → SafetyDecision
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .config import MAX_MESSAGE_LENGTH
from .types import RelationshipContext, SafetyAction, SafetyDecision


# ─────────────────────────────────────────────────────────────────────────────
# Replacement Messages (calm, non-judgmental, never shaming)
# ─────────────────────────────────────────────────────────────────────────────

_CRISIS_MESSAGE = (
    "I want to make sure you're safe. If you're having thoughts of harming yourself, "
    "please reach out to the 988 Suicide & Crisis Lifeline (call or text 988) "
    "or the Crisis Text Line (text HOME to 741741). "
    "I'm here to help with your relationship, but this is beyond what I can support."
)

_VIOLENCE_MESSAGE = (
    "If you or someone you know is in danger, please contact emergency services (911) "
    "or the National Domestic Violence Hotline (1-800-799-7233). "
    "Your safety comes first."
)

_BLOCK_EMPTY = "It looks like your message was empty. What's on your mind?"

_BLOCK_TOO_LONG = (
    "That message is a bit long for me to process well. "
    "Could you try sharing the most important part in fewer words?"
)

_BLOCK_ILLEGAL = (
    "I'm not able to help with that. "
    "I'm here to support your relationship — is there something about how you and your partner "
    "are doing that I can help with?"
)

_BLOCK_HATE = (
    "I'm here to help you and your partner understand each other better. "
    "I'm not able to engage with that kind of language. "
    "Would you like to try rephrasing what you're feeling?"
)

_BLOCK_MEDICAL = (
    "That sounds like something a healthcare professional could help with better than I can. "
    "I'm best at helping you think about your relationship. "
    "Is there something between you and your partner I can help with?"
)

_BLOCK_INJECTION = (
    "I appreciate the creativity, but I'm here specifically to help with your relationship. "
    "What's been on your mind about you and your partner?"
)

_BLOCK_OUT_OF_SCOPE = (
    "That's outside what I'm designed to help with. "
    "I'm here to support conversations about your relationship. "
    "Is there anything about how things are going between you two?"
)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Definitions
# ─────────────────────────────────────────────────────────────────────────────

_SELF_HARM_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(kill\s*(my)?self|suicide|suicidal|end\s*(my|it\s*all))\b", re.IGNORECASE),
    re.compile(r"\b(want\s*to\s*die|don'?t\s*want\s*to\s*(live|be\s*alive))\b", re.IGNORECASE),
    re.compile(r"\b(self[- ]?harm|cut(ting)?\s*myself|hurt(ing)?\s*myself)\b", re.IGNORECASE),
]

_VIOLENCE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(hit(s|ting)?\s*(me|her|him)|beat(s|ing)?\s*(me|her|him))\b", re.IGNORECASE),
    re.compile(r"\b(abuse[ds]?|abusing|domestic\s*violence)\b", re.IGNORECASE),
    re.compile(r"\b(threaten(ed|ing|s)?(\s*to)?\s*(kill|hurt|harm))\b", re.IGNORECASE),
    re.compile(r"\b(chok(ed|ing|es?)|strangl(ed|ing|es?))\b", re.IGNORECASE),
]

_HATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(racial\s*slur|hate\s*(all|every)\s*(women|men|people))\b", re.IGNORECASE),
    re.compile(r"\b(deserve[s]?\s*to\s*(die|suffer|be\s*hurt))\b", re.IGNORECASE),
]

_ILLEGAL_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(how\s*to\s*(stalk|hack|drug|poison|blackmail))\b", re.IGNORECASE),
    re.compile(r"\b(revenge\s*porn|spy\s*on\s*(my|her|his))\b", re.IGNORECASE),
    re.compile(r"\b(track(ing)?\s*(her|his|my\s*partner('s)?\s*(phone|location)))\b", re.IGNORECASE),
]

_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s*(all\s*)?(previous|prior|above)\s*(instructions|prompts?|rules)", re.IGNORECASE),
    re.compile(r"(reveal|show|print|output)\s*(your|the)\s*(system\s*prompt|instructions|rules)", re.IGNORECASE),
    re.compile(r"act\s*as\s*(chatgpt|gpt|a\s*different|another)\b", re.IGNORECASE),
    re.compile(r"forget\s*(your|all|the)\s*(rules|instructions|boundaries|constraints)", re.IGNORECASE),
    re.compile(r"you\s*are\s*now\s*(a|an|my)\b", re.IGNORECASE),
    re.compile(r"(new|override|bypass)\s*(system\s*)?(prompt|instructions|persona)", re.IGNORECASE),
    re.compile(r"\bDAN\s*mode\b", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
]

_MEDICAL_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(diagnos(e|is|ed)|what\s*(disorder|condition|illness))\b", re.IGNORECASE),
    re.compile(r"\b(prescri(be|ption)|medic(ation|ine)|should\s*I\s*take)\b", re.IGNORECASE),
    re.compile(r"\b(BPD|ADHD|bipolar|narcissi(st|stic)|sociopath|psychopath)\b", re.IGNORECASE),
    re.compile(r"\b(is\s*(my\s*partner|he|she)\s*(a\s*)?(narcissi|sociopath|psychopath))", re.IGNORECASE),
]

_OUT_OF_SCOPE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(write\s*(me\s*)?(a|an|some)\s*(code|essay|email|story|poem))\b", re.IGNORECASE),
    re.compile(r"\b(help\s*(me\s*)?(with\s*)?(my\s*)?(homework|math|physics|chemistry))\b", re.IGNORECASE),
    re.compile(r"\b(what\s*is\s*the\s*(capital|population|weather))\b", re.IGNORECASE),
    re.compile(r"\b(translate|summarize\s*this\s*article)\b", re.IGNORECASE),
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_message(
    user_message: str,
    relationship_context: RelationshipContext,
) -> SafetyDecision:
    """Evaluate whether a user message is safe to process.

    Runs deterministic rule-based checks in priority order.
    Stops at the first matching rule and returns the corresponding decision.

    Args:
        user_message: The raw message text from the user.
        relationship_context: Current relationship context (unused by most rules,
            available for future context-aware checks).

    Returns:
        A SafetyDecision indicating whether the message is allowed.
    """
    # Ordered checks — first match wins
    checks: List[Tuple[str, SafetyDecision]] = [
        ("empty", _check_empty(user_message)),
        ("length", _check_too_long(user_message)),
        ("self_harm", _check_self_harm(user_message)),
        ("violence", _check_violence(user_message)),
        ("hate", _check_hate(user_message)),
        ("illegal", _check_illegal(user_message)),
        ("injection", _check_prompt_injection(user_message)),
        ("medical", _check_medical(user_message)),
        ("scope", _check_out_of_scope(user_message)),
    ]

    for _name, decision in checks:
        if not decision.allowed:
            return decision

    return _allow()


# ─────────────────────────────────────────────────────────────────────────────
# Check Helpers (each returns SafetyDecision)
# ─────────────────────────────────────────────────────────────────────────────


def _check_empty(message: str) -> SafetyDecision:
    """Block empty or whitespace-only messages."""
    if not message or not message.strip():
        return _block(_BLOCK_EMPTY, "empty_message")
    return _allow()


def _check_too_long(message: str) -> SafetyDecision:
    """Block messages exceeding the maximum character length."""
    if len(message) > MAX_MESSAGE_LENGTH:
        return _block(_BLOCK_TOO_LONG, "message_too_long")
    return _allow()


def _check_self_harm(message: str) -> SafetyDecision:
    """Escalate messages indicating self-harm or suicidal ideation."""
    if _matches_any(message, _SELF_HARM_PATTERNS):
        return _escalate(_CRISIS_MESSAGE, "self_harm_detected")
    return _allow()


def _check_violence(message: str) -> SafetyDecision:
    """Escalate messages indicating domestic violence or physical harm."""
    if _matches_any(message, _VIOLENCE_PATTERNS):
        return _escalate(_VIOLENCE_MESSAGE, "violence_detected")
    return _allow()


def _check_hate(message: str) -> SafetyDecision:
    """Block messages containing hate speech."""
    if _matches_any(message, _HATE_PATTERNS):
        return _block(_BLOCK_HATE, "hate_speech")
    return _allow()


def _check_illegal(message: str) -> SafetyDecision:
    """Block messages requesting help with illegal activities."""
    if _matches_any(message, _ILLEGAL_PATTERNS):
        return _block(_BLOCK_ILLEGAL, "illegal_request")
    return _allow()


def _check_prompt_injection(message: str) -> SafetyDecision:
    """Block prompt injection and jailbreak attempts."""
    if _matches_any(message, _INJECTION_PATTERNS):
        return _block(_BLOCK_INJECTION, "prompt_injection")
    return _allow()


def _check_medical(message: str) -> SafetyDecision:
    """Block requests for medical or psychological diagnosis."""
    if _matches_any(message, _MEDICAL_PATTERNS):
        return _block(_BLOCK_MEDICAL, "medical_request")
    return _allow()


def _check_out_of_scope(message: str) -> SafetyDecision:
    """Block requests clearly outside relationship coaching scope."""
    if _matches_any(message, _OUT_OF_SCOPE_PATTERNS):
        return _block(_BLOCK_OUT_OF_SCOPE, "out_of_scope")
    return _allow()


# ─────────────────────────────────────────────────────────────────────────────
# Decision Builders
# ─────────────────────────────────────────────────────────────────────────────


def _allow() -> SafetyDecision:
    """Construct an ALLOW decision."""
    return SafetyDecision(allowed=True, action=SafetyAction.ALLOW)


def _block(replacement: str, reason: str) -> SafetyDecision:
    """Construct a BLOCK decision with a replacement message."""
    return SafetyDecision(
        allowed=False,
        action=SafetyAction.BLOCK,
        reason=reason,
        replacement_message=replacement,
    )


def _escalate(replacement: str, reason: str) -> SafetyDecision:
    """Construct an ESCALATE decision with crisis resources."""
    return SafetyDecision(
        allowed=False,
        action=SafetyAction.ESCALATE,
        reason=reason,
        replacement_message=replacement,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Matching Utility
# ─────────────────────────────────────────────────────────────────────────────


def _matches_any(text: str, patterns: List[re.Pattern]) -> bool:
    """Check if text matches any pattern in the list."""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False
