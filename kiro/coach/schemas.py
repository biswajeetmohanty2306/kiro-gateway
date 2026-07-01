# -*- coding: utf-8 -*-
"""AI Relationship Coach Pydantic schemas (J7-H).

Request/response models for the Coach API.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Request Schemas ─────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    """Request body for sending a message to the coach."""

    message: str = Field(..., min_length=1, max_length=2000, description="User's message")


# ─── Response Schemas ────────────────────────────────────────────────────────


class StartConversationResponse(BaseModel):
    """Response after starting a new conversation."""

    conversation_id: str
    status: str
    greeting: str
    started_at: str


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    conversation_id: Optional[str] = None
    response: str
    turn_number: int
    safety_action: Optional[str] = None


class ConversationMessage(BaseModel):
    """A single message in conversation history."""

    role: str
    content: str
    turn_number: int


class GetConversationResponse(BaseModel):
    """Response for getting a conversation with messages."""

    id: str
    status: str
    turn_count: int
    started_at: str
    messages: List[ConversationMessage]


class ConversationListItem(BaseModel):
    """A conversation in the list view."""

    id: str
    status: str
    turn_count: int
    started_at: str


class ListConversationsResponse(BaseModel):
    """Response for listing conversations."""

    conversations: List[ConversationListItem]


class CompleteConversationResponse(BaseModel):
    """Response after completing a conversation."""

    conversation_id: str
    status: str
