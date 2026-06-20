# -*- coding: utf-8 -*-
"""Compatibility report API router (F5C).

Endpoints:
  GET  /api/reports/compatibility          — Get current report
  POST /api/reports/generate               — Generate/regenerate report
  GET  /api/reports/improvement            — Get improvement plans
  POST /api/reports/improvement/{id}/complete — Mark task done
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..supabase_auth.dependencies import get_current_user_profile
from ..supabase_auth.user import AuthenticatedUser
from .service import complete_plan, generate_report, get_improvement_plans, get_report

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _get_pool(request: Request):
    return request.app.state.supabase_auth._audit_pool


def _get_user_id(user) -> str:
    return user.user_id


@router.get("/compatibility")
async def reports_compatibility(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get the current compatibility report. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_report(pool, _get_user_id(user))


@router.post("/generate")
async def reports_generate(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Generate or regenerate the compatibility report. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await generate_report(pool, _get_user_id(user))


@router.get("/improvement")
async def reports_improvement(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Get improvement plans for the current report. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await get_improvement_plans(pool, _get_user_id(user))


@router.post("/improvement/{plan_id}/complete")
async def reports_improvement_complete(
    request: Request,
    plan_id: str,
    user: AuthenticatedUser = Depends(get_current_user_profile),
):
    """Mark an improvement plan task as completed. Requires auth + onboarding."""
    pool = _get_pool(request)
    return await complete_plan(pool, _get_user_id(user), plan_id)
