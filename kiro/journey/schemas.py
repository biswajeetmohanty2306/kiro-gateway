# -*- coding: utf-8 -*-
"""Journey Pydantic schemas (J2).

Request/response models for the Journey API.
Synchronized with the frozen service layer output.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ─── Request Schemas ─────────────────────────────────────────────────────────


class ReflectionAnswer(BaseModel):
    """A single answer within a reflection submission."""

    question_id: str = Field(..., description="ID of the question being answered")
    answer: str = Field(..., min_length=1, max_length=1000, description="User's response")


class SubmitReflectionRequest(BaseModel):
    """Request body for submitting a weekly reflection."""

    responses: List[ReflectionAnswer] = Field(
        ..., min_length=1, max_length=5, description="Answers to reflection questions"
    )


# ─── Response Schemas ────────────────────────────────────────────────────────


class JourneyStateResponse(BaseModel):
    """Current journey state for the user."""

    active: bool = Field(..., description="Whether a journey is active")
    current_week: int = Field(default=0, description="Current week number (0 if inactive)")
    journey_started_at: Optional[str] = Field(default=None, description="ISO timestamp when journey began")
    total_reflections: int = Field(default=0, description="Total reflections completed")
    last_reflection_at: Optional[str] = Field(default=None, description="ISO timestamp of last reflection")
    this_week_submitted: bool = Field(default=False, description="Whether this week's reflection is done")
    journey_phase: Literal["EARLY", "BUILDING", "GROWING", "ESTABLISHED"] = Field(
        default="EARLY", description="Current journey phase based on reflection count"
    )
    user_name: str = Field(default="", description="User's display name")
    partner_name: str = Field(default="", description="Partner's display name")


class QuestionOption(BaseModel):
    """Options for scale-type questions."""

    min_label: str = ""
    max_label: str = ""
    min_value: int = 1
    max_value: int = 5


class ReflectionQuestionResponse(BaseModel):
    """A reflection question for the user to answer."""

    id: str
    text: str
    type: str  # scale, open, yes_no
    options: Optional[QuestionOption] = None


class QuestionsResponse(BaseModel):
    """Response containing this week's reflection questions."""

    week_number: int
    questions: List[ReflectionQuestionResponse]
    already_submitted: bool = False


class ReflectionSubmissionResponse(BaseModel):
    """Response after successfully submitting a weekly reflection."""

    id: str = Field(..., description="UUID of the created reflection")
    week_number: int = Field(..., description="Journey week number for this reflection")
    week_start: str = Field(..., description="ISO date of the Monday this reflection represents")
    created_at: str = Field(..., description="ISO timestamp when the reflection was stored")
    message: str = Field(..., description="Confirmation message")


class HistoryEntry(BaseModel):
    """A single historical reflection entry."""

    id: str
    week_number: int
    week_start: str
    responses: list
    created_at: str


class HistoryResponse(BaseModel):
    """Response containing reflection history."""

    reflections: List[HistoryEntry]
    total: int
