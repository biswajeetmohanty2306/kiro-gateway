# -*- coding: utf-8 -*-
"""Progress tracking API router (F6B).

Endpoints:
  GET  /api/progress/overview     — Get progress summary
  GET  /api/progress/history      — Get activity timeline
  GET  /api/progress/milestones   — Get earned milestones
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .service import get_milestones, get_progress_history, get_progress_overview

router = APIRouter(prefix="/api/progress", tags=["Progress"])


def _get_pool(request: Request):
    return request.app.state.supabase_auth._audit_pool


def _get_user_id(user) -> str:
    return user.user_id


@router.get("/overview")
async def progress_overview(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get the user's progress overview. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_progress_overview(pool, _get_user_id(user))


@router.get("/history")
async def progress_history(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get recent activity timeline. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_progress_history(pool, _get_user_id(user))


@router.get("/milestones")
async def progress_milestones(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get earned milestones. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_milestones(pool, _get_user_id(user))
