# -*- coding: utf-8 -*-
"""Progress tracking API router (F6B).

Endpoints:
  GET  /api/progress/overview              — Get progress summary
  GET  /api/progress/history               — Get activity timeline
  GET  /api/progress/milestones            — Get earned milestones
  GET  /api/progress/goals                 — Get weekly goals
  GET  /api/progress/notifications         — Get notifications
  POST /api/progress/notifications/{id}/read — Mark notification read
  POST /api/progress/notifications/read-all  — Mark all notifications read
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .service import get_milestones, get_progress_history, get_progress_overview
from .goals import get_weekly_goals
from .notifications import get_notifications, mark_notification_read, mark_all_notifications_read
from .trends import get_health_trends

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


@router.get("/goals")
async def progress_goals(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get current week's goals (generates if needed). Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_weekly_goals(pool, _get_user_id(user))


@router.get("/notifications")
async def progress_notifications(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
    unread: bool = Query(default=False, description="Filter to unread only"),
    limit: int = Query(default=20, ge=1, le=50, description="Max notifications to return"),
):
    """Get user notifications. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_notifications(pool, _get_user_id(user), unread_only=unread, limit=limit)


@router.post("/notifications/{notification_id}/read")
async def progress_notification_read(
    request: Request,
    notification_id: str,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Mark a notification as read. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await mark_notification_read(pool, _get_user_id(user), notification_id)


@router.post("/notifications/read-all")
async def progress_notifications_read_all(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Mark all notifications as read. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await mark_all_notifications_read(pool, _get_user_id(user))


@router.get("/trends")
async def progress_trends(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
    weeks: int = Query(default=12, ge=1, le=52, description="Number of weeks to return"),
):
    """Get health trend snapshots. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_health_trends(pool, _get_user_id(user), weeks=weeks)
