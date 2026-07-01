# -*- coding: utf-8 -*-
"""AI Relationship Coach API router (J7-H).

Thin HTTP layer — authentication, validation, delegation to service.
Contains zero business logic.

Endpoints:
  GET  /api/coach/conversations                        — List conversations
  POST /api/coach/conversations                        — Start new conversation
  GET  /api/coach/conversations/{conversation_id}      — Get conversation
  POST /api/coach/conversations/{conversation_id}/messages  — Send message
  POST /api/coach/conversations/{conversation_id}/complete  — Complete conversation
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .schemas import (
    CompleteConversationResponse,
    GetConversationResponse,
    ListConversationsResponse,
    SendMessageRequest,
    SendMessageResponse,
    StartConversationResponse,
)
from .service import (
    complete_conversation,
    get_conversation,
    list_conversations,
    send_message,
    start_conversation,
)

router = APIRouter(prefix="/api/coach", tags=["Coach"])


def _get_pool(request: Request):
    return request.app.state.supabase_auth._audit_pool


def _get_user_id(user) -> str:
    return user.user_id


@router.get("/conversations", response_model=ListConversationsResponse)
async def coach_list_conversations(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """List all coach conversations for the authenticated user."""
    pool = _get_pool(request)
    return await list_conversations(pool, _get_user_id(user))


@router.post("/conversations", response_model=StartConversationResponse)
async def coach_start_conversation(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Start a new coach conversation."""
    pool = _get_pool(request)
    return await start_conversation(pool, _get_user_id(user))


@router.get("/conversations/{conversation_id}", response_model=GetConversationResponse)
async def coach_get_conversation(
    request: Request,
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get a conversation with its full message history."""
    pool = _get_pool(request)
    return await get_conversation(pool, _get_user_id(user), conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def coach_send_message(
    request: Request,
    conversation_id: str,
    body: SendMessageRequest,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Send a message in an existing conversation."""
    pool = _get_pool(request)
    return await send_message(pool, _get_user_id(user), conversation_id, body.message)


@router.post("/conversations/{conversation_id}/complete", response_model=CompleteConversationResponse)
async def coach_complete_conversation(
    request: Request,
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Complete (end) a conversation."""
    pool = _get_pool(request)
    return await complete_conversation(pool, _get_user_id(user), conversation_id)
