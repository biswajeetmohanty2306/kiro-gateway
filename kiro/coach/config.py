# -*- coding: utf-8 -*-
"""AI Relationship Coach configuration constants (J7).

All behavioral limits, model settings, and token budgets for the coach.
Grouped by concern. No external dependencies.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Model Settings
# ─────────────────────────────────────────────────────────────────────────────

COACH_MODEL: str = "claude-sonnet-4-20250514"
COACH_MAX_TOKENS: int = 1500
COACH_TEMPERATURE: float = 0.7

# ─────────────────────────────────────────────────────────────────────────────
# Token Budgets
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_MAX_TOKENS: int = 4000
HISTORY_MAX_TOKENS: int = 4000
CONTEXT_SUMMARY_MAX_TOKENS: int = 1500

# ─────────────────────────────────────────────────────────────────────────────
# Conversation Limits
# ─────────────────────────────────────────────────────────────────────────────

MAX_TURNS_PER_CONVERSATION: int = 20
MAX_ACTIVE_CONVERSATIONS: int = 5
MAX_MESSAGE_LENGTH: int = 2000
MAX_RESPONSE_LENGTH: int = 1500
CONVERSATION_EXPIRY_DAYS: int = 7
SUMMARY_TRIGGER_TURNS: int = 15  # Generate intermediate summary after N turns

# ─────────────────────────────────────────────────────────────────────────────
# Rate Limits
# ─────────────────────────────────────────────────────────────────────────────

MAX_MESSAGES_PER_DAY: int = 50
MAX_MESSAGES_PER_HOUR: int = 20

# ─────────────────────────────────────────────────────────────────────────────
# Safety
# ─────────────────────────────────────────────────────────────────────────────

MAX_REGENERATION_ATTEMPTS: int = 1
