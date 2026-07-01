# -*- coding: utf-8 -*-
"""AI Relationship Coach type definitions (J7).

All frozen dataclasses and enums for the coach module.
Pure data — no behavior, no SQL, no async, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class ConversationStatus(str, Enum):
    """Lifecycle state of a coach conversation."""

    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class SafetyAction(str, Enum):
    """What the safety layer recommends after checking content."""

    ALLOW = "allow"
    BLOCK = "block"
    REPLACE = "replace"
    REGENERATE = "regenerate"
    ESCALATE = "escalate"


# ─────────────────────────────────────────────────────────────────────────────
# Message Record
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MessageRecord:
    """A single stored message in a conversation."""

    role: str  # "user" | "assistant"
    content: str
    turn_number: int
    created_at: str  # ISO timestamp


# ─────────────────────────────────────────────────────────────────────────────
# Context Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RelationshipContext:
    """What the coach knows about this couple's relationship.

    Assembled by context_builder from existing DB data.
    Pure data — no behavior.
    """

    # Identity
    user_name: str
    partner_name: str

    # Compatibility
    overall_score: float
    top_strengths: List[str] = field(default_factory=list)
    top_challenges: List[str] = field(default_factory=list)
    dimension_summaries: Dict[str, str] = field(default_factory=dict)

    # Journey
    journey_phase: str = "EARLY"
    current_week: int = 0
    total_reflections: int = 0
    recent_insight: Optional[str] = None
    weekly_sync_status: Optional[str] = None

    # Improvement Plans
    active_challenges: List[str] = field(default_factory=list)
    completed_plans: int = 0


@dataclass(frozen=True)
class ConversationContext:
    """State of the current conversation.

    Loaded from coach_conversations + coach_messages.
    """

    conversation_id: str
    status: ConversationStatus
    turn_count: int
    started_at: str  # ISO timestamp
    previous_topics: List[str] = field(default_factory=list)
    last_summary: Optional[str] = None


@dataclass(frozen=True)
class PromptContext:
    """Complete input to the prompt engine.

    Combines relationship understanding with conversation state.
    This is the ONLY type prompt_engine.py receives.
    """

    relationship: RelationshipContext
    conversation: ConversationContext
    user_message: str
    message_history: List[MessageRecord] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Safety Decision
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SafetyDecision:
    """Result of a safety check on input or output.

    Determines whether content is allowed to proceed and what
    corrective action should be taken if not.
    """

    allowed: bool
    action: SafetyAction
    reason: Optional[str] = None
    replacement_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Prompt Package
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromptPackage:
    """Complete prompt ready for LLM submission.

    Built by prompt_engine. Consumed by provider.
    service.py passes this through without inspecting contents.
    """

    system_prompt: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    model: str = ""
    max_tokens: int = 1500
    temperature: float = 0.7
