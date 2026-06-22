# -*- coding: utf-8 -*-
"""Notification system (F6D).

Creates, retrieves, and manages user notifications for milestones,
goal completions, streak achievements, and other progress events.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Notification type → default icon mapping
NOTIFICATION_ICONS = {
    "milestone_unlocked": "🏆",
    "weekly_goal_completed": "✅",
    "weekly_goals_sweep": "🎉",
    "streak_reached": "🔥",
    "assessment_completed": "📝",
    "partner_connected": "👥",
    "report_generated": "📊",
}


async def create_notification(
    pool: Any,
    user_id: str,
    notification_type: str,
    title: str,
    body: str,
    icon: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """
    Create a notification for a user.

    Returns the notification ID, or None if creation fails.
    """
    resolved_icon = icon or NOTIFICATION_ICONS.get(notification_type, "🔔")

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.notifications (user_id, type, title, body, icon, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING id
                """,
                user_id,
                notification_type,
                title,
                body,
                resolved_icon,
                json.dumps(metadata or {}),
            )
            return str(row["id"])
    except Exception:
        logger.exception("Failed to create notification for user %s", user_id)
        return None


async def get_notifications(
    pool: Any,
    user_id: str,
    unread_only: bool = False,
    limit: int = 20,
) -> dict:
    """
    Get notifications for a user, ordered newest first.

    Returns notifications list and unread count.
    """
    async with pool.acquire() as conn:
        if unread_only:
            rows = await conn.fetch(
                """
                SELECT id, type, title, body, icon, metadata, read, created_at
                FROM public.notifications
                WHERE user_id = $1 AND read = false
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, type, title, body, icon, metadata, read, created_at
                FROM public.notifications
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )

        unread_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.notifications WHERE user_id = $1 AND read = false",
            user_id,
        )

    notifications = []
    for row in rows:
        meta = row["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        notifications.append({
            "id": str(row["id"]),
            "type": row["type"],
            "title": row["title"],
            "body": row["body"],
            "icon": row["icon"],
            "metadata": meta,
            "read": row["read"],
            "created_at": row["created_at"].isoformat(),
        })

    return {
        "notifications": notifications,
        "unread_count": unread_count,
    }


async def mark_notification_read(pool: Any, user_id: str, notification_id: str) -> dict:
    """
    Mark a single notification as read.

    Returns the updated state. Raises if notification not found or not owned.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.notifications
            SET read = true
            WHERE id = $1 AND user_id = $2
            RETURNING id, read
            """,
            notification_id,
            user_id,
        )

    if not row:
        from .exceptions import ProgressError
        raise ProgressError("NOT_FOUND", "Notification not found", 404)

    return {"id": str(row["id"]), "read": True}


async def mark_all_notifications_read(pool: Any, user_id: str) -> dict:
    """
    Mark all unread notifications as read for a user.

    Returns count of marked notifications.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE public.notifications
            SET read = true
            WHERE user_id = $1 AND read = false
            """,
            user_id,
        )

    # asyncpg returns "UPDATE N" where N is row count
    try:
        marked = int(result.split()[-1])
    except (ValueError, IndexError):
        marked = 0

    return {"marked": marked}


# =============================================================================
# Integration helpers — called from service.py / goals.py
# =============================================================================


async def notify_milestone_unlocked(
    pool: Any,
    user_id: str,
    milestone_key: str,
    milestone_title: str,
    milestone_icon: str,
) -> None:
    """Create a notification when a milestone is unlocked."""
    await create_notification(
        pool,
        user_id,
        "milestone_unlocked",
        f"{milestone_title}!",
        f"You unlocked: {milestone_title}",
        icon=milestone_icon,
        metadata={"milestone_key": milestone_key},
    )


async def notify_goal_completed(
    pool: Any,
    user_id: str,
    goal_type: str,
) -> None:
    """Create a notification when a weekly goal is completed."""
    await create_notification(
        pool,
        user_id,
        "weekly_goal_completed",
        "Goal Complete!",
        f"You completed your weekly goal: {goal_type.replace('_', ' ')}",
        metadata={"goal_type": goal_type},
    )


async def notify_goals_sweep(pool: Any, user_id: str) -> None:
    """Create a notification for completing all weekly goals."""
    await create_notification(
        pool,
        user_id,
        "weekly_goals_sweep",
        "Perfect Week!",
        "All weekly goals completed — bonus points earned!",
    )


async def notify_streak_reached(
    pool: Any,
    user_id: str,
    streak_days: int,
) -> None:
    """Create a notification for a streak milestone."""
    await create_notification(
        pool,
        user_id,
        "streak_reached",
        f"{streak_days}-day streak!",
        f"You've been consistent for {streak_days} days",
        metadata={"streak_days": streak_days},
    )
