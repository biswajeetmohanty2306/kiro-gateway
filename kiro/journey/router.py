# -*- coding: utf-8 -*-
"""Journey API router (J2).

Thin HTTP layer — authentication, validation, delegation to service.
Contains zero business logic.

Endpoints:
  GET  /api/journey              — Current journey state
  GET  /api/journey/questions    — This week's reflection questions
  POST /api/journey/reflections  — Submit a weekly reflection
  GET  /api/journey/history      — Past reflections (chronological)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .schemas import (
    HistoryResponse,
    JourneyStateResponse,
    QuestionsResponse,
    ReflectionSubmissionResponse,
    SubmitReflectionRequest,
)
from .service import get_history, get_journey, get_questions, submit_reflection

router = APIRouter(prefix="/api/journey", tags=["Journey"])


def _get_pool(request: Request):
    return request.app.state.supabase_auth._audit_pool


def _get_user_id(user) -> str:
    return user.user_id


@router.get("", response_model=JourneyStateResponse)
async def journey_state(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get current journey state including week, phase, and reflection status."""
    pool = _get_pool(request)
    return await get_journey(pool, _get_user_id(user))


@router.get("/questions", response_model=QuestionsResponse)
async def journey_questions(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get this week's reflection questions (3 questions, under 2 minutes)."""
    pool = _get_pool(request)
    return await get_questions(pool, _get_user_id(user))


@router.post("/reflections", response_model=ReflectionSubmissionResponse)
async def journey_submit_reflection(
    request: Request,
    body: SubmitReflectionRequest,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Submit this week's reflection. One submission per user per week."""
    pool = _get_pool(request)
    responses = [r.model_dump() for r in body.responses]
    return await submit_reflection(pool, _get_user_id(user), responses)


@router.get("/history", response_model=HistoryResponse)
async def journey_history(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
    limit: int = Query(default=20, ge=1, le=50, description="Max reflections to return"),
):
    """Get past reflections in reverse chronological order."""
    pool = _get_pool(request)
    return await get_history(pool, _get_user_id(user), limit=limit)
