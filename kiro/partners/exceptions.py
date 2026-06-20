# -*- coding: utf-8 -*-
"""Partner-specific exceptions (F4)."""

from __future__ import annotations


class PartnerError(Exception):
    """Base exception for partner operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AlreadyConnectedError(PartnerError):
    """User already has an active partner connection."""

    def __init__(self) -> None:
        super().__init__("ALREADY_CONNECTED", "You already have an active partner connection", 409)


class InviteNotFoundError(PartnerError):
    """Invite code is invalid or expired."""

    def __init__(self) -> None:
        super().__init__("INVITE_NOT_FOUND", "Invite code is invalid or has already been used", 404)


class SelfInviteError(PartnerError):
    """User attempted to accept their own invite."""

    def __init__(self) -> None:
        super().__init__("SELF_INVITE", "You cannot accept your own invitation", 400)


class NotConnectedError(PartnerError):
    """User has no active partner connection."""

    def __init__(self) -> None:
        super().__init__("NOT_CONNECTED", "You have no active partner connection", 404)
