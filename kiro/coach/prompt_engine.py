# -*- coding: utf-8 -*-
"""AI Relationship Coach Prompt Engine (J7-D).

Converts a fully-built PromptContext into a PromptPackage ready for LLM submission.
Responsible ONLY for prompt construction — no business logic, no DB, no async.

Pure module:
  - Deterministic: same PromptContext always produces same PromptPackage
  - No SQL, no async, no FastAPI, no HTTP, no I/O
  - Never mutates inputs
  - Respects token budgets from config

Public API:
  build_prompt_package(context: PromptContext) → PromptPackage
"""

from __future__ import annotations

from typing import Dict, List

from .config import (
    COACH_MAX_TOKENS,
    COACH_MODEL,
    COACH_TEMPERATURE,
    HISTORY_MAX_TOKENS,
)
from .types import (
    MessageRecord,
    PromptContext,
    PromptPackage,
    RelationshipContext,
    ConversationContext,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants — Approximate token estimation (chars / 4)
# ─────────────────────────────────────────────────────────────────────────────

_CHARS_PER_TOKEN = 4


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt Sections
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_IDENTITY = """You are RelateAI's relationship coach — a warm, thoughtful companion \
who has been quietly paying attention to {user_name} and {partner_name}'s relationship."""

_SECTION_ROLE = """Your role is to help them understand each other better. \
You are not a therapist, not a mediator, and not a judge. \
You are a wise friend who listens carefully and asks good questions."""

_SECTION_BOUNDARIES = """\
You must NEVER:
- Recommend ending the relationship
- Take sides between partners
- Diagnose mental health conditions
- Provide therapy or clinical advice
- Share one partner's private messages with the other
- Make promises about outcomes
- Use clinical or psychological terminology
- If someone discloses abuse or self-harm, respond ONLY with crisis resources (988 Suicide & Crisis Lifeline, National Domestic Violence Hotline: 1-800-799-7233)"""

_SECTION_COACHING_STYLE = """\
How you communicate:
- Speak like a calm, wise friend — never like a textbook
- Ask questions more than give answers
- Acknowledge feelings before offering perspectives
- Use {user_name} and {partner_name}'s names naturally
- Keep responses 2–4 short paragraphs maximum
- One topic per exchange
- End with a gentle question or prompt"""

_SECTION_SAFETY = """\
Safety rules:
- If the conversation becomes about abuse, violence, or self-harm: stop coaching immediately and provide crisis resources only
- Never encourage deception or manipulation
- Never validate harmful behavior
- Always speak to both partners' humanity, even when one is frustrated"""

_SECTION_CONVERSATION_STYLE = """\
Conversation guidelines:
- Validate before redirecting
- If the user seems upset, slow down and reflect back what you're hearing
- Be curious, not certain
- Prefer "I wonder if..." over "You should..."
- Prefer "What do you think would happen if..." over "Here's what to do..."
- When giving perspective, acknowledge uncertainty"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def build_prompt_package(context: PromptContext) -> PromptPackage:
    """Build a complete PromptPackage from a PromptContext.

    Assembles the system prompt from relationship context, builds the
    message list from conversation history (trimmed to budget), and
    packages everything with model configuration from config.

    Args:
        context: The fully-built PromptContext (relationship + conversation + message + history).

    Returns:
        An immutable PromptPackage ready for LLM submission.
    """
    system_prompt = _build_system_prompt(context.relationship, context.conversation)
    messages = _build_messages(context.message_history, context.user_message, context.conversation)

    return PromptPackage(
        system_prompt=system_prompt,
        messages=messages,
        model=COACH_MODEL,
        max_tokens=COACH_MAX_TOKENS,
        temperature=COACH_TEMPERATURE,
    )


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt Assembly
# ─────────────────────────────────────────────────────────────────────────────


def _build_system_prompt(relationship: RelationshipContext, conversation: ConversationContext) -> str:
    """Assemble the full system prompt from independent sections."""
    sections: List[str] = [
        _build_identity_section(relationship),
        _SECTION_ROLE,
        _build_relationship_context_section(relationship),
        _build_conversation_memory_section(conversation),
        _SECTION_BOUNDARIES,
        _SECTION_COACHING_STYLE.format(
            user_name=relationship.user_name,
            partner_name=relationship.partner_name,
        ),
        _SECTION_SAFETY,
        _SECTION_CONVERSATION_STYLE,
    ]

    # Filter empty sections and join with double newlines
    return "\n\n".join(s for s in sections if s.strip())


def _build_identity_section(relationship: RelationshipContext) -> str:
    """Build the identity/opening section with names."""
    return _SECTION_IDENTITY.format(
        user_name=relationship.user_name,
        partner_name=relationship.partner_name,
    )


def _build_relationship_context_section(relationship: RelationshipContext) -> str:
    """Build the 'what you know' section from relationship data."""
    parts: List[str] = ["What you know about this relationship:"]

    # Compatibility overview
    if relationship.overall_score > 0:
        parts.append(f"- Overall compatibility: {relationship.overall_score:.0f}/100")

    # Strengths
    if relationship.top_strengths:
        strengths = ", ".join(relationship.top_strengths)
        parts.append(f"- Key strengths: {strengths}")

    # Challenges
    if relationship.top_challenges:
        challenges = ", ".join(relationship.top_challenges)
        parts.append(f"- Growth areas: {challenges}")

    # Journey
    if relationship.current_week > 0:
        parts.append(f"- Journey: Week {relationship.current_week}, phase: {relationship.journey_phase}")
        parts.append(f"- Weekly reflections completed: {relationship.total_reflections}")

    # Recent insight
    if relationship.recent_insight:
        parts.append(f"- Recent pattern: {relationship.recent_insight}")

    # Weekly sync
    if relationship.weekly_sync_status:
        sync_descriptions = {
            "SYNCED": "Both partners experienced the week similarly",
            "GROWING": "Both partners report positive trends",
            "MISALIGNED": "Partners experienced the week differently",
        }
        desc = sync_descriptions.get(relationship.weekly_sync_status, relationship.weekly_sync_status)
        parts.append(f"- This week together: {desc}")

    # Active challenges
    if relationship.active_challenges:
        parts.append("- Currently working on:")
        for challenge in relationship.active_challenges[:3]:
            parts.append(f"  • {challenge}")

    # Completed plans
    if relationship.completed_plans > 0:
        parts.append(f"- Improvement plans completed: {relationship.completed_plans}")

    # Dimension summaries (compact)
    if relationship.dimension_summaries:
        parts.append("- Dimension insights:")
        for dim_name, summary in list(relationship.dimension_summaries.items())[:5]:
            parts.append(f"  • {dim_name}: {summary}")

    return "\n".join(parts)


def _build_conversation_memory_section(conversation: ConversationContext) -> str:
    """Build the conversation memory section from previous topics and summary."""
    parts: List[str] = []

    if conversation.last_summary:
        parts.append(f"Previous conversation summary: {conversation.last_summary}")

    if conversation.previous_topics:
        topics = ", ".join(conversation.previous_topics[:5])
        parts.append(f"Topics discussed before: {topics}")

    if not parts:
        return ""

    return "Conversation memory:\n" + "\n".join(f"- {p}" for p in parts)


# ─────────────────────────────────────────────────────────────────────────────
# Message Building
# ─────────────────────────────────────────────────────────────────────────────


def _build_messages(
    history: List[MessageRecord],
    user_message: str,
    conversation: ConversationContext,
) -> List[Dict[str, str]]:
    """Build the message list: optional summary + trimmed history + current message.

    Order:
      1. Conversation summary (if present, as first user context message)
      2. Conversation history (oldest → newest, trimmed to budget)
      3. Current user message

    Never mutates the input history list.
    """
    messages: List[Dict[str, str]] = []

    # 1. Include conversation summary as context (if present and conversation is resuming)
    if conversation.last_summary and conversation.turn_count > 0:
        messages.append({
            "role": "user",
            "content": f"[Context from our previous conversation: {conversation.last_summary}]",
        })
        messages.append({
            "role": "assistant",
            "content": "I remember. How can I help today?",
        })

    # 2. Trim and include history
    trimmed_history = _trim_history(history)
    for record in trimmed_history:
        messages.append({"role": record.role, "content": record.content})

    # 3. Current user message (always included, never trimmed)
    messages.append({"role": "user", "content": user_message})

    return messages


def _trim_history(history: List[MessageRecord]) -> List[MessageRecord]:
    """Trim conversation history to fit within token budget.

    Removes oldest messages first. Never removes all messages —
    keeps at least the most recent exchange if budget allows.
    """
    if not history:
        return []

    # Sort by turn number ascending (oldest first)
    sorted_history = sorted(history, key=lambda m: m.turn_number)

    # Estimate total token usage
    total_chars = sum(len(m.content) for m in sorted_history)
    budget_chars = HISTORY_MAX_TOKENS * _CHARS_PER_TOKEN

    if total_chars <= budget_chars:
        return sorted_history

    # Trim from the oldest until within budget
    trimmed: List[MessageRecord] = []
    remaining_chars = budget_chars

    # Build from newest to oldest, then reverse
    for message in reversed(sorted_history):
        msg_chars = len(message.content)
        if remaining_chars >= msg_chars:
            trimmed.append(message)
            remaining_chars -= msg_chars
        else:
            break

    # Reverse to restore chronological order
    trimmed.reverse()
    return trimmed
