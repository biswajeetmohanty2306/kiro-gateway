# -*- coding: utf-8 -*-
"""Weekly goals system (F6D).

Generates 3 goals per user per week, tracks progress, and awards bonuses.
Goals are generated lazily on first request of the week (idempotent).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from .types import EVENT_WEEKLY_GOAL_COMPLETED, EVENT_WEEKLY_GOALS_SWEEP

logger = logging.getLogger(__name__)

# Goal type definitions
GOAL_TYPES = {
    "complete_plan": {
        "description": "Complete an improvement plan",
        "target": 1,
        "bonus_points": 15,
    },
    "maintain_streak": {
        "description": "Keep your streak alive for 3 days",
        "target": 3,
        "bonus_points": 10,
    },
    "log_activity": {
        "description": "Record at least 2 activities",
        "target": 2,
        "bonus_points": 10,
    },
}

SWEEP_BONUS = 20


def _get_week_start(d: Optional[date] = None) -> date:
    """Get the Monday of the current (or given) week."""
    today = d or date.today()
    return today - timedelta(days=today.weekday())


def _select_goals_for_user(has_incomplete_plans: bool, week_number: int) -> list[str]:
    """Select 3 goal types based on user context."""
    goals = ["maintain_streak"]

    if has_incomplete_plans:
        goals.append("complete_plan")
    else:
        goals.append("log_activity")

    # Third goal: alternate between log_activity and complete_plan
    # Keep it simple for MVP: always include log_activity as third if not already present
    if "log_activity" not in goals:
        goals.append("log_activity")
    else:
        goals.append("complete_plan")

    return goals[:3]


async def generate_weekly_goals(pool: Any, user_id: str) -> list[dict]:
    """
    Generate weekly goals for the current week if not already generated.

    Idempotent: if goals already exist for this week, returns them.
    Returns the list of goal dicts.
    """
    week_start = _get_week_start()

    async with pool.acquire() as conn:
        # Check if goals already exist for this week
        existing = await conn.fetch(
            """
            SELECT id, goal_type, target, progress, completed, completed_at, bonus_points
            FROM public.weekly_goals
            WHERE user_id = $1 AND week_start = $2
            ORDER BY created_at
            """,
            user_id,
            week_start,
        )

        if existing:
            return [
                {
                    "id": str(row["id"]),
                    "goal_type": row["goal_type"],
                    "target": row["target"],
                    "progress": row["progress"],
                    "completed": row["completed"],
                    "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                    "bonus_points": row["bonus_points"],
                }
                for row in existing
            ]

        # Determine user context for goal selection
        has_incomplete_plans = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM public.improvement_plans ip
                JOIN public.compatibility_reports cr ON cr.id = ip.report_id
                JOIN public.partner_connections pc ON pc.id = cr.connection_id
                WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1)
                  AND pc.status = 'accepted'
                  AND ip.completed = false
            )
            """,
            user_id,
        )

        # Calculate week number for rotation
        week_number = week_start.isocalendar()[1]

        # Select goal types
        goal_types = _select_goals_for_user(has_incomplete_plans, week_number)

        # Insert goals
        goals = []
        for goal_type in goal_types:
            definition = GOAL_TYPES[goal_type]
            row = await conn.fetchrow(
                """
                INSERT INTO public.weekly_goals (user_id, week_start, goal_type, target, bonus_points)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, week_start, goal_type) DO NOTHING
                RETURNING id, goal_type, target, progress, completed, completed_at, bonus_points
                """,
                user_id,
                week_start,
                goal_type,
                definition["target"],
                definition["bonus_points"],
            )
            if row:
                goals.append({
                    "id": str(row["id"]),
                    "goal_type": row["goal_type"],
                    "target": row["target"],
                    "progress": row["progress"],
                    "completed": row["completed"],
                    "completed_at": None,
                    "bonus_points": row["bonus_points"],
                })

        return goals


async def get_weekly_goals(pool: Any, user_id: str) -> dict:
    """
    Get the current week's goals, generating them if needed.

    Returns goals list + completion summary.
    """
    goals = await generate_weekly_goals(pool, user_id)
    week_start = _get_week_start()

    all_completed = len(goals) > 0 and all(g["completed"] for g in goals)

    return {
        "week_start": week_start.isoformat(),
        "goals": goals,
        "all_completed": all_completed,
        "sweep_bonus": SWEEP_BONUS,
    }


async def update_weekly_goals_progress(
    pool: Any,
    user_id: str,
    event_type: str,
    streak_days: int = 0,
) -> list[dict]:
    """
    Update progress on active weekly goals based on a new event.

    Called after recording a progress event.
    Returns list of newly completed goals (if any).

    Mapping:
    - plan_completed → advances 'complete_plan' and 'log_activity'
    - any event → advances 'log_activity'
    - streak update → advances 'maintain_streak' (if streak >= target)
    """
    week_start = _get_week_start()
    newly_completed = []

    async with pool.acquire() as conn:
        # Fetch active (not completed) goals for this week
        goals = await conn.fetch(
            """
            SELECT id, goal_type, target, progress, completed
            FROM public.weekly_goals
            WHERE user_id = $1 AND week_start = $2 AND completed = false
            """,
            user_id,
            week_start,
        )

        for goal in goals:
            should_increment = False
            new_progress = goal["progress"]

            if goal["goal_type"] == "complete_plan" and event_type == "plan_completed":
                should_increment = True
                new_progress = goal["progress"] + 1

            elif goal["goal_type"] == "log_activity":
                # Any qualifying event counts toward log_activity
                if event_type in ("plan_completed", "weekly_exercise", "assessment_completed"):
                    should_increment = True
                    new_progress = goal["progress"] + 1

            elif goal["goal_type"] == "maintain_streak":
                # Streak goal checks current streak against target
                if streak_days >= goal["target"]:
                    should_increment = True
                    new_progress = streak_days

            if should_increment:
                is_completed = new_progress >= goal["target"]
                await conn.execute(
                    """
                    UPDATE public.weekly_goals
                    SET progress = $2, completed = $3, completed_at = CASE WHEN $3 THEN now() ELSE NULL END
                    WHERE id = $1
                    """,
                    goal["id"],
                    new_progress,
                    is_completed,
                )
                if is_completed:
                    newly_completed.append({
                        "goal_type": goal["goal_type"],
                        "bonus_points": goal.get("bonus_points", 10),
                    })

    return newly_completed


async def complete_goal_rewards(
    pool: Any,
    user_id: str,
    newly_completed: list[dict],
    connection_id: Optional[str] = None,
) -> dict:
    """
    Award bonus points for newly completed goals and check for sweep bonus.
    Creates notifications for each completed goal and sweep.

    Returns points awarded and whether sweep bonus was triggered.
    """
    from .service import record_progress_event
    from .notifications import notify_goal_completed, notify_goals_sweep

    total_bonus = 0
    sweep_awarded = False

    # Award individual goal bonuses
    for goal in newly_completed:
        bonus = goal.get("bonus_points", 10)
        await record_progress_event(
            pool, user_id, EVENT_WEEKLY_GOAL_COMPLETED, bonus,
            connection_id=connection_id,
            metadata={"goal_type": goal["goal_type"]},
        )
        total_bonus += bonus
        await notify_goal_completed(pool, user_id, goal["goal_type"])

    # Check for sweep bonus (all 3 goals complete)
    if newly_completed:
        sweep_awarded = await check_goal_sweep_bonus(pool, user_id, connection_id)
        if sweep_awarded:
            total_bonus += SWEEP_BONUS
            await notify_goals_sweep(pool, user_id)

    return {
        "goals_completed": len(newly_completed),
        "bonus_points": total_bonus,
        "sweep_awarded": sweep_awarded,
    }


async def check_goal_sweep_bonus(
    pool: Any,
    user_id: str,
    connection_id: Optional[str] = None,
) -> bool:
    """
    Check if all 3 weekly goals are complete and award sweep bonus if so.

    Only awards once per week (idempotent via event check).
    Returns True if sweep bonus was awarded this call.
    """
    from .service import record_progress_event

    week_start = _get_week_start()

    async with pool.acquire() as conn:
        # Check if all goals for this week are completed
        stats = await conn.fetchrow(
            """
            SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE completed = true) as done
            FROM public.weekly_goals
            WHERE user_id = $1 AND week_start = $2
            """,
            user_id,
            week_start,
        )

        if not stats or stats["total"] == 0 or stats["done"] < stats["total"]:
            return False

        # Check if sweep bonus already awarded this week
        already_awarded = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM public.progress_events
                WHERE user_id = $1 AND event_type = $2
                  AND created_at >= $3::date::timestamptz
            )
            """,
            user_id,
            EVENT_WEEKLY_GOALS_SWEEP,
            week_start,
        )

        if already_awarded:
            return False

    # Award sweep bonus
    await record_progress_event(
        pool, user_id, EVENT_WEEKLY_GOALS_SWEEP, SWEEP_BONUS,
        connection_id=connection_id,
        metadata={"week_start": week_start.isoformat()},
    )
    return True
