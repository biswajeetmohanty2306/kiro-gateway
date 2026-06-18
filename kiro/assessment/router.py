# -*- coding: utf-8 -*-
"""Assessment API router (F2A + F2C).

Endpoints:
  POST /assessment/start      — Start or resume an assessment
  GET  /assessment/questions   — Fetch all active questions
  POST /assessment/answers     — Submit answers
  GET  /assessment/progress    — Get current progress
  POST /assessment/complete    — Complete assessment, trigger scoring + profile generation
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .exceptions import AssessmentError
from .schemas import (
    AssessmentResponse,
    ProgressResponse,
    QuestionsResponse,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
)
from .service import get_or_create_assessment, get_questions, get_progress, submit_answers, complete_assessment

router = APIRouter(prefix="/assessment", tags=["Assessment"])


def _get_pool(request: Request):
    """Get the privileged DB pool from app state."""
    bundle = request.app.state.supabase_auth
    return bundle._audit_pool


def _get_user_id(user: AuthenticatedUser) -> str:
    """Extract user_id string from the authenticated user."""
    return user.user_id


@router.post("/start", response_model=AssessmentResponse, status_code=200)
async def assessment_start(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Start a new assessment or resume an existing in-progress one.

    Returns 200 with existing assessment (resume) or 201 with new assessment.
    Requires auth + onboarding (via get_current_user_profile dependency).
    """
    pool = _get_pool(request)
    user_id = _get_user_id(user)

    data, created = await get_or_create_assessment(pool, user_id)

    status_code = 201 if created else 200
    return JSONResponse(content=data, status_code=status_code)


@router.get("/questions", response_model=QuestionsResponse)
async def assessment_questions(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Fetch all active assessment questions in presentation order.

    Client-safe: scores, weights, sub-scales are NOT included.
    Requires auth + onboarding.
    """
    pool = _get_pool(request)
    questions = await get_questions(pool)

    return {
        "questions": questions,
        "total": len(questions),
    }


@router.post("/answers", response_model=SubmitAnswersResponse)
async def assessment_answers(
    request: Request,
    body: SubmitAnswersRequest,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Submit one or more answers for an in-progress assessment.

    Scores are computed server-side. UPSERT behavior allows changing answers.
    Requires auth + onboarding.
    """
    pool = _get_pool(request)
    user_id = _get_user_id(user)

    result = await submit_answers(pool, user_id, body.assessment_id, body.answers)
    return result


@router.get("/progress", response_model=AssessmentResponse)
async def assessment_progress(
    request: Request,
    assessment_id: str = None,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Get current assessment progress (answered vs total).

    If assessment_id is omitted, returns the current in-progress assessment.
    Requires auth + onboarding.
    """
    pool = _get_pool(request)
    user_id = _get_user_id(user)

    data = await get_progress(pool, user_id, assessment_id)
    return data


# --- Question cache (loaded once, shared across requests) ---
_question_cache: list = []


async def _get_question_cache(pool) -> list:
    """Load and cache question metadata for scoring."""
    global _question_cache
    if not _question_cache:
        _question_cache = await _load_questions_for_scoring(pool)
    return _question_cache


async def _load_questions_for_scoring(pool) -> list:
    """Fetch full question metadata (including scoring fields) for the engine."""
    import json

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category, sub_scale, weight, reverse_scored, answer_options
            FROM public.questions
            WHERE active = true
            ORDER BY order_index
            """
        )

    questions = []
    for row in rows:
        options = row["answer_options"]
        if isinstance(options, str):
            options = json.loads(options)
        questions.append({
            "id": row["id"],
            "category": row["category"],
            "sub_scale": row["sub_scale"],
            "weight": float(row["weight"]),
            "reverse_scored": row["reverse_scored"],
            "answer_options": options,
        })
    return questions


class CompleteRequest:
    """Simple request model for complete endpoint."""
    pass


from pydantic import BaseModel as _BaseModel


class _CompleteAssessmentRequest(_BaseModel):
    assessment_id: str


@router.post("/complete")
async def assessment_complete(
    request: Request,
    body: _CompleteAssessmentRequest,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Complete an assessment: validate all answers, score, and generate profile.

    Atomically transitions the assessment to 'completed' and UPSERTs the user's
    relationship profile. Requires all 68 questions answered.
    Requires auth + onboarding.
    """
    pool = _get_pool(request)
    user_id = _get_user_id(user)

    question_cache = await _get_question_cache(pool)

    result = await complete_assessment(pool, user_id, body.assessment_id, question_cache)
    return result


@router.get("/profile")
async def assessment_profile(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """
    Get the user's relationship profile (generated from assessment).

    Returns has_profile=true with full dimension breakdown if profile exists,
    or has_profile=false if the user hasn't completed an assessment yet.
    Requires auth + onboarding.
    """
    from .types import (
        DIMENSION_ORDER,
        DIMENSION_DISPLAY_NAMES,
        get_strength_label,
        get_type_label,
        get_type_description,
    )
    import json

    pool = _get_pool(request)
    user_id = _get_user_id(user)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.user_id, p.assessment_id, p.created_at,
                   p.attachment_style, p.communication_style, p.conflict_style,
                   p.love_language, p.financial_personality, p.lifestyle_type,
                   p.relationship_archetype, p.dimension_scores,
                   a.score as overall_score
            FROM public.profiles p
            JOIN public.assessments a ON a.id = p.assessment_id
            WHERE p.user_id = $1
            """,
            user_id,
        )

    if not row:
        return {"has_profile": False, "profile": None}

    # Parse dimension_scores JSONB
    dim_scores_raw = row["dimension_scores"]
    if isinstance(dim_scores_raw, str):
        dim_scores_raw = json.loads(dim_scores_raw)

    # Build enriched dimension response in fixed order
    dimensions = {}
    for dim_key in DIMENSION_ORDER:
        dim_data = dim_scores_raw.get(dim_key, {})
        type_key = dim_data.get("type", "unknown")
        strength = dim_data.get("strength", 0)
        score = dim_data.get("score", 0)
        sub_scores = dim_data.get("sub_scores", {})

        dimensions[dim_key] = {
            "type": type_key,
            "label": get_type_label(dim_key, type_key),
            "strength": strength,
            "strength_label": get_strength_label(strength),
            "score": score,
            "description": get_type_description(dim_key, type_key),
            "dimension_name": DIMENSION_DISPLAY_NAMES.get(dim_key, dim_key),
            "sub_scores": sub_scores,
        }

    return {
        "has_profile": True,
        "profile": {
            "user_id": str(row["user_id"]),
            "assessment_id": str(row["assessment_id"]),
            "created_at": row["created_at"].isoformat(),
            "overall_score": float(row["overall_score"]) if row["overall_score"] else 0.0,
            "dimensions": dimensions,
        },
    }
