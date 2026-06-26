# -*- coding: utf-8 -*-
"""Journey-specific exceptions (J2)."""

from __future__ import annotations


class JourneyError(Exception):
    """Base exception for journey operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NoConnectionError(JourneyError):
    """User has no accepted partner connection."""

    def __init__(self):
        super().__init__(
            code="NO_CONNECTION",
            message="No accepted partner connection found.",
            status_code=404,
        )


class ReflectionAlreadySubmittedError(JourneyError):
    """User already submitted a reflection this week."""

    def __init__(self):
        super().__init__(
            code="REFLECTION_ALREADY_SUBMITTED",
            message="You've already submitted your reflection for this week.",
            status_code=409,
        )
