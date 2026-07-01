# -*- coding: utf-8 -*-
"""AI Relationship Coach exceptions (J7).

Follows the same pattern as journey/exceptions.py and progress/exceptions.py.
"""

from __future__ import annotations


class CoachError(Exception):
    """Base exception for coach operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NoConnectionError(CoachError):
    """User has no accepted partner connection."""

    def __init__(self):
        super().__init__(
            code="NO_CONNECTION",
            message="No accepted partner connection found.",
            status_code=404,
        )


class ConversationNotFoundError(CoachError):
    """Requested conversation does not exist or does not belong to user."""

    def __init__(self):
        super().__init__(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found.",
            status_code=404,
        )


class ConversationLimitError(CoachError):
    """User has reached the maximum number of active conversations."""

    def __init__(self):
        super().__init__(
            code="CONVERSATION_LIMIT",
            message="You've reached the maximum number of active conversations.",
            status_code=409,
        )


class ConversationCompletedError(CoachError):
    """Attempting to send a message to a completed/expired conversation."""

    def __init__(self):
        super().__init__(
            code="CONVERSATION_COMPLETED",
            message="This conversation has ended.",
            status_code=409,
        )


class TurnLimitError(CoachError):
    """Conversation has reached the maximum number of turns."""

    def __init__(self):
        super().__init__(
            code="TURN_LIMIT_REACHED",
            message="This conversation has reached its limit. Start a new one to continue.",
            status_code=409,
        )


class MessageTooLongError(CoachError):
    """User message exceeds the maximum allowed length."""

    def __init__(self):
        super().__init__(
            code="MESSAGE_TOO_LONG",
            message="Your message is too long. Please keep it under 2000 characters.",
            status_code=422,
        )


class RateLimitError(CoachError):
    """User has exceeded message rate limits."""

    def __init__(self):
        super().__init__(
            code="RATE_LIMIT",
            message="You've sent too many messages. Please wait a while before trying again.",
            status_code=429,
        )


class SafetyBlockError(CoachError):
    """Message was blocked by the safety layer."""

    def __init__(self, message: str = "This message cannot be processed."):
        super().__init__(
            code="SAFETY_BLOCK",
            message=message,
            status_code=422,
        )


class ProviderError(CoachError):
    """LLM provider returned an error or is unavailable."""

    def __init__(self):
        super().__init__(
            code="PROVIDER_UNAVAILABLE",
            message="The coach is temporarily unavailable. Please try again in a moment.",
            status_code=503,
        )
