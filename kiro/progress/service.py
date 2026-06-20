# -*- coding: utf-8 -*-
"""Progress tracking service (F6B).

Provides event recording, streak management, milestone awarding,
and overview/history queries.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from .types import (
    MILESTONES,
    POINTS_PLAN_COMPLETED,
    POINTS_ASSESSMENT_COMPLETED,
    POINTS_PARTNER_CONNECTED,
    POINTS_REPORT_GENERATED,
    POINTS_STREAK_7_DAY,
    EVENT_PLAN_COMPLETED,
    EVENT_STREAK_MAINTAINED,
    EVENT_MILESTONE_REACHED,
)

logger = logging.getLogger(__name__)


async def record_progress_event(
    pool: Any,
    user_id: str,
    event_type: str,
    points: int,
    connection_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """
    Record a progress event and return the event ID.

    This is the core write function — all point-earning activities flow through here.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.progress_events (user_id, connection_id, event_type, points, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id
            """,
            user_id,
            connection_id,
            event_type,
            points,
            json.dumps(metadata or {}),
        )
        return str(row["id"])


async def update_streak(pool: Any, user_id: str) -> dict:
    """
    Update the user's streak based on today's date.

    Logic:
    - If last_active_date is today → no-op (already counted)
    - If last_active_date is yesterday → increment streak
    - Otherwise → reset streak to 1

    Returns the updated streak state.
    """
    today = date.today()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, current_streak, longest_streak, last_active_date FROM public.streaks WHERE user_id = $1",
            user_id,
        )

        if not row:
            # First activity ever — create streak row
            await conn.execute(
                """
                INSERT INTO public.streaks (user_id, current_streak, longest_streak, last_active_date)
                VALUES ($1, 1, 1, $2)
                """,
                user_id,
                today,
            )
            return {"current_streak": 1, "longest_streak": 1, "is_new_day": True}

        last_active = row["last_active_date"]
        current = row["current_streak"]
        longest = row["longest_streak"]

        if last_active == today:
            # Already counted today
            return {"current_streak": current, "longest_streak": longest, "is_new_day": False}

        if last_active == today - timedelta(days=1):
            # Consecutive day — increment
            new_current = current + 1
        else:
            # Gap — reset
            new_current = 1

        new_longest = max(longest, new_current)

        await conn.execute(
            """
            UPDATE public.streaks
            SET current_streak = $2, longest_streak = $3, last_active_date = $4, updated_at = now()
            WHERE user_id = $1
            """,
            user_id,
            new_current,
            new_longest,
            today,
        )

        return {"current_streak": new_current, "longest_streak": new_longest, "is_new_day": True}


async def award_milestone(
    pool: Any,
    user_id: str,
    milestone_key: str,
    connection_id: Optional[str] = None,
) -> bool:
    """
    Award a milestone if not already earned. Returns True if newly awarded.

    Uses INSERT ... ON CONFLICT DO NOTHING for idempotency.
    """
    if milestone_key not in MILESTONES:
        logger.warning("Unknown milestone key: %s", milestone_key)
        return False

    definition = MILESTONES[milestone_key]

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO public.milestones (user_id, connection_id, milestone_key, title, description, icon)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, milestone_key) DO NOTHING
            """,
            user_id,
            connection_id,
            milestone_key,
            definition["title"],
            definition["description"],
            definition["icon"],
        )
        # asyncpg returns "INSERT 0 1" on success, "INSERT 0 0" on conflict
        return result == "INSERT 0 1"


async def evaluate_milestones(
    pool: Any,
    user_id: str,
    connection_id: Optional[str] = None,
) -> list[str]:
    """
    Evaluate which milestones the user qualifies for and award any new ones.

    Returns a list of newly awarded milestone keys.
    """
    awarded = []

    async with pool.acquire() as conn:
        # Check what's already earned
        existing = await conn.fetch(
            "SELECT milestone_key FROM public.milestones WHERE user_id = $1",
            user_id,
        )
        earned_keys = {row["milestone_key"] for row in existing}

        # first_assessment: user has a completed assessment
        if "first_assessment" not in earned_keys:
            has_assessment = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM public.assessments WHERE user_id = $1 AND status = 'completed')",
                user_id,
            )
            if has_assessment:
                if await award_milestone(pool, user_id, "first_assessment", connection_id):
                    awarded.append("first_assessment")

        # first_partner: user has an accepted partner connection
        if "first_partner" not in earned_keys:
            has_partner = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM public.partner_connections
                    WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
                )
                """,
                user_id,
            )
            if has_partner:
                if await award_milestone(pool, user_id, "first_partner", connection_id):
                    awarded.append("first_partner")

        # first_report: user has a compatibility report
        if "first_report" not in earned_keys:
            has_report = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM public.compatibility_reports cr
                    JOIN public.partner_connections pc ON pc.id = cr.connection_id
                    WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1)
                )
                """,
                user_id,
            )
            if has_report:
                if await award_milestone(pool, user_id, "first_report", connection_id):
                    awarded.append("first_report")

        # first_plan_complete: user has at least 1 completed plan
        if "first_plan_complete" not in earned_keys:
            has_plan = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM public.progress_events
                    WHERE user_id = $1 AND event_type = 'plan_completed'
                )
                """,
                user_id,
            )
            if has_plan:
                if await award_milestone(pool, user_id, "first_plan_complete", connection_id):
                    awarded.append("first_plan_complete")

        # all_plans_complete: all plans in current report are completed
        if "all_plans_complete" not in earned_keys:
            all_complete = await conn.fetchval(
                """
                SELECT CASE
                    WHEN COUNT(*) = 0 THEN false
                    ELSE COUNT(*) = COUNT(*) FILTER (WHERE ip.completed = true)
                END
                FROM public.improvement_plans ip
                JOIN public.compatibility_reports cr ON cr.id = ip.report_id
                JOIN public.partner_connections pc ON pc.id = cr.connection_id
                WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1) AND pc.status = 'accepted'
                """,
                user_id,
            )
            if all_complete:
                if await award_milestone(pool, user_id, "all_plans_complete", connection_id):
                    awarded.append("all_plans_complete")

        # seven_day_streak: current streak >= 7
        if "seven_day_streak" not in earned_keys:
            streak_row = await conn.fetchrow(
                "SELECT current_streak FROM public.streaks WHERE user_id = $1",
                user_id,
            )
            if streak_row and streak_row["current_streak"] >= 7:
                if await award_milestone(pool, user_id, "seven_day_streak", connection_id):
                    awarded.append("seven_day_streak")

    return awarded


async def on_plan_completed(
    pool: Any,
    user_id: str,
    plan_id: str,
    connection_id: Optional[str] = None,
) -> dict:
    """
    Hook called when an improvement plan is completed.

    Records event, updates streak, evaluates milestones.
    Returns summary of what happened.
    """
    # 1. Record progress event
    event_id = await record_progress_event(
        pool,
        user_id,
        EVENT_PLAN_COMPLETED,
        POINTS_PLAN_COMPLETED,
        connection_id=connection_id,
        metadata={"plan_id": plan_id},
    )

    # 2. Update streak
    streak = await update_streak(pool, user_id)

    # 3. Check for 7-day streak bonus
    if streak["is_new_day"] and streak["current_streak"] > 0 and streak["current_streak"] % 7 == 0:
        await record_progress_event(
            pool, user_id, EVENT_STREAK_MAINTAINED, POINTS_STREAK_7_DAY,
            connection_id=connection_id,
            metadata={"streak_days": streak["current_streak"]},
        )

    # 4. Evaluate milestones
    new_milestones = await evaluate_milestones(pool, user_id, connection_id)

    return {
        "event_id": event_id,
        "points": POINTS_PLAN_COMPLETED,
        "streak": streak,
        "new_milestones": new_milestones,
    }


async def get_progress_overview(pool: Any, user_id: str) -> dict:
    """
    Get the user's progress overview.

    Returns relationship health proxy, weekly/lifetime points, streak, plan count, milestones.
    """
    async with pool.acquire() as conn:
        # Lifetime points
        lifetime = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM public.progress_events WHERE user_id = $1",
            user_id,
        )

        # Weekly points (last 7 days)
        weekly = await conn.fetchval(
            """
            SELECT COALESCE(SUM(points), 0) FROM public.progress_events
            WHERE user_id = $1 AND created_at >= now() - interval '7 days'
            """,
            user_id,
        )

        # Current streak
        streak_row = await conn.fetchrow(
            "SELECT current_streak, longest_streak FROM public.streaks WHERE user_id = $1",
            user_id,
        )
        current_streak = streak_row["current_streak"] if streak_row else 0

        # Completed plans count
        completed_plans = await conn.fetchval(
            """
            SELECT COUNT(*) FROM public.progress_events
            WHERE user_id = $1 AND event_type = 'plan_completed'
            """,
            user_id,
        )

        # Milestones unlocked
        milestones_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.milestones WHERE user_id = $1",
            user_id,
        )

        # Relationship health (compatibility score if available)
        report_score = await conn.fetchval(
            """
            SELECT cr.overall_score
            FROM public.compatibility_reports cr
            JOIN public.partner_connections pc ON pc.id = cr.connection_id
            WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1) AND pc.status = 'accepted'
            LIMIT 1
            """,
            user_id,
        )
        relationship_health = float(report_score) if report_score else 0

    return {
        "relationship_health": relationship_health,
        "weekly_points": weekly,
        "lifetime_points": lifetime,
        "current_streak": current_streak,
        "completed_plans": completed_plans,
        "milestones_unlocked": milestones_count,
    }


async def get_progress_history(pool: Any, user_id: str, limit: int = 20) -> dict:
    """Get recent progress events as an activity timeline."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, event_type, points, metadata, created_at
            FROM public.progress_events
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )

    activities = []
    for row in rows:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        activities.append({
            "id": str(row["id"]),
            "event_type": row["event_type"],
            "points": row["points"],
            "metadata": metadata,
            "created_at": row["created_at"].isoformat(),
        })

    return {"activities": activities, "total": len(activities)}


async def get_milestones(pool: Any, user_id: str) -> dict:
    """Get all earned milestones for the user."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT milestone_key, title, description, icon, earned_at
            FROM public.milestones
            WHERE user_id = $1
            ORDER BY earned_at DESC
            """,
            user_id,
        )

    milestones = []
    for row in rows:
        milestones.append({
            "key": row["milestone_key"],
            "title": row["title"],
            "description": row["description"],
            "icon": row["icon"],
            "earned_at": row["earned_at"].isoformat(),
        })

    return {"milestones": milestones, "total": len(milestones)}
