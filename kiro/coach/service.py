# -*- coding: utf-8 -*-
"""AI Relationship Coach Service (J7-F).

Orchestrates the coach conversation lifecycle:
  - Loads relationship data from existing tables
  - Calls pure modules (context_builder, prompt_engine, safety)
  - Manages conversation state (create, message, complete, expire)
  - Prepares provider inputs (provider implementation is separate)

Service responsibilities:
  ✓ Load relationship data
  ✓ Call build_relationship_context()
  ✓ Build PromptContext
  ✓ Call build_prompt_package()
  ✓ Call evaluate_message()
  ✓ Manage conversation lifecycle
  ✓ Load/save conversations and messages
  ✓ Maintain turn counts

Service must NOT:
  ✗ Construct prompts directly
  ✗ Contain safety rules
  ✗ Calculate compatibility/journey
  ✗ Import FastAPI
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .config import MAX_ACTIVE_CONVERSATIONS, MAX_TURNS_PER_CONVERSATION
from .context_builder import build_relationship_context
from .exceptions import (
    ConversationCompletedError,
    ConversationLimitError,
    ConversationNotFoundError,
    NoConnectionError,
    ProviderError,
    TurnLimitError,
)
from .prompt_engine import build_prompt_package
from .safety import evaluate_message
from .types import (
    ConversationContext,
    ConversationStatus,
    MessageRecord,
    PromptContext,
    PromptPackage,
    RelationshipContext,
    SafetyAction,
    SafetyDecision,
)


# ─────────────────────────────────────────────────────────────────────────────
# SQL Constants
# ─────────────────────────────────────────────────────────────────────────────

_SQL_CONNECTION = """
    SELECT id, inviter_id, invitee_id
    FROM public.partner_connections
    WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
    LIMIT 1
"""

_SQL_USER_NAMES = """
    SELECT name, email FROM public.users WHERE user_id = $1
"""

_SQL_REPORT = """
    SELECT overall_score, dimension_scores
    FROM public.compatibility_reports
    WHERE connection_id = $1
"""

_SQL_JOURNEY_STATE = """
    SELECT started_at FROM public.journey_state
    WHERE connection_id = $1 AND user_id = $2
"""

_SQL_JOURNEY_STATS = """
    SELECT COUNT(*) AS total FROM public.weekly_reflections
    WHERE connection_id = $1 AND user_id = $2
"""

_SQL_IMPROVEMENT_PLANS = """
    SELECT dimension, severity, challenge_description, completed
    FROM public.improvement_plans ip
    JOIN public.compatibility_reports cr ON cr.id = ip.report_id
    WHERE cr.connection_id = $1
    ORDER BY ip.created_at
"""

_SQL_ACTIVE_CONVERSATIONS = """
    SELECT COUNT(*) AS total FROM public.coach_conversations
    WHERE user_id = $1 AND status = 'active'
"""

_SQL_CONVERSATION_BY_ID = """
    SELECT id, connection_id, user_id, status, context_version, context_hash,
           summary, turn_count, started_at, completed_at, created_at
    FROM public.coach_conversations
    WHERE id = $1 AND user_id = $2
"""

_SQL_CREATE_CONVERSATION = """
    INSERT INTO public.coach_conversations
        (connection_id, user_id, status, context_hash, turn_count)
    VALUES ($1, $2, 'active', $3, 0)
    RETURNING id, started_at, created_at
"""

_SQL_CONVERSATION_MESSAGES = """
    SELECT role, content, turn_number, created_at
    FROM public.coach_messages
    WHERE conversation_id = $1
    ORDER BY turn_number ASC
"""

_SQL_INSERT_MESSAGE = """
    INSERT INTO public.coach_messages (conversation_id, role, content, turn_number)
    VALUES ($1, $2, $3, $4)
    RETURNING id, created_at
"""

_SQL_INCREMENT_TURN = """
    UPDATE public.coach_conversations
    SET turn_count = turn_count + 1
    WHERE id = $1
    RETURNING turn_count
"""

_SQL_COMPLETE_CONVERSATION = """
    UPDATE public.coach_conversations
    SET status = 'completed', completed_at = now(), summary = $2
    WHERE id = $1 AND user_id = $3
    RETURNING id, status
"""

_SQL_PAST_SUMMARIES = """
    SELECT summary FROM public.coach_conversations
    WHERE user_id = $1 AND status = 'completed' AND summary IS NOT NULL
    ORDER BY completed_at DESC
    LIMIT 3
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def start_conversation(pool: Any, user_id: str) -> Dict[str, Any]:
    """Start a new coach conversation.

    Validates:
      - User has an accepted partner connection
      - User has not exceeded active conversation limit

    Returns conversation_id + context-aware greeting.
    """
    async with pool.acquire() as conn:
        connection_id, partner_id = await _resolve_connection(conn, user_id)

        # Check active conversation limit
        active_count = await conn.fetchval(_SQL_ACTIVE_CONVERSATIONS, user_id)
        if active_count >= MAX_ACTIVE_CONVERSATIONS:
            raise ConversationLimitError()

        # Load context and compute hash
        relationship = await _load_relationship_context(conn, connection_id, user_id, partner_id)
        context_hash = _compute_context_hash(relationship)

        # Create conversation
        row = await conn.fetchrow(_SQL_CREATE_CONVERSATION, connection_id, user_id, context_hash)

        return {
            "conversation_id": str(row["id"]),
            "status": "active",
            "greeting": f"Hi {relationship.user_name}. What's on your mind about your relationship?",
            "started_at": row["started_at"].isoformat(),
        }


async def send_message(pool: Any, user_id: str, conversation_id: str, message: str) -> Dict[str, Any]:
    """Send a message in an existing conversation.

    Pipeline:
      1. Load conversation → validate lifecycle
      2. Load relationship context
      3. Safety check
      4. Build PromptContext → PromptPackage
      5. Call provider
      6. Save messages + increment turn
      7. Return response
    """
    async with pool.acquire() as conn:
        # 1. Load and validate conversation
        conv_row = await _load_conversation(conn, user_id, conversation_id)
        connection_id = str(conv_row["connection_id"])
        partner_id = await _get_partner_id(conn, connection_id, user_id)

        # 2. Load relationship context
        relationship = await _load_relationship_context(conn, connection_id, user_id, partner_id)

        # 3. Safety check
        safety_decision = evaluate_message(message, relationship)
        if not safety_decision.allowed:
            return _safety_response(safety_decision, conv_row["turn_count"])

        # 4. Build prompt
        conversation_context = await _build_conversation_context(conn, conv_row, user_id)
        history = await _load_message_history(conn, conversation_id)

        prompt_context = PromptContext(
            relationship=relationship,
            conversation=conversation_context,
            user_message=message,
            message_history=history,
        )
        package = build_prompt_package(prompt_context)

        # 5. Call provider
        response_text = await _generate_ai_response(package)

        # 6. Save messages and increment turn
        new_turn = conv_row["turn_count"] + 1
        await conn.execute(_SQL_INSERT_MESSAGE, conversation_id, "user", message, new_turn)
        await conn.execute(_SQL_INSERT_MESSAGE, conversation_id, "assistant", response_text, new_turn)
        await conn.fetchval(_SQL_INCREMENT_TURN, conversation_id)

        # Check if turn limit reached → auto-complete
        if new_turn >= MAX_TURNS_PER_CONVERSATION:
            await conn.execute(
                _SQL_COMPLETE_CONVERSATION, conversation_id,
                "Conversation reached its natural conclusion.", user_id,
            )

        return {
            "conversation_id": conversation_id,
            "response": response_text,
            "turn_number": new_turn,
        }


async def get_conversation(pool: Any, user_id: str, conversation_id: str) -> Dict[str, Any]:
    """Get a conversation with its full message history."""
    async with pool.acquire() as conn:
        conv_row = await _load_conversation_readonly(conn, user_id, conversation_id)
        messages = await _load_message_history(conn, conversation_id)

        return {
            "id": str(conv_row["id"]),
            "status": conv_row["status"],
            "turn_count": conv_row["turn_count"],
            "started_at": conv_row["started_at"].isoformat(),
            "messages": [
                {"role": m.role, "content": m.content, "turn_number": m.turn_number}
                for m in messages
            ],
        }


async def list_conversations(pool: Any, user_id: str) -> Dict[str, Any]:
    """List all conversations for the user."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, turn_count, started_at, completed_at
            FROM public.coach_conversations
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            user_id,
        )

        conversations = []
        for row in rows:
            conversations.append({
                "id": str(row["id"]),
                "status": row["status"],
                "turn_count": row["turn_count"],
                "started_at": row["started_at"].isoformat(),
            })

        return {"conversations": conversations}


async def complete_conversation(pool: Any, user_id: str, conversation_id: str) -> Dict[str, Any]:
    """Explicitly complete a conversation."""
    async with pool.acquire() as conn:
        conv_row = await _load_conversation(conn, user_id, conversation_id)

        if conv_row["status"] != "active":
            raise ConversationCompletedError()

        await conn.execute(
            _SQL_COMPLETE_CONVERSATION, conversation_id,
            "Conversation completed by user.", user_id,
        )

        return {"conversation_id": conversation_id, "status": "completed"}


# ─────────────────────────────────────────────────────────────────────────────
# Private Helpers — Connection & Names
# ─────────────────────────────────────────────────────────────────────────────


async def _resolve_connection(conn, user_id: str) -> tuple:
    """Find the user's accepted partner connection. Returns (connection_id, partner_id)."""
    row = await conn.fetchrow(_SQL_CONNECTION, user_id)
    if not row:
        raise NoConnectionError()
    inviter_id = str(row["inviter_id"])
    invitee_id = str(row["invitee_id"])
    partner_id = invitee_id if inviter_id == user_id else inviter_id
    return str(row["id"]), partner_id


async def _get_partner_id(conn, connection_id: str, user_id: str) -> str:
    """Resolve partner_id from a known connection."""
    row = await conn.fetchrow(
        "SELECT inviter_id, invitee_id FROM public.partner_connections WHERE id = $1",
        connection_id,
    )
    inviter_id = str(row["inviter_id"])
    invitee_id = str(row["invitee_id"])
    return invitee_id if inviter_id == user_id else inviter_id


def _display_name(user_row) -> str:
    """Extract display name from a users table row."""
    if not user_row:
        return "User"
    name = user_row.get("name") if hasattr(user_row, "get") else user_row["name"]
    if name and str(name).strip():
        return str(name).strip()
    email = user_row.get("email") if hasattr(user_row, "get") else user_row["email"]
    if email and "@" in str(email):
        return str(email).split("@")[0]
    return "User"


# ─────────────────────────────────────────────────────────────────────────────
# Private Helpers — Context Loading
# ─────────────────────────────────────────────────────────────────────────────


async def _load_relationship_context(conn, connection_id: str, user_id: str, partner_id: str) -> RelationshipContext:
    """Load all relationship data and build context via context_builder."""
    # Names
    user_row = await conn.fetchrow(_SQL_USER_NAMES, user_id)
    partner_row = await conn.fetchrow(_SQL_USER_NAMES, partner_id)
    user_name = _display_name(user_row)
    partner_name = _display_name(partner_row)

    # Compatibility
    report_row = await conn.fetchrow(_SQL_REPORT, connection_id)
    overall_score = float(report_row["overall_score"]) if report_row else None
    dimension_scores = None
    if report_row and report_row["dimension_scores"]:
        ds = report_row["dimension_scores"]
        dimension_scores = json.loads(ds) if isinstance(ds, str) else ds

    # Journey
    journey_row = await conn.fetchrow(_SQL_JOURNEY_STATE, connection_id, user_id)
    journey_phase = None
    current_week = None
    if journey_row:
        from ..journey.service import _week_number_since, _determine_journey_phase
        current_week = _week_number_since(journey_row["started_at"])
    stats_row = await conn.fetchrow(_SQL_JOURNEY_STATS, connection_id, user_id)
    total_reflections = stats_row["total"] if stats_row else 0
    if total_reflections is not None:
        from ..journey.service import _determine_journey_phase
        journey_phase = _determine_journey_phase(total_reflections)

    # Improvement plans
    plan_rows = await conn.fetch(_SQL_IMPROVEMENT_PLANS, connection_id)
    plans = []
    for row in plan_rows:
        plans.append({
            "dimension": row["dimension"],
            "severity": row.get("severity", "medium") if hasattr(row, "get") else "medium",
            "challenge_description": row["challenge_description"] or "",
            "completed": row["completed"],
        })

    return build_relationship_context(
        user_name=user_name,
        partner_name=partner_name,
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        journey_phase=journey_phase,
        current_week=current_week,
        total_reflections=total_reflections,
        improvement_plans=plans,
    )


def _compute_context_hash(context: RelationshipContext) -> str:
    """Compute a deterministic hash of the relationship context."""
    raw = f"{context.user_name}:{context.partner_name}:{context.overall_score}:{context.journey_phase}:{context.current_week}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Private Helpers — Conversation Management
# ─────────────────────────────────────────────────────────────────────────────


async def _load_conversation(conn, user_id: str, conversation_id: str):
    """Load and validate a conversation row for WRITING (send_message, complete).

    Rejects non-active conversations and turn-limited conversations.
    """
    row = await conn.fetchrow(_SQL_CONVERSATION_BY_ID, conversation_id, user_id)
    if not row:
        raise ConversationNotFoundError()
    if row["status"] != "active":
        raise ConversationCompletedError()
    if row["turn_count"] >= MAX_TURNS_PER_CONVERSATION:
        raise TurnLimitError()
    return row


async def _load_conversation_readonly(conn, user_id: str, conversation_id: str):
    """Load a conversation row for READING (get_conversation). Allows any status."""
    row = await conn.fetchrow(_SQL_CONVERSATION_BY_ID, conversation_id, user_id)
    if not row:
        raise ConversationNotFoundError()
    return row


async def _build_conversation_context(conn, conv_row, user_id: str) -> ConversationContext:
    """Build ConversationContext from DB row + past summaries."""
    past_summaries = await conn.fetch(_SQL_PAST_SUMMARIES, user_id)
    topics = [s["summary"][:50] for s in past_summaries if s["summary"]]
    last_summary = past_summaries[0]["summary"] if past_summaries else None

    return ConversationContext(
        conversation_id=str(conv_row["id"]),
        status=ConversationStatus(conv_row["status"]),
        turn_count=conv_row["turn_count"],
        started_at=conv_row["started_at"].isoformat(),
        previous_topics=topics,
        last_summary=last_summary,
    )


async def _load_message_history(conn, conversation_id: str) -> List[MessageRecord]:
    """Load message history for a conversation."""
    rows = await conn.fetch(_SQL_CONVERSATION_MESSAGES, conversation_id)
    return [
        MessageRecord(
            role=row["role"],
            content=row["content"],
            turn_number=row["turn_number"],
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Private Helpers — Safety Response
# ─────────────────────────────────────────────────────────────────────────────


def _safety_response(decision: SafetyDecision, current_turn: int) -> Dict[str, Any]:
    """Build a response dict from a safety decision (message not processed by LLM)."""
    return {
        "conversation_id": None,
        "response": decision.replacement_message or "I'm not able to help with that.",
        "turn_number": current_turn,
        "safety_action": decision.action.value,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Provider Integration
# ─────────────────────────────────────────────────────────────────────────────


async def _generate_ai_response(package: PromptPackage) -> str:
    """Generate AI response from a PromptPackage via the provider adapter."""
    from .provider import generate_response
    return await generate_response(package)
