# -*- coding: utf-8 -*-
"""Progress tracking types and constants (F6)."""

from __future__ import annotations

# Event types
EVENT_PLAN_COMPLETED = "plan_completed"
EVENT_ASSESSMENT_COMPLETED = "assessment_completed"
EVENT_PARTNER_CONNECTED = "partner_connected"
EVENT_REPORT_GENERATED = "report_generated"
EVENT_STREAK_MAINTAINED = "streak_maintained"
EVENT_MILESTONE_REACHED = "milestone_reached"
EVENT_WEEKLY_EXERCISE = "weekly_exercise"
EVENT_WEEKLY_GOAL_COMPLETED = "weekly_goal_completed"
EVENT_WEEKLY_GOALS_SWEEP = "weekly_goals_sweep"

# Point values
POINTS_PLAN_COMPLETED = 50
POINTS_ASSESSMENT_COMPLETED = 30
POINTS_PARTNER_CONNECTED = 25
POINTS_REPORT_GENERATED = 10
POINTS_STREAK_7_DAY = 10
POINTS_WEEKLY_EXERCISE = 20

# Milestone definitions (all 15)
MILESTONES = {
    # --- Journey milestones ---
    "first_assessment": {
        "title": "Self-Discovery",
        "description": "Completed your first assessment",
        "icon": "\U0001f4dd",  # 📝
        "points": 30,
    },
    "first_partner": {
        "title": "Better Together",
        "description": "Connected with your partner",
        "icon": "\U0001f465",  # 👥
        "points": 25,
    },
    "first_report": {
        "title": "Insight Unlocked",
        "description": "Generated your first compatibility report",
        "icon": "\U0001f4ca",  # 📊
        "points": 10,
    },
    # --- Plan completion progression ---
    "first_plan_complete": {
        "title": "First Step",
        "description": "Completed your first improvement plan",
        "icon": "\U0001f331",  # 🌱
        "points": 50,
    },
    "five_plans_complete": {
        "title": "Dedicated Improver",
        "description": "Completed 5 improvement plans",
        "icon": "\U0001f3af",  # 🎯
        "points": 75,
    },
    "ten_plans_complete": {
        "title": "Master Builder",
        "description": "Completed 10 improvement plans",
        "icon": "\u2b50",  # ⭐
        "points": 100,
    },
    "all_plans_complete": {
        "title": "Growth Champion",
        "description": "Completed all current improvement plans",
        "icon": "\U0001f3c6",  # 🏆
        "points": 100,
    },
    # --- Streak ladder ---
    "three_day_streak": {
        "title": "Getting Started",
        "description": "Maintained a 3-day streak",
        "icon": "\u2728",  # ✨
        "points": 5,
    },
    "seven_day_streak": {
        "title": "Week Warrior",
        "description": "Maintained a 7-day activity streak",
        "icon": "\U0001f525",  # 🔥
        "points": 10,
    },
    "fourteen_day_streak": {
        "title": "Fortnight Focus",
        "description": "Maintained a 14-day streak",
        "icon": "\U0001f4aa",  # 💪
        "points": 25,
    },
    "thirty_day_streak": {
        "title": "Monthly Momentum",
        "description": "Maintained a 30-day streak",
        "icon": "\u26a1",  # ⚡
        "points": 50,
    },
    # --- Score-based ---
    "relationship_champion": {
        "title": "Relationship Champion",
        "description": "Achieved relationship health score of 80+",
        "icon": "\U0001f496",  # 💖
        "points": 75,
    },
    "communication_master": {
        "title": "Communication Master",
        "description": "Communication dimension score 80+",
        "icon": "\U0001f4ac",  # 💬
        "points": 50,
    },
    # --- Aggregate ---
    "consistency_star": {
        "title": "Consistency Star",
        "description": "Active for 4 consecutive weeks",
        "icon": "\U0001f31f",  # 🌟
        "points": 50,
    },
    "elite_partner": {
        "title": "Elite Partner",
        "description": "Earned 500+ lifetime points",
        "icon": "\U0001f48e",  # 💎
        "points": 0,
    },
}
