# -*- coding: utf-8 -*-
"""Partner invitation API router (F4).

Endpoints:
  POST /api/partners/invite         — Generate invite code
  GET  /api/partners/invite/{code}  — Validate invite code (public)
  POST /api/partners/accept         — Accept invitation
  GET  /api/partners/status         — Get connection status
  POST /api/partners/disconnect     — Disconnect from partner
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .service import (
    accept_invite,
    create_invite,
    disconnect,
    get_status,
    validate_invite,
)

router = APIRouter(prefix="/api/partners", tags=["Partners"])


def _get_pool(request: Request):
    """Get the privileged DB pool from app state."""
    return request.app.state.supabase_auth._audit_pool


def _get_user_id(user) -> str:
    return user.user_id


class AcceptRequest(BaseModel):
    invite_code: str


@router.post("/invite")
async def partner_invite(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Generate a new partner invite code. Requires auth + onboarding."""
    pool = _get_pool(request)
    result = await create_invite(pool, _get_user_id(user))
    return result


@router.get("/invite/{code}")
async def partner_validate_invite(
    request: Request,
    code: str,
):
    """
    Validate an invite code. Public endpoint (no auth required).
    Returns inviter name if valid, 404 if not.
    """
    pool = _get_pool(request)
    result = await validate_invite(pool, code)
    if not result:
        from .exceptions import InviteNotFoundError
        raise InviteNotFoundError()
    return result


@router.post("/accept")
async def partner_accept(
    request: Request,
    body: AcceptRequest,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Accept a partner invitation. Requires auth + onboarding."""
    pool = _get_pool(request)
    result = await accept_invite(pool, _get_user_id(user), body.invite_code)
    return result


@router.get("/status")
async def partner_status(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get current partner connection status. Requires auth + onboarding."""
    pool = _get_pool(request)
    result = await get_status(pool, _get_user_id(user))
    return result


@router.post("/disconnect")
async def partner_disconnect(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Disconnect from partner. Requires auth + onboarding."""
    pool = _get_pool(request)
    result = await disconnect(pool, _get_user_id(user))
    return result
