# -*- coding: utf-8 -*-
"""Relationship Timeline Generator (J6).

Transforms structured journey data into a chronological timeline of
relationship events. This is the memory of the relationship — a
narrative of what has happened between two people.

Architecture:
  - Pure module: no SQL, no async, no database, no FastAPI, no service imports.
  - Deterministic: same TimelineContext always produces same timeline.
  - Events are DERIVED from existing data — no dedicated timeline table.
  - Extensible via EventType enum and immutable private milestone registries.

Inputs:
  A TimelineContext frozen dataclass containing facts pre-loaded by the
  service layer:
    journey_started_at     — when the journey began
    current_week           — the current week number
    today                  — the current date (explicitly passed for testability)
    reflections            — list of ReflectionRecord for completed reflections
    report_created_at      — when the compatibility report was generated
    connection_accepted_at — when the partnership was accepted
    insight_message        — the current insight (if any)

Outputs:
  A chronological list of TimelineEvent frozen dataclasses, from oldest to
  newest, including one "current" marker and optionally one "upcoming"
  milestone.

Extension guide:
  To add a new event type:
    1. Add to EventType enum
    2. Add to _EVENT_TYPE_SORT_PRIORITY
    3. (If milestone) Add a DurationMilestone or ReflectionMilestone to the
       appropriate private registry tuple
    4. (If custom) Add a field to TimelineContext and a builder call in
       generate_timeline()

What this module intentionally does NOT do:
  - Store events in a database (derived on demand)
  - Access the database directly (caller provides context)
  - Generate AI content
  - Track individual question answers
  - Compare partners' reflections (that's relationship_sync.py)
  - Analyze trends (that's insights.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Event Types
# ─────────────────────────────────────────────────────────────────────────────


class EventType(str, Enum):
    """Categories of timeline events.

    Adding a new type requires:
      1. Add the enum member here
      2. Add to _EVENT_TYPE_SORT_PRIORITY below
    """

    RELATIONSHIP_STARTED = "relationship_started"
    REPORT_GENERATED = "report_generated"
    JOURNEY_STARTED = "journey_started"
    REFLECTION = "reflection"
    MILESTONE_DURATION = "milestone_duration"
    MILESTONE_REFLECTIONS = "milestone_reflections"
    INSIGHT = "insight"
    CURRENT_WEEK = "current_week"
    UPCOMING = "upcoming"


# Sort priority for events that occur on the same date.
# Lower number = appears earlier in the day's events.
_EVENT_TYPE_SORT_PRIORITY: Dict[EventType, int] = {
    EventType.RELATIONSHIP_STARTED: 0,
    EventType.REPORT_GENERATED: 1,
    EventType.JOURNEY_STARTED: 2,
    EventType.MILESTONE_DURATION: 3,
    EventType.MILESTONE_REFLECTIONS: 4,
    EventType.REFLECTION: 5,
    EventType.INSIGHT: 6,
    EventType.CURRENT_WEEK: 7,
    EventType.UPCOMING: 8,
}


# ─────────────────────────────────────────────────────────────────────────────
# Event Metadata
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UpcomingMilestoneMetadata:
    """Typed metadata attached to upcoming milestone events.

    Exactly one of the two fields will be populated, indicating
    which dimension (time or reflections) drives the milestone.
    """

    days_remaining: Optional[int] = None
    reflections_remaining: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Event Model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimelineEvent:
    """A single event on the relationship timeline.

    Immutable. Once generated, cannot be accidentally mutated during rendering.

    Fields:
      event_type  — categorizes the event for rendering decisions
      title       — short human-readable label
      description — optional supporting text
      occurred_at — when the event happened (None for upcoming events)
      week_number — journey week this event belongs to (if applicable)
      is_current  — whether this represents the active moment
      metadata    — typed UpcomingMilestoneMetadata or None
    """

    event_type: EventType
    title: str
    description: str = ""
    occurred_at: Optional[date] = None
    week_number: Optional[int] = None
    is_current: bool = False
    metadata: Optional[UpcomingMilestoneMetadata] = None


# ─────────────────────────────────────────────────────────────────────────────
# Milestone Definitions
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DurationMilestone:
    """A milestone earned after a number of days on the journey."""

    days_required: int
    title: str
    description: str


@dataclass(frozen=True)
class ReflectionMilestone:
    """A milestone earned after completing a number of reflections."""

    count_required: int
    title: str
    description: str


# Private immutable registries. Append new entries to extend — never
# remove or reorder existing entries (would change historical timelines).

_DURATION_MILESTONES: Tuple[DurationMilestone, ...] = (
    DurationMilestone(days_required=7, title="1 Week Together", description="Your journey's first full week."),
    DurationMilestone(days_required=30, title="1 Month Together", description="A month of paying attention to each other."),
    DurationMilestone(days_required=90, title="3 Months Together", description="Three months of showing up. That's rare."),
    DurationMilestone(days_required=180, title="6 Months Together", description="Half a year of building understanding."),
    DurationMilestone(days_required=365, title="1 Year Together", description="A year of intentional connection."),
)

_REFLECTION_MILESTONES: Tuple[ReflectionMilestone, ...] = (
    ReflectionMilestone(count_required=1, title="First Reflection", description="The journey begins with the first honest check-in."),
    ReflectionMilestone(count_required=4, title="One Month of Reflections", description="Four weeks of showing up for each other."),
    ReflectionMilestone(count_required=8, title="Two Months of Reflections", description="Consistency is building."),
    ReflectionMilestone(count_required=12, title="Three Months of Reflections", description="Twelve weeks of paying attention. That's meaningful."),
    ReflectionMilestone(count_required=26, title="Six Months of Reflections", description="Half a year of weekly conversations about your relationship."),
    ReflectionMilestone(count_required=52, title="One Year of Reflections", description="52 weeks. A full year of understanding."),
)


# ─────────────────────────────────────────────────────────────────────────────
# Foundation Event Text Constants
# ─────────────────────────────────────────────────────────────────────────────

_TITLE_RELATIONSHIP_STARTED = "Relationship Started"
_DESC_RELATIONSHIP_STARTED = "You connected as partners."

_TITLE_REPORT_GENERATED = "Compatibility Report Generated"
_DESC_REPORT_GENERATED = "Your first shared understanding."

_TITLE_JOURNEY_STARTED = "Journey Began"
_DESC_JOURNEY_STARTED = "Weekly reflections started."

_TITLE_REFLECTION_TEMPLATE = "Week {week} Reflection"
_DESC_REFLECTION = "Weekly check-in completed."

_TITLE_INSIGHT = "Pattern Noticed"

_TITLE_CURRENT_WEEK_TEMPLATE = "Week {week}"
_DESC_CURRENT_WEEK = "This is where you are now."


# ─────────────────────────────────────────────────────────────────────────────
# Input Context
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReflectionRecord:
    """Minimal representation of a completed reflection for timeline purposes."""

    week_number: int
    created_at: date


@dataclass(frozen=True)
class TimelineContext:
    """All data needed to generate a timeline, pre-loaded by the service layer.

    The service layer is responsible for querying existing tables and
    constructing this context. The timeline module never accesses the DB.
    """

    journey_started_at: date
    current_week: int
    today: date
    reflections: List[ReflectionRecord] = field(default_factory=list)
    report_created_at: Optional[date] = None
    connection_accepted_at: Optional[date] = None
    insight_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def generate_timeline(context: TimelineContext) -> List[TimelineEvent]:
    """Generate a chronological relationship timeline from the given context.

    Returns events sorted oldest-to-newest, with a current-week marker
    and optionally one upcoming milestone.

    Args:
        context: Pre-loaded journey data (no DB access here).

    Returns:
        Ordered list of TimelineEvent objects.
    """
    events: List[TimelineEvent] = []

    events.extend(_build_foundation_events(context))
    events.extend(_build_reflection_events(context))
    events.extend(_build_duration_milestones(context))
    events.extend(_build_reflection_milestones(context))

    if context.insight_message:
        events.append(TimelineEvent(
            event_type=EventType.INSIGHT,
            title=_TITLE_INSIGHT,
            description=context.insight_message,
            occurred_at=context.today,
            week_number=context.current_week,
        ))

    events.append(TimelineEvent(
        event_type=EventType.CURRENT_WEEK,
        title=_TITLE_CURRENT_WEEK_TEMPLATE.format(week=context.current_week),
        description=_DESC_CURRENT_WEEK,
        occurred_at=context.today,
        week_number=context.current_week,
        is_current=True,
    ))

    upcoming = _build_upcoming_event(context)
    if upcoming:
        events.append(upcoming)

    events.sort(key=_event_sort_key)
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Event Builders
# ─────────────────────────────────────────────────────────────────────────────


def _build_foundation_events(context: TimelineContext) -> List[TimelineEvent]:
    """Build the one-time foundation events (connection, report, journey start)."""
    events: List[TimelineEvent] = []

    if context.connection_accepted_at:
        events.append(TimelineEvent(
            event_type=EventType.RELATIONSHIP_STARTED,
            title=_TITLE_RELATIONSHIP_STARTED,
            description=_DESC_RELATIONSHIP_STARTED,
            occurred_at=context.connection_accepted_at,
        ))

    if context.report_created_at:
        events.append(TimelineEvent(
            event_type=EventType.REPORT_GENERATED,
            title=_TITLE_REPORT_GENERATED,
            description=_DESC_REPORT_GENERATED,
            occurred_at=context.report_created_at,
        ))

    events.append(TimelineEvent(
        event_type=EventType.JOURNEY_STARTED,
        title=_TITLE_JOURNEY_STARTED,
        description=_DESC_JOURNEY_STARTED,
        occurred_at=context.journey_started_at,
        week_number=1,
    ))

    return events


def _build_reflection_events(context: TimelineContext) -> List[TimelineEvent]:
    """Build one event for each completed weekly reflection."""
    return [
        TimelineEvent(
            event_type=EventType.REFLECTION,
            title=_TITLE_REFLECTION_TEMPLATE.format(week=ref.week_number),
            description=_DESC_REFLECTION,
            occurred_at=ref.created_at,
            week_number=ref.week_number,
        )
        for ref in context.reflections
    ]


def _build_duration_milestones(context: TimelineContext) -> List[TimelineEvent]:
    """Build duration-based milestones that have been earned."""
    days_elapsed = (context.today - context.journey_started_at).days
    events: List[TimelineEvent] = []

    for milestone in _DURATION_MILESTONES:
        if days_elapsed >= milestone.days_required:
            events.append(TimelineEvent(
                event_type=EventType.MILESTONE_DURATION,
                title=milestone.title,
                description=milestone.description,
                occurred_at=context.journey_started_at + timedelta(days=milestone.days_required),
            ))

    return events


def _build_reflection_milestones(context: TimelineContext) -> List[TimelineEvent]:
    """Build reflection-count milestones that have been earned."""
    total = len(context.reflections)
    if total == 0:
        return []

    sorted_refs = sorted(context.reflections, key=lambda r: r.created_at)
    events: List[TimelineEvent] = []

    for milestone in _REFLECTION_MILESTONES:
        if total >= milestone.count_required:
            earning_ref = sorted_refs[milestone.count_required - 1]
            events.append(TimelineEvent(
                event_type=EventType.MILESTONE_REFLECTIONS,
                title=milestone.title,
                description=milestone.description,
                occurred_at=earning_ref.created_at,
                week_number=earning_ref.week_number,
            ))

    return events


def _build_upcoming_event(context: TimelineContext) -> Optional[TimelineEvent]:
    """Determine the single closest unearned milestone and build an upcoming event.

    Compares the next duration milestone vs. the next reflection milestone
    and picks whichever is estimated to arrive sooner.
    """
    days_elapsed = (context.today - context.journey_started_at).days
    total_reflections = len(context.reflections)

    next_duration = _find_next_unearned_duration(days_elapsed)
    next_reflection = _find_next_unearned_reflection(total_reflections)

    if next_duration is None and next_reflection is None:
        return None

    if next_duration and next_reflection:
        days_to_duration = next_duration.days_required - days_elapsed
        days_to_reflection = (next_reflection.count_required - total_reflections) * 7

        if days_to_duration <= days_to_reflection:
            return _duration_to_upcoming(next_duration, days_elapsed)
        else:
            return _reflection_to_upcoming(next_reflection, total_reflections)

    if next_duration:
        return _duration_to_upcoming(next_duration, days_elapsed)

    if next_reflection:
        return _reflection_to_upcoming(next_reflection, total_reflections)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Upcoming Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _find_next_unearned_duration(days_elapsed: int) -> Optional[DurationMilestone]:
    """Find the first duration milestone not yet earned."""
    for milestone in _DURATION_MILESTONES:
        if days_elapsed < milestone.days_required:
            return milestone
    return None


def _find_next_unearned_reflection(total_reflections: int) -> Optional[ReflectionMilestone]:
    """Find the first reflection milestone not yet earned."""
    for milestone in _REFLECTION_MILESTONES:
        if total_reflections < milestone.count_required:
            return milestone
    return None


def _duration_to_upcoming(milestone: DurationMilestone, days_elapsed: int) -> TimelineEvent:
    """Create an upcoming event from a duration milestone."""
    return TimelineEvent(
        event_type=EventType.UPCOMING,
        title=milestone.title,
        description=milestone.description,
        occurred_at=None,
        metadata=UpcomingMilestoneMetadata(days_remaining=milestone.days_required - days_elapsed),
    )


def _reflection_to_upcoming(milestone: ReflectionMilestone, total_reflections: int) -> TimelineEvent:
    """Create an upcoming event from a reflection milestone."""
    return TimelineEvent(
        event_type=EventType.UPCOMING,
        title=milestone.title,
        description=milestone.description,
        occurred_at=None,
        metadata=UpcomingMilestoneMetadata(reflections_remaining=milestone.count_required - total_reflections),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sorting
# ─────────────────────────────────────────────────────────────────────────────


def _event_sort_key(event: TimelineEvent) -> Tuple[date, int]:
    """Sort key for chronological ordering.

    Rules:
      - Events with occurred_at sort by date (ascending).
      - Same-day events sort by _EVENT_TYPE_SORT_PRIORITY (lower = earlier).
      - Events without occurred_at (upcoming) sort last.

    Adding a new EventType only requires adding it to _EVENT_TYPE_SORT_PRIORITY.
    The sort function itself never needs editing.
    """
    if event.occurred_at is None:
        return (date.max, _EVENT_TYPE_SORT_PRIORITY.get(event.event_type, 99))
    return (event.occurred_at, _EVENT_TYPE_SORT_PRIORITY.get(event.event_type, 99))
