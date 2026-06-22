# -*- coding: utf-8 -*-
"""Health trends system (F6D).

Stores weekly health snapshots and provides trend calculations.
Snapshots are idempotent per user per week (UNIQUE constraint).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_week_start(d: Optional[date] = None) -> date:
    """Get the Monday of the current (or given) week."""
    today = d or date.today()
    return today - timedelta(days=today.weekday())


async def create_health_snapshot(
    pool: Any,
    user_id: str,
    connection_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Create a health snapshot for the current week.

    Idempotent: uses ON CONFLICT DO UPDATE to refresh the snapshot if one
    already exists for this week. This means re-triggering (e.g., report
    regeneration) simply updates the existing row.

    Returns the snapshot dict, or None on failure.
    """
    week_start = _get_week_start()

    try:
        async with pool.acquire() as conn:
            # Gather current stats
            compatibility_score = await conn.fetchval(
                """
                SELECT cr.overall_score
                FROM public.compatibility_reports cr
                JOIN public.partner_connections pc ON pc.id = cr.connection_id
                WHERE (pc.inviter_id = $1 OR pc.invitee_id = $1) AND pc.status = 'accepted'
                LIMIT 1
                """,
                user_id,
            )

            engagement_score = await conn.fetchval(
                """
                SELECT COALESCE(SUM(points), 0) FROM public.progress_events
                WHERE user_id = $1 AND created_at >= $2::date::timestamptz
                """,
                user_id,
                week_start,
            )

            plans_completed = await conn.fetchval(
                """
                SELECT COUNT(*) FROM public.progress_events
                WHERE user_id = $1 AND event_type = 'plan_completed'
                """,
                user_id,
            )

            streak_row = await conn.fetchrow(
                "SELECT current_streak FROM public.streaks WHERE user_id = $1",
                user_id,
            )
            streak_days = streak_row["current_streak"] if streak_row else 0

            # UPSERT snapshot
            row = await conn.fetchrow(
                """
                INSERT INTO public.health_snapshots (
                    user_id, connection_id, week_start,
                    compatibility_score, engagement_score, plans_completed, streak_days
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, week_start) DO UPDATE SET
                    connection_id = EXCLUDED.connection_id,
                    compatibility_score = EXCLUDED.compatibility_score,
                    engagement_score = EXCLUDED.engagement_score,
                    plans_completed = EXCLUDED.plans_completed,
                    streak_days = EXCLUDED.streak_days,
                    created_at = now()
                RETURNING id, week_start, compatibility_score, engagement_score, plans_completed, streak_days
                """,
                user_id,
                connection_id,
                week_start,
                compatibility_score,
                engagement_score,
                plans_completed,
                streak_days,
            )

            return {
                "id": str(row["id"]),
                "week_start": row["week_start"].isoformat(),
                "compatibility_score": float(row["compatibility_score"]) if row["compatibility_score"] else None,
                "engagement_score": row["engagement_score"],
                "plans_completed": row["plans_completed"],
                "streak_days": row["streak_days"],
            }

    except Exception:
        logger.exception("Failed to create health snapshot for user %s", user_id)
        return None


async def get_latest_snapshot(pool: Any, user_id: str) -> Optional[dict]:
    """Get the most recent health snapshot for a user."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, week_start, compatibility_score, engagement_score, plans_completed, streak_days
            FROM public.health_snapshots
            WHERE user_id = $1
            ORDER BY week_start DESC
            LIMIT 1
            """,
            user_id,
        )

    if not row:
        return None

    return {
        "id": str(row["id"]),
        "week_start": row["week_start"].isoformat(),
        "compatibility_score": float(row["compatibility_score"]) if row["compatibility_score"] else None,
        "engagement_score": row["engagement_score"],
        "plans_completed": row["plans_completed"],
        "streak_days": row["streak_days"],
    }


def calculate_trend_direction(
    current_score: Optional[float],
    previous_score: Optional[float],
) -> dict:
    """
    Calculate trend direction between two scores.

    Returns dict with direction, delta, and percentage change.
    Direction: "up", "down", or "flat".
    Flat threshold: less than 5% change.
    """
    if current_score is None or previous_score is None:
        return {
            "direction": "flat",
            "delta": 0,
            "percentage_change": 0,
        }

    delta = current_score - previous_score

    if previous_score == 0:
        # Avoid division by zero
        if delta > 0:
            return {"direction": "up", "delta": round(delta, 1), "percentage_change": 100}
        return {"direction": "flat", "delta": 0, "percentage_change": 0}

    percentage = (delta / previous_score) * 100

    if percentage > 5:
        direction = "up"
    elif percentage < -5:
        direction = "down"
    else:
        direction = "flat"

    return {
        "direction": direction,
        "delta": round(delta, 1),
        "percentage_change": round(percentage, 1),
    }


async def get_health_trends(pool: Any, user_id: str, weeks: int = 12) -> dict:
    """
    Get health trend data for the user.

    Returns weekly snapshots and trend calculations.
    If no snapshot exists for the current week, creates one lazily.
    """
    week_start = _get_week_start()

    async with pool.acquire() as conn:
        # Check if current week has a snapshot; create lazily if not
        current_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.health_snapshots WHERE user_id = $1 AND week_start = $2)",
            user_id,
            week_start,
        )

    if not current_exists:
        await create_health_snapshot(pool, user_id)

    # Fetch snapshots
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT week_start, compatibility_score, engagement_score, plans_completed, streak_days
            FROM public.health_snapshots
            WHERE user_id = $1
            ORDER BY week_start DESC
            LIMIT $2
            """,
            user_id,
            weeks,
        )

    snapshots = []
    for row in rows:
        snapshots.append({
            "week_start": row["week_start"].isoformat(),
            "compatibility_score": float(row["compatibility_score"]) if row["compatibility_score"] else None,
            "engagement_score": row["engagement_score"],
            "plans_completed": row["plans_completed"],
            "streak_days": row["streak_days"],
        })

    # Calculate trend from last 2 snapshots
    if len(snapshots) >= 2:
        current = snapshots[0]["engagement_score"]
        previous = snapshots[1]["engagement_score"]
        trend = calculate_trend_direction(current, previous)
    else:
        trend = {"direction": "flat", "delta": 0, "percentage_change": 0}

    return {
        "snapshots": snapshots,
        "total": len(snapshots),
        "trend": trend,
    }
