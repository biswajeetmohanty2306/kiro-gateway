# -*- coding: utf-8 -*-
"""Assessment-specific exceptions (F2A)."""

from __future__ import annotations


class AssessmentError(Exception):
    """Base exception for assessment operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AssessmentNotFoundError(AssessmentError):
    """Assessment does not exist or is not owned by the user."""

    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "Assessment not found", 404)


class AssessmentAlreadyCompletedError(AssessmentError):
    """Attempt to modify a completed assessment."""

    def __init__(self) -> None:
        super().__init__("ALREADY_COMPLETED", "This assessment has already been completed", 409)


class InvalidQuestionError(AssessmentError):
    """Question ID not found or inactive."""

    def __init__(self, question_id: str) -> None:
        super().__init__(
            "INVALID_QUESTION",
            f"Question not found or inactive: {question_id}",
            400,
        )


class InvalidOptionError(AssessmentError):
    """Option index out of range."""

    def __init__(self) -> None:
        super().__init__("INVALID_OPTION", "Option index must be 0–4", 400)


class AssessmentIncompleteError(AssessmentError):
    """Attempt to complete an assessment with unanswered questions."""

    def __init__(self, missing: int) -> None:
        super().__init__(
            "INCOMPLETE",
            f"Assessment has {missing} unanswered questions",
            400,
        )
        self.missing = missing
