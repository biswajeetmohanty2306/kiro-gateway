# -*- coding: utf-8 -*-
"""Compatibility-specific exceptions (F5C)."""

from __future__ import annotations


class CompatibilityError(Exception):
    """Base exception for compatibility operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NoPartnerError(CompatibilityError):
    """User has no accepted partner connection."""

    def __init__(self) -> None:
        super().__init__("NO_PARTNER", "You need an accepted partner connection first", 400)


class PartnerNoProfileError(CompatibilityError):
    """Partner has not completed their assessment."""

    def __init__(self) -> None:
        super().__init__("PARTNER_NO_PROFILE", "Your partner hasn't completed their assessment yet", 400)


class UserNoProfileError(CompatibilityError):
    """Current user has not completed their assessment."""

    def __init__(self) -> None:
        super().__init__("USER_NO_PROFILE", "You need to complete your assessment first", 400)


class ReportNotFoundError(CompatibilityError):
    """No compatibility report exists."""

    def __init__(self) -> None:
        super().__init__("REPORT_NOT_FOUND", "No compatibility report found", 404)


class PlanNotFoundError(CompatibilityError):
    """Improvement plan not found."""

    def __init__(self) -> None:
        super().__init__("PLAN_NOT_FOUND", "Improvement plan not found", 404)
