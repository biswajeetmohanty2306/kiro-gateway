# -*- coding: utf-8 -*-
"""Couple Synchronization Engine (J5).

Compares BOTH partners' weekly reflections and generates ONE shared
weekly relationship summary using pure deterministic logic.

Inputs:
  - user_reflection: List of {question_id: str, answer: str} from the user
  - partner_reflection: List of {question_id: str, answer: str} from the partner
  Both are for the SAME calendar week. Either or both may be None/empty.

Outputs:
  A WeeklyRelationshipSummary TypedDict with exactly these fields:
    status              — One of: SYNCED, GROWING, MISALIGNED, CHECK_IN, INSUFFICIENT
    confidence          — Float 0.0–1.0 indicating certainty of the assessment
    title               — Human-readable headline
    summary             — 1–2 sentence description
    highlight           — One specific observation
    conversation_prompt — One gentle question for the couple

Deterministic rules:
  - Scale answers (1–5) are compared directly
  - Yes/no answers are converted: yes → 5.0, no → 1.0
  - Open-ended text answers are intentionally IGNORED (not comparable)
  - Alignment threshold: within 1.0 point on a 5-point scale
  - Growth threshold: both averages ≥ 3.5
  - Status is determined by: alignment + magnitude
  - Declining patterns are NEVER surfaced negatively — framed as SYNCED

What is intentionally ignored:
  - Open-ended text (cannot be compared deterministically)
  - Historical trends (that's the insights engine's job)
  - Individual question weighting (all scale answers weighted equally)
  - Time of submission (only presence matters)

No AI. No ML. No LLM. No external services.
No SQL. No async. No database access. No service imports.
Pure function: data in → summary out.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# Output Type
# ─────────────────────────────────────────────────────────────────────────────


class WeeklyRelationshipSummary(TypedDict):
    """Typed output of the synchronization engine."""

    status: str
    confidence: float
    title: str
    summary: str
    highlight: str
    conversation_prompt: str


# ─────────────────────────────────────────────────────────────────────────────
# Status Constants
# ─────────────────────────────────────────────────────────────────────────────

STATUS_SYNCED = "SYNCED"
STATUS_GROWING = "GROWING"
STATUS_MISALIGNED = "MISALIGNED"
STATUS_CHECK_IN = "CHECK_IN"
STATUS_INSUFFICIENT = "INSUFFICIENT"

# ─────────────────────────────────────────────────────────────────────────────
# Question Category Constants
# ─────────────────────────────────────────────────────────────────────────────

_SAFETY_IDS = frozenset({"safety_1", "safety_2", "safety_3"})
_CONNECTION_IDS = frozenset({"conn_1", "conn_2", "conn_3", "conn_4", "conn_5", "conn_6"})

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds
# ─────────────────────────────────────────────────────────────────────────────

_ALIGNMENT_THRESHOLD = 1.0   # Within 1 point on a 5-point scale
_GROWTH_THRESHOLD = 3.5      # Both averages must be ≥ this for GROWING

# ─────────────────────────────────────────────────────────────────────────────
# Titles (by status)
# ─────────────────────────────────────────────────────────────────────────────

_TITLES: Dict[str, str] = {
    STATUS_SYNCED: "You're on the same page",
    STATUS_GROWING: "Growing together",
    STATUS_MISALIGNED: "Different experiences this week",
    STATUS_INSUFFICIENT: "Not enough data yet",
    STATUS_CHECK_IN: "One voice so far",
}

# ─────────────────────────────────────────────────────────────────────────────
# Summaries (by status)
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARIES: Dict[str, str] = {
    STATUS_SYNCED: (
        "You both described this week in remarkably similar ways. "
        "When two people experience the same week similarly, "
        "it usually means you're paying attention to each other."
    ),
    STATUS_GROWING: (
        "Both of you seem to be moving in the same positive direction. "
        "Whatever you're doing differently — it's working."
    ),
    STATUS_MISALIGNED: (
        "One of you experienced more closeness than the other this week. "
        "Different experiences are common, and talking about them "
        "often creates understanding."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Highlight Strings (by status + condition)
# ─────────────────────────────────────────────────────────────────────────────

_HIGHLIGHT_SYNCED_HIGH = "Emotional safety is strong between you."
_HIGHLIGHT_SYNCED_MODERATE = "You both feel a similar sense of comfort together."
_HIGHLIGHT_SYNCED_DEFAULT = "You're experiencing this week from a similar place."

_HIGHLIGHT_GROWING_HIGH = "Connection feels especially strong this week."
_HIGHLIGHT_GROWING_DEFAULT = "The effort you're both making is visible in your answers."

_HIGHLIGHT_MISALIGNED_SAFETY = "Emotional safety felt different for each of you. That's worth a gentle conversation."
_HIGHLIGHT_MISALIGNED_DEFAULT = "Small differences in perception are completely normal."

# ─────────────────────────────────────────────────────────────────────────────
# Conversation Prompts (by status)
# ─────────────────────────────────────────────────────────────────────────────

_CONVERSATION_PROMPTS: Dict[str, List[str]] = {
    STATUS_SYNCED: [
        "What felt different for each of you this week?",
        "When did you feel closest to each other?",
        "What's one thing you'd like more of next week?",
    ],
    STATUS_GROWING: [
        "What do you think is helping things feel better?",
        "What helped you feel emotionally safe this week?",
        "What's one thing you noticed your partner doing differently?",
    ],
    STATUS_MISALIGNED: [
        "What felt different for each of you this week?",
        "Is there something one of you experienced that the other didn't notice?",
        "What would help you feel more connected next week?",
    ],
    STATUS_CHECK_IN: [
        "When your partner checks in, compare notes about how this week felt.",
    ],
    STATUS_INSUFFICIENT: [],
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def generate_weekly_relationship_summary(
    user_reflection: Optional[List[Dict[str, str]]],
    partner_reflection: Optional[List[Dict[str, str]]],
) -> WeeklyRelationshipSummary:
    """Generate a shared weekly relationship summary from both partners' reflections.

    Compares numeric/yes-no answers from both partners for the same week
    and determines how aligned their experiences were.

    Args:
        user_reflection: List of {question_id, answer} from the user, or None.
        partner_reflection: List of {question_id, answer} from the partner, or None.

    Returns:
        WeeklyRelationshipSummary with: status, confidence, title, summary,
        highlight, conversation_prompt.
    """
    has_user = user_reflection is not None and len(user_reflection) > 0
    has_partner = partner_reflection is not None and len(partner_reflection) > 0

    # Neither submitted
    if not has_user and not has_partner:
        return _build_result(
            status=STATUS_INSUFFICIENT,
            confidence=0.0,
            title=_build_title(STATUS_INSUFFICIENT),
            summary="Neither of you has checked in this week yet.",
            highlight="",
            prompt="",
        )

    # Only one submitted
    if not has_user or not has_partner:
        return _build_result(
            status=STATUS_CHECK_IN,
            confidence=0.3,
            title=_build_title(STATUS_CHECK_IN),
            summary="We're still waiting to hear your partner's perspective. "
                    "The relationship summary appears once both of you have checked in.",
            highlight="Checking in takes under two minutes.",
            prompt=_select_conversation_prompt(STATUS_CHECK_IN, None, None),
        )

    # Both submitted — compare
    user_scores = _extract_scores(user_reflection)
    partner_scores = _extract_scores(partner_reflection)

    if not user_scores and not partner_scores:
        return _build_result(
            status=STATUS_INSUFFICIENT,
            confidence=0.2,
            title=_build_title(STATUS_INSUFFICIENT),
            summary="Both reflections are present but don't contain enough comparable answers yet.",
            highlight="",
            prompt="",
        )

    # Compute category averages
    user_safety = _category_average(user_scores, _SAFETY_IDS)
    partner_safety = _category_average(partner_scores, _SAFETY_IDS)
    user_connection = _category_average(user_scores, _CONNECTION_IDS)
    partner_connection = _category_average(partner_scores, _CONNECTION_IDS)

    # Overall averages
    user_avg = _overall_average(user_scores)
    partner_avg = _overall_average(partner_scores)

    # Determine status
    status, confidence = _determine_status(
        user_avg, partner_avg,
        user_safety, partner_safety,
        user_connection, partner_connection,
    )

    # Build output
    title = _build_title(status)
    summary = _build_summary(status)
    highlight = _build_highlight(status, user_safety, partner_safety, user_connection, partner_connection)
    prompt = _select_conversation_prompt(status, user_avg, partner_avg)

    return _build_result(
        status=status,
        confidence=confidence,
        title=title,
        summary=summary,
        highlight=highlight,
        prompt=prompt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output Construction
# ─────────────────────────────────────────────────────────────────────────────


def _build_result(
    status: str,
    confidence: float,
    title: str,
    summary: str,
    highlight: str,
    prompt: str,
) -> WeeklyRelationshipSummary:
    """Construct the standardized output dict."""
    return {
        "status": status,
        "confidence": round(confidence, 2),
        "title": title,
        "summary": summary,
        "highlight": highlight,
        "conversation_prompt": prompt,
    }


def _build_title(status: str) -> str:
    """Generate a human-readable title for the given status."""
    return _TITLES.get(status, "This week together")


def _build_summary(status: str) -> str:
    """Generate the main summary text for a given status."""
    return _SUMMARIES.get(status, "")


def _build_highlight(
    status: str,
    user_safety: Optional[float],
    partner_safety: Optional[float],
    user_connection: Optional[float],
    partner_connection: Optional[float],
) -> str:
    """Select a highlight string based on status and category scores.

    This function contains decision logic only — all wording lives in
    module-level constants.
    """
    if status == STATUS_SYNCED:
        if user_safety is not None and partner_safety is not None:
            avg_safety = (user_safety + partner_safety) / 2
            if avg_safety >= 4.0:
                return _HIGHLIGHT_SYNCED_HIGH
            elif avg_safety >= 3.0:
                return _HIGHLIGHT_SYNCED_MODERATE
        return _HIGHLIGHT_SYNCED_DEFAULT

    elif status == STATUS_GROWING:
        if user_connection is not None and partner_connection is not None:
            avg_conn = (user_connection + partner_connection) / 2
            if avg_conn >= 4.0:
                return _HIGHLIGHT_GROWING_HIGH
        return _HIGHLIGHT_GROWING_DEFAULT

    elif status == STATUS_MISALIGNED:
        if (user_safety is not None and partner_safety is not None
                and abs(user_safety - partner_safety) > 1.5):
            return _HIGHLIGHT_MISALIGNED_SAFETY
        return _HIGHLIGHT_MISALIGNED_DEFAULT

    return ""


def _select_conversation_prompt(
    status: str,
    user_avg: Optional[float],
    partner_avg: Optional[float],
) -> str:
    """Select one conversation prompt based on status.

    Uses a deterministic index derived from the averages for variety
    across different weeks.
    """
    prompts = _CONVERSATION_PROMPTS.get(status, [])
    if not prompts:
        return ""

    if user_avg is not None and partner_avg is not None:
        index = int((user_avg + partner_avg) * 10) % len(prompts)
    else:
        index = 0

    return prompts[index]


# ─────────────────────────────────────────────────────────────────────────────
# Score Extraction
# ─────────────────────────────────────────────────────────────────────────────


def _extract_scores(answers: List[Dict[str, str]]) -> Dict[str, float]:
    """Extract numeric scores from a list of answers.

    Converts scale answers (1–5) directly and yes/no to 5.0/1.0.
    Open-ended answers (open_*) are skipped.
    """
    scores: Dict[str, float] = {}
    for entry in answers:
        qid = entry.get("question_id", "")
        answer = entry.get("answer", "")
        if qid.startswith("open_"):
            continue
        score = _answer_to_score(answer)
        if score is not None:
            scores[qid] = score
    return scores


def _answer_to_score(answer: str) -> Optional[float]:
    """Convert an answer string to a numeric score (1.0–5.0).

    Returns None if the answer cannot be converted.
    """
    try:
        val = float(answer)
        if 1.0 <= val <= 5.0:
            return val
    except (ValueError, TypeError):
        pass
    lower = answer.strip().lower()
    if lower == "yes":
        return 5.0
    if lower == "no":
        return 1.0
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Averages
# ─────────────────────────────────────────────────────────────────────────────


def _category_average(scores: Dict[str, float], category_ids: frozenset) -> Optional[float]:
    """Compute average score for a specific question category."""
    vals = [v for k, v in scores.items() if k in category_ids]
    return sum(vals) / len(vals) if vals else None


def _overall_average(scores: Dict[str, float]) -> Optional[float]:
    """Compute overall average across all numeric scores."""
    vals = list(scores.values())
    return sum(vals) / len(vals) if vals else None


# ─────────────────────────────────────────────────────────────────────────────
# Status Determination
# ─────────────────────────────────────────────────────────────────────────────


def _determine_status(
    user_avg: Optional[float],
    partner_avg: Optional[float],
    user_safety: Optional[float],
    partner_safety: Optional[float],
    user_connection: Optional[float],
    partner_connection: Optional[float],
) -> Tuple[str, float]:
    """Determine relationship status and confidence from score comparison.

    Rules:
      - If averages are within _ALIGNMENT_THRESHOLD and both ≥ _GROWTH_THRESHOLD → GROWING
      - If averages are within _ALIGNMENT_THRESHOLD but below threshold → SYNCED
      - If averages differ by more than _ALIGNMENT_THRESHOLD → MISALIGNED
    """
    if user_avg is None or partner_avg is None:
        return STATUS_INSUFFICIENT, 0.2

    diff = abs(user_avg - partner_avg)
    both_high = user_avg >= _GROWTH_THRESHOLD and partner_avg >= _GROWTH_THRESHOLD

    if diff <= _ALIGNMENT_THRESHOLD:
        if both_high:
            confidence = min(0.95, 0.7 + (min(user_avg, partner_avg) - 3.0) * 0.1)
            return STATUS_GROWING, round(confidence, 2)
        else:
            confidence = min(0.9, 0.6 + (1.0 - diff) * 0.3)
            return STATUS_SYNCED, round(confidence, 2)

    confidence = min(0.85, 0.5 + (diff - 1.0) * 0.2)
    return STATUS_MISALIGNED, round(confidence, 2)
