# -*- coding: utf-8 -*-
"""Pydantic request/response schemas for the Assessment API (F2A)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# --- Request schemas ---


class AnswerItem(BaseModel):
    """A single answer submission."""

    question_id: str
    selected_option_index: int = Field(ge=0, le=4)


class SubmitAnswersRequest(BaseModel):
    """Request body for POST /assessment/answers."""

    assessment_id: str
    answers: List[AnswerItem] = Field(min_length=1, max_length=68)


class StartAssessmentRequest(BaseModel):
    """Request body for POST /assessment/start (optional)."""

    assessment_type: str = "core_compatibility"


# --- Response schemas ---


class ProgressResponse(BaseModel):
    """Assessment progress information."""

    answered: int
    total: int


class AssessmentResponse(BaseModel):
    """Response for start/progress endpoints."""

    assessment_id: str
    status: str
    started_at: str
    progress: ProgressResponse


class AnswerOptionOut(BaseModel):
    """A single answer option (client-safe — no score exposed)."""

    text: str
    index: int


class QuestionOut(BaseModel):
    """A single question (client-safe — no scoring data exposed)."""

    id: str
    category: str
    order_index: int
    text: str
    answer_options: List[AnswerOptionOut]


class QuestionsResponse(BaseModel):
    """Response for GET /assessment/questions."""

    questions: List[QuestionOut]
    total: int


class SubmitAnswersResponse(BaseModel):
    """Response for POST /assessment/answers."""

    accepted: int
    progress: ProgressResponse
