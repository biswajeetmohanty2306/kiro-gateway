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

# Point values
POINTS_PLAN_COMPLETED = 50
POINTS_ASSESSMENT_COMPLETED = 30
POINTS_PARTNER_CONNECTED = 25
POINTS_REPORT_GENERATED = 10
POINTS_STREAK_7_DAY = 10

# Milestone definitions
MILESTONES = {
    "first_assessment": {
        "title": "Self-Discovery",
        "description": "Completed your first assessment",
        "icon": "📝",
    },
    "first_partner": {
        "title": "Better Together",
        "description": "Connected with your partner",
        "icon": "👥",
    },
    "first_report": {
        "title": "Insight Unlocked",
        "description": "Generated your first compatibility report",
        "icon": "📊",
    },
    "first_plan_complete": {
        "title": "First Step",
        "description": "Completed your first improvement plan",
        "icon": "🌱",
    },
    "all_plans_complete": {
        "title": "Growth Champion",
        "description": "Completed all improvement plans",
        "icon": "🏆",
    },
    "seven_day_streak": {
        "title": "Week Warrior",
        "description": "Maintained a 7-day activity streak",
        "icon": "🔥",
    },
}
