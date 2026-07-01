# -*- coding: utf-8 -*-
"""Unit tests for the AI Relationship Coach Prompt Engine (J7-D)."""

from __future__ import annotations

from kiro.coach.prompt_engine import build_prompt_package
from kiro.coach.types import (
    ConversationContext,
    ConversationStatus,
    MessageRecord,
    PromptContext,
    PromptPackage,
    RelationshipContext,
)
from kiro.coach.config import COACH_MODEL, COACH_MAX_TOKENS, COACH_TEMPERATURE


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _relationship(
    user_name: str = "Alice",
    partner_name: str = "Bob",
    overall_score: float = 72.5,
    **kwargs,
) -> RelationshipContext:
    return RelationshipContext(user_name=user_name, partner_name=partner_name, overall_score=overall_score, **kwargs)


def _conversation(
    conversation_id: str = "conv-1",
    turn_count: int = 0,
    last_summary: str = None,
    previous_topics: list = None,
) -> ConversationContext:
    return ConversationContext(
        conversation_id=conversation_id,
        status=ConversationStatus.ACTIVE,
        turn_count=turn_count,
        started_at="2026-07-01T10:00:00Z",
        previous_topics=previous_topics or [],
        last_summary=last_summary,
    )


def _context(
    relationship: RelationshipContext = None,
    conversation: ConversationContext = None,
    user_message: str = "How can we communicate better?",
    history: list = None,
) -> PromptContext:
    return PromptContext(
        relationship=relationship or _relationship(),
        conversation=conversation or _conversation(),
        user_message=user_message,
        message_history=history or [],
    )


def _message(role: str, content: str, turn: int) -> MessageRecord:
    return MessageRecord(role=role, content=content, turn_number=turn, created_at="2026-07-01T10:00:00Z")


# ─────────────────────────────────────────────────────────────────────────────
# Package Creation
# ─────────────────────────────────────────────────────────────────────────────


class TestPackageCreation:
    """build_prompt_package produces a valid PromptPackage."""

    def test_returns_prompt_package(self):
        """Output is a PromptPackage."""
        pkg = build_prompt_package(_context())
        assert isinstance(pkg, PromptPackage)

    def test_model_from_config(self):
        """Model comes from config."""
        pkg = build_prompt_package(_context())
        assert pkg.model == COACH_MODEL

    def test_max_tokens_from_config(self):
        """Max tokens comes from config."""
        pkg = build_prompt_package(_context())
        assert pkg.max_tokens == COACH_MAX_TOKENS

    def test_temperature_from_config(self):
        """Temperature comes from config."""
        pkg = build_prompt_package(_context())
        assert pkg.temperature == COACH_TEMPERATURE

    def test_system_prompt_non_empty(self):
        """System prompt is always non-empty."""
        pkg = build_prompt_package(_context())
        assert len(pkg.system_prompt) > 100

    def test_messages_non_empty(self):
        """Messages always contains at least the user message."""
        pkg = build_prompt_package(_context())
        assert len(pkg.messages) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt Assembly
# ─────────────────────────────────────────────────────────────────────────────


class TestSystemPrompt:
    """System prompt is assembled correctly from relationship context."""

    def test_contains_user_name(self):
        """System prompt includes user name."""
        pkg = build_prompt_package(_context(relationship=_relationship(user_name="Sarah")))
        assert "Sarah" in pkg.system_prompt

    def test_contains_partner_name(self):
        """System prompt includes partner name."""
        pkg = build_prompt_package(_context(relationship=_relationship(partner_name="Raj")))
        assert "Raj" in pkg.system_prompt

    def test_contains_boundaries(self):
        """System prompt includes safety boundaries."""
        pkg = build_prompt_package(_context())
        assert "NEVER" in pkg.system_prompt
        assert "ending the relationship" in pkg.system_prompt.lower() or "recommend ending" in pkg.system_prompt.lower()

    def test_contains_coaching_style(self):
        """System prompt includes coaching style guidance."""
        pkg = build_prompt_package(_context())
        assert "question" in pkg.system_prompt.lower()

    def test_includes_score_when_present(self):
        """System prompt includes compatibility score."""
        pkg = build_prompt_package(_context(relationship=_relationship(overall_score=72.5)))
        assert "72" in pkg.system_prompt or "73" in pkg.system_prompt

    def test_includes_strengths(self):
        """System prompt includes top strengths."""
        rel = _relationship(top_strengths=["Communication Style", "Love Language"])
        pkg = build_prompt_package(_context(relationship=rel))
        assert "Communication Style" in pkg.system_prompt

    def test_includes_challenges(self):
        """System prompt includes growth areas."""
        rel = _relationship(top_challenges=["Conflict Style"])
        pkg = build_prompt_package(_context(relationship=rel))
        assert "Conflict Style" in pkg.system_prompt

    def test_includes_journey_info(self):
        """System prompt includes journey week and phase."""
        rel = _relationship(current_week=8, journey_phase="BUILDING")
        pkg = build_prompt_package(_context(relationship=rel))
        assert "Week 8" in pkg.system_prompt
        assert "BUILDING" in pkg.system_prompt

    def test_includes_insight(self):
        """System prompt includes recent insight."""
        rel = _relationship(recent_insight="Emotional safety improving.")
        pkg = build_prompt_package(_context(relationship=rel))
        assert "Emotional safety improving" in pkg.system_prompt

    def test_includes_sync_status(self):
        """System prompt includes weekly sync status."""
        rel = _relationship(weekly_sync_status="MISALIGNED")
        pkg = build_prompt_package(_context(relationship=rel))
        assert "differently" in pkg.system_prompt.lower()

    def test_includes_active_challenges(self):
        """System prompt includes active improvement plan challenges."""
        rel = _relationship(active_challenges=["The pursuit-distance cycle"])
        pkg = build_prompt_package(_context(relationship=rel))
        assert "pursuit-distance" in pkg.system_prompt

    def test_includes_dimension_summaries(self):
        """System prompt includes dimension summaries."""
        rel = _relationship(dimension_summaries={"Attachment Style": "Strong bond."})
        pkg = build_prompt_package(_context(relationship=rel))
        assert "Strong bond" in pkg.system_prompt

    def test_no_score_when_zero(self):
        """System prompt omits score line when score is 0."""
        rel = _relationship(overall_score=0.0)
        pkg = build_prompt_package(_context(relationship=rel))
        assert "compatibility: 0" not in pkg.system_prompt.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Message Ordering
# ─────────────────────────────────────────────────────────────────────────────


class TestMessageOrdering:
    """Messages are ordered correctly."""

    def test_user_message_is_last(self):
        """Current user message is always the last message."""
        ctx = _context(user_message="What should we talk about?")
        pkg = build_prompt_package(ctx)
        assert pkg.messages[-1]["role"] == "user"
        assert pkg.messages[-1]["content"] == "What should we talk about?"

    def test_history_before_current(self):
        """History messages come before current user message."""
        history = [
            _message("user", "Hello", 1),
            _message("assistant", "Hi there!", 2),
        ]
        ctx = _context(history=history, user_message="Follow up")
        pkg = build_prompt_package(ctx)
        assert pkg.messages[-1]["content"] == "Follow up"
        assert pkg.messages[-3]["content"] == "Hello"
        assert pkg.messages[-2]["content"] == "Hi there!"

    def test_history_chronological(self):
        """History is in chronological order (oldest first)."""
        history = [
            _message("assistant", "Response 2", 4),
            _message("user", "Question 2", 3),
            _message("assistant", "Response 1", 2),
            _message("user", "Question 1", 1),
        ]
        ctx = _context(history=history, user_message="Question 3")
        pkg = build_prompt_package(ctx)
        # Excluding current message, history should be sorted by turn
        history_msgs = pkg.messages[:-1]
        assert history_msgs[0]["content"] == "Question 1"
        assert history_msgs[1]["content"] == "Response 1"
        assert history_msgs[2]["content"] == "Question 2"
        assert history_msgs[3]["content"] == "Response 2"

    def test_empty_history(self):
        """Empty history results in just the user message."""
        ctx = _context(history=[], user_message="First message")
        pkg = build_prompt_package(ctx)
        assert len(pkg.messages) == 1
        assert pkg.messages[0] == {"role": "user", "content": "First message"}


# ─────────────────────────────────────────────────────────────────────────────
# Summary Inclusion
# ─────────────────────────────────────────────────────────────────────────────


class TestSummaryInclusion:
    """Conversation summary is included when present and conversation is resuming."""

    def test_summary_included_when_resuming(self):
        """Summary appears as context when turn_count > 0."""
        conv = _conversation(turn_count=5, last_summary="We discussed communication.")
        ctx = _context(conversation=conv)
        pkg = build_prompt_package(ctx)
        # Summary should be injected before history
        assert any("previous conversation" in m["content"].lower() for m in pkg.messages)

    def test_no_summary_on_fresh_conversation(self):
        """No summary injection on fresh conversation (turn_count=0)."""
        conv = _conversation(turn_count=0, last_summary="Old summary.")
        ctx = _context(conversation=conv)
        pkg = build_prompt_package(ctx)
        assert not any("previous conversation" in m["content"].lower() for m in pkg.messages)

    def test_no_summary_when_none(self):
        """No summary injection when last_summary is None."""
        conv = _conversation(turn_count=5, last_summary=None)
        ctx = _context(conversation=conv)
        pkg = build_prompt_package(ctx)
        assert not any("previous conversation" in m["content"].lower() for m in pkg.messages)

    def test_previous_topics_in_system_prompt(self):
        """Previous topics appear in system prompt memory section."""
        conv = _conversation(previous_topics=["communication", "trust"])
        ctx = _context(conversation=conv)
        pkg = build_prompt_package(ctx)
        assert "communication" in pkg.system_prompt
        assert "trust" in pkg.system_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Token Budgeting / History Trimming
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenBudget:
    """History is trimmed to fit within token budget."""

    def test_short_history_untrimmed(self):
        """Short history fits within budget and is preserved completely."""
        history = [_message("user", "short", i) for i in range(3)]
        ctx = _context(history=history)
        pkg = build_prompt_package(ctx)
        # 3 history + 1 current = 4
        assert len(pkg.messages) == 4

    def test_long_history_trimmed(self):
        """Very long history gets trimmed (oldest messages removed)."""
        # Create history that exceeds HISTORY_MAX_TOKENS (4000 tokens ≈ 16000 chars)
        long_content = "x" * 5000  # ~1250 tokens each
        history = [_message("user", long_content, i) for i in range(20)]
        ctx = _context(history=history)
        pkg = build_prompt_package(ctx)
        # Should have fewer messages than original 20 + 1 current
        assert len(pkg.messages) < 21

    def test_trimmed_preserves_newest(self):
        """Trimming removes oldest, keeps newest."""
        long_content = "x" * 5000
        history = [
            _message("user", long_content, 1),
            _message("assistant", long_content, 2),
            _message("user", long_content, 3),
            _message("assistant", long_content, 4),
            _message("user", "recent short message", 5),
        ]
        ctx = _context(history=history)
        pkg = build_prompt_package(ctx)
        # The newest short message should be preserved
        history_contents = [m["content"] for m in pkg.messages[:-1]]
        assert "recent short message" in history_contents

    def test_current_message_never_trimmed(self):
        """Current user message is never removed regardless of budget."""
        long_content = "x" * 20000
        history = [_message("user", long_content, i) for i in range(5)]
        ctx = _context(history=history, user_message="Important question")
        pkg = build_prompt_package(ctx)
        assert pkg.messages[-1]["content"] == "Important question"


# ─────────────────────────────────────────────────────────────────────────────
# Determinism & Immutability
# ─────────────────────────────────────────────────────────────────────────────


class TestDeterminismAndImmutability:
    """Output is deterministic and inputs are never mutated."""

    def test_deterministic(self):
        """Same input always produces same output."""
        ctx = _context(
            relationship=_relationship(
                top_strengths=["A", "B"],
                active_challenges=["C"],
                recent_insight="Test insight",
            ),
            history=[_message("user", "hello", 1), _message("assistant", "hi", 2)],
        )
        pkg1 = build_prompt_package(ctx)
        pkg2 = build_prompt_package(ctx)
        assert pkg1.system_prompt == pkg2.system_prompt
        assert pkg1.messages == pkg2.messages
        assert pkg1.model == pkg2.model
        assert pkg1.max_tokens == pkg2.max_tokens
        assert pkg1.temperature == pkg2.temperature

    def test_output_is_frozen(self):
        """PromptPackage is immutable."""
        pkg = build_prompt_package(_context())
        try:
            pkg.system_prompt = "hacked"  # type: ignore
            assert False, "Should raise"
        except (AttributeError, TypeError):
            pass

    def test_input_history_not_mutated(self):
        """Original history list is never mutated."""
        history = [_message("user", "test", 1)]
        original_len = len(history)
        build_prompt_package(_context(history=history))
        assert len(history) == original_len
