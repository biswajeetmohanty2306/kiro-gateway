# -*- coding: utf-8 -*-
"""Journey data models (J2).

Defines internal structures for journey state and reflections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class JourneyState:
    """Current state of a couple's relationship journey."""

    connection_id: str
    user_id: str
    partner_id: str
    user_name: str
    partner_name: str
    journey_started_at: Optional[datetime] = None
    current_week: int = 1
    total_reflections: int = 0
    last_reflection_at: Optional[datetime] = None
    this_week_submitted: bool = False


@dataclass
class ReflectionQuestion:
    """A single reflection question presented to the user."""

    id: str
    text: str
    type: str  # "scale" | "open" | "yes_no"
    options: Optional[dict] = None


@dataclass
class ReflectionResponse:
    """A user's answer to a reflection question."""

    question_id: str
    answer: str  # Text for open, "1"-"5" for scale, "yes"/"no" for yes_no


@dataclass
class WeeklyReflection:
    """A completed weekly reflection."""

    id: str
    connection_id: str
    user_id: str
    week_number: int
    week_start: date
    responses: list  # list of {question_id, question_text, answer}
    created_at: datetime
