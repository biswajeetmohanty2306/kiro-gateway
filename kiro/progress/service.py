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
    Creates a notification on successful award.
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
        newly_awarded = result == "INSERT 0 1"

    if newly_awarded:
        from .notifications import notify_milestone_unlocked
        await notify_milestone_unlocked(
            pool, user_id, milestone_key, definition["title"], definition["icon"]
        )

    return newly_awarded


async def evaluate_milestones(
    pool: Any,
    user_id: str,
    connection_id: Optional[str] = None,
) -> list[str]:
    """
    Evaluate which milestones the user qualifies for and award any new ones.

    Checks all 15 milestones. Returns a list of newly awarded milestone keys.
    """
    awarded = []

    async with pool.acquire() as conn:
        # Check what's already earned
        existing = await conn.fetch(
            "SELECT milestone_key FROM public.milestones WHERE user_id = $1",
            user_id,
        )
        earned_keys = {row["milestone_key"] for row in existing}

        # --- Journey milestones ---

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

        # --- Plan completion progression ---

        # first_plan_complete: 1+ plan_completed events
        if "first_plan_complete" not in earned_keys:
            plan_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.progress_events WHERE user_id = $1 AND event_type = 'plan_completed'",
                user_id,
            )
            if plan_count >= 1:
                if await award_milestone(pool, user_id, "first_plan_complete", connection_id):
                    awarded.append("first_plan_complete")

        # five_plans_complete: 5+ plan_completed events
        if "five_plans_complete" not in earned_keys:
            plan_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.progress_events WHERE user_id = $1 AND event_type = 'plan_completed'",
                user_id,
            )
            if plan_count >= 5:
                if await award_milestone(pool, user_id, "five_plans_complete", connection_id):
                    awarded.append("five_plans_complete")

        # ten_plans_complete: 10+ plan_completed events
        if "ten_plans_complete" not in earned_keys:
            plan_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.progress_events WHERE user_id = $1 AND event_type = 'plan_completed'",
                user_id,
            )
            if plan_count >= 10:
                if await award_milestone(pool, user_id, "ten_plans_complete", connection_id):
                    awarded.append("ten_plans_complete")

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

        # --- Streak ladder ---
        streak_row = await conn.fetchrow(
            "SELECT current_streak FROM public.streaks WHERE user_id = $1",
            user_id,
        )
        current_streak = streak_row["current_streak"] if streak_row else 0

        if "three_day_streak" not in earned_keys and current_streak >= 3:
            if await award_milestone(pool, user_id, "three_day_streak", connection_id):
                awarded.append("three_day_streak")

        if "seven_day_streak" not in earned_keys and current_streak >= 7:
            if await award_milestone(pool, user_id, "seven_day_streak", connection_id):
                awarded.append("seven_day_streak")

        if "fourteen_day_streak" not in earned_keys and current_streak >= 14:
            if await award_milestone(pool, user_id, "fourteen_day_streak", connection_id):
                awarded.append("fourteen_day_streak")

        if "thirty_day_streak" not in earned_keys and current_streak >= 30:
            if await award_milestone(pool, user_id, "thirty_day_streak", connection_id):
                awarded.append("thirty_day_streak")

        # --- Score-based milestones ---

        # relationship_champion: overall compatibility score >= 80
        if "relationship_champion" not in earned_keys:
            score = await conn.fetchval(
                """
                SELECT cr.overall_score
                FROM public.compatibility_reports cr
                JOIN public.partner_connections pc ON pc.id = cr.connection_id
                WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1) AND pc.status = 'accepted'
                LIMIT 1
                """,
                user_id,
            )
            if score is not None and float(score) >= 80:
                if await award_milestone(pool, user_id, "relationship_champion", connection_id):
                    awarded.append("relationship_champion")

        # communication_master: communication dimension score >= 80
        if "communication_master" not in earned_keys:
            dim_scores_raw = await conn.fetchval(
                """
                SELECT cr.dimension_scores
                FROM public.compatibility_reports cr
                JOIN public.partner_connections pc ON pc.id = cr.connection_id
                WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1) AND pc.status = 'accepted'
                LIMIT 1
                """,
                user_id,
            )
            if dim_scores_raw:
                dim_scores = dim_scores_raw if isinstance(dim_scores_raw, dict) else json.loads(dim_scores_raw)
                comm = dim_scores.get("communication_style", {})
                comm_score = comm.get("score", 0) if isinstance(comm, dict) else 0
                if comm_score >= 80:
                    if await award_milestone(pool, user_id, "communication_master", connection_id):
                        awarded.append("communication_master")

        # --- Aggregate milestones ---

        # consistency_star: activity in 4 consecutive weeks
        if "consistency_star" not in earned_keys:
            distinct_weeks = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT date_trunc('week', created_at))
                FROM public.progress_events
                WHERE user_id = $1 AND created_at >= now() - interval '28 days'
                """,
                user_id,
            )
            if distinct_weeks >= 4:
                if await award_milestone(pool, user_id, "consistency_star", connection_id):
                    awarded.append("consistency_star")

        # elite_partner: 500+ lifetime points
        if "elite_partner" not in earned_keys:
            lifetime_pts = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM public.progress_events WHERE user_id = $1",
                user_id,
            )
            if lifetime_pts >= 500:
                if await award_milestone(pool, user_id, "elite_partner", connection_id):
                    awarded.append("elite_partner")

    return awarded


async def on_plan_completed(
    pool: Any,
    user_id: str,
    plan_id: str,
    connection_id: Optional[str] = None,
) -> dict:
    """
    Hook called when an improvement plan is completed.

    Records event, updates streak, evaluates milestones, updates weekly goals.
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
        from .notifications import notify_streak_reached
        await notify_streak_reached(pool, user_id, streak["current_streak"])

    # 4. Evaluate milestones
    new_milestones = await evaluate_milestones(pool, user_id, connection_id)

    # 5. Update weekly goals
    from .goals import update_weekly_goals_progress, complete_goal_rewards
    newly_completed_goals = await update_weekly_goals_progress(
        pool, user_id, EVENT_PLAN_COMPLETED, streak_days=streak["current_streak"]
    )
    goal_rewards = {"goals_completed": 0, "bonus_points": 0, "sweep_awarded": False}
    if newly_completed_goals:
        goal_rewards = await complete_goal_rewards(pool, user_id, newly_completed_goals, connection_id)

    return {
        "event_id": event_id,
        "points": POINTS_PLAN_COMPLETED,
        "streak": streak,
        "new_milestones": new_milestones,
        "goal_rewards": goal_rewards,
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
