# -*- coding: utf-8 -*-
"""Journey service (J2) — Weekly reflections and journey state.

Architecture:
  - Journey state is assumed to already exist when these methods are called.
  - JourneyState is created by compatibility/service.py after a successful
    report generation (see _initialize_journey in that module).
  - Questions rotate on a weekly calendar boundary.
  - Reflections store minimal data; question text lives in the question library.

Public API:
  get_journey(pool, user_id)             — Current journey state + phase
  get_questions(pool, user_id)           — This week's 3 reflection questions
  submit_reflection(pool, user_id, ..)   — Record a weekly reflection
  get_history(pool, user_id, limit)      — Chronological list of past reflections
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import NoConnectionError, ReflectionAlreadySubmittedError


# ─────────────────────────────────────────────────────────────────────────────
# Time Helpers (centralized for testing, scheduling, and replay)
# ─────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    """Current UTC datetime. Single source of truth for all time-dependent logic."""
    return datetime.now(timezone.utc)


def _today() -> date:
    """Current date, derived from _now(). All date logic flows through _now()."""
    return _now().date()


# ─────────────────────────────────────────────────────────────────────────────
# Display Name
# ─────────────────────────────────────────────────────────────────────────────


def _display_name(user_row) -> str:
    """Derive display name from a users table row. Fallback: email prefix → 'User'."""
    if not user_row:
        return "User"
    name = user_row.get("name") if hasattr(user_row, "get") else (user_row["name"] if user_row else None)
    if name and str(name).strip():
        return str(name).strip()
    email = user_row.get("email") if hasattr(user_row, "get") else (user_row["email"] if user_row else None)
    if email and "@" in str(email):
        return str(email).split("@")[0]
    return "User"


# ─────────────────────────────────────────────────────────────────────────────
# Connection Resolution
# ─────────────────────────────────────────────────────────────────────────────

_CONNECTION_QUERY = """
    SELECT id, inviter_id, invitee_id
    FROM public.partner_connections
    WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
    LIMIT 1
"""


async def _resolve_connection(conn, user_id: str) -> Optional[Tuple[str, str, str]]:
    """Find the user's accepted partner connection.

    Returns (connection_id, user_id, partner_id) or None.
    """
    row = await conn.fetchrow(_CONNECTION_QUERY, user_id)
    if not row:
        return None
    inviter_id = str(row["inviter_id"])
    invitee_id = str(row["invitee_id"])
    partner_id = invitee_id if inviter_id == user_id else inviter_id
    return str(row["id"]), user_id, partner_id


async def _fetch_display_names(conn, user_id: str, partner_id: str) -> Tuple[str, str]:
    """Fetch display names for user and partner."""
    user_row = await conn.fetchrow(
        "SELECT name, email FROM public.users WHERE user_id = $1", user_id
    )
    partner_row = await conn.fetchrow(
        "SELECT name, email FROM public.users WHERE user_id = $1", partner_id
    )
    return _display_name(user_row), _display_name(partner_row)


# ─────────────────────────────────────────────────────────────────────────────
# Week Calculation
# ─────────────────────────────────────────────────────────────────────────────


def _current_week_start() -> date:
    """Return the Monday of the current ISO week (calendar-aligned)."""
    today = _today()
    return today - timedelta(days=today.weekday())


def _week_number_since(started_at: datetime) -> int:
    """Calculate the current journey week number (1-indexed, calendar-aligned).

    Strategy:
      Week 1 = the partial or full calendar week containing the start date.
      Week 2 begins the following Monday.

    Example:
      - Journey starts Wednesday → Week 1 is Wed–Sun.
      - Monday after that → Week 2.

    The calculation counts how many Monday boundaries have passed since
    the journey started, then adds 1.

    Future improvement: This can evolve into a full CalendarWeek model
    without changing the public interface.
    """
    if not started_at:
        return 1

    start_day = started_at.date() if isinstance(started_at, datetime) else started_at
    today = _today()

    if today < start_day:
        return 1

    start_week_monday = start_day - timedelta(days=start_day.weekday())
    current_week_monday = today - timedelta(days=today.weekday())
    weeks_elapsed = (current_week_monday - start_week_monday).days // 7

    return max(1, weeks_elapsed + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Journey Phase
# ─────────────────────────────────────────────────────────────────────────────

_PHASE_THRESHOLDS = [
    (17, "ESTABLISHED"),
    (9, "GROWING"),
    (4, "BUILDING"),
    (0, "EARLY"),
]


def _determine_journey_phase(total_reflections: int) -> str:
    """Derive the journey phase from completed reflection count.

    Phases:
      EARLY        0–3 reflections   (first month)
      BUILDING     4–8 reflections   (months 1–2)
      GROWING      9–16 reflections  (months 2–4)
      ESTABLISHED  17+ reflections   (4+ months)

    Calculated dynamically — no database column required.
    """
    for threshold, phase in _PHASE_THRESHOLDS:
        if total_reflections >= threshold:
            return phase
    return "EARLY"


# ─────────────────────────────────────────────────────────────────────────────
# Question Library
# ─────────────────────────────────────────────────────────────────────────────

# Slot 1: Emotional Safety (always included — core metric per J1 architecture)
SAFETY_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "safety_1",
        "text": "How emotionally safe did this week feel between you?",
        "type": "scale",
        "options": {"min_label": "Not safe", "max_label": "Very safe", "min_value": 1, "max_value": 5},
    },
    {
        "id": "safety_2",
        "text": "How comfortable did you feel being yourself around your partner this week?",
        "type": "scale",
        "options": {"min_label": "Uncomfortable", "max_label": "Completely comfortable", "min_value": 1, "max_value": 5},
    },
    {
        "id": "safety_3",
        "text": "Did you feel you could share something vulnerable this week without being judged?",
        "type": "scale",
        "options": {"min_label": "Not at all", "max_label": "Absolutely", "min_value": 1, "max_value": 5},
    },
]

# Slot 2: Connection / Communication / Appreciation (rotating)
CONNECTION_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "conn_1",
        "text": "How connected did you feel to each other this week?",
        "type": "scale",
        "options": {"min_label": "Distant", "max_label": "Very connected", "min_value": 1, "max_value": 5},
    },
    {
        "id": "conn_2",
        "text": "Did you have at least one conversation this week that felt genuinely good?",
        "type": "yes_no",
    },
    {
        "id": "conn_3",
        "text": "How many evenings did you spend meaningful time together this week?",
        "type": "scale",
        "options": {"min_label": "None", "max_label": "Most evenings", "min_value": 1, "max_value": 5},
    },
    {
        "id": "conn_4",
        "text": "Did you feel heard when you shared something important this week?",
        "type": "yes_no",
    },
    {
        "id": "conn_5",
        "text": "Were there any conversations that felt unfinished this week?",
        "type": "yes_no",
    },
    {
        "id": "conn_6",
        "text": "Did you tell your partner something you appreciated about them this week?",
        "type": "yes_no",
    },
]

# Slot 3: Open-ended reflection
OPEN_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "open_1",
        "text": "One thing I noticed about us this week...",
        "type": "open",
    },
    {
        "id": "open_2",
        "text": "Something that made me feel close to my partner this week...",
        "type": "open",
    },
    {
        "id": "open_3",
        "text": "If I could change one thing about how we communicated this week, it would be...",
        "type": "open",
    },
    {
        "id": "open_4",
        "text": "A moment this week when I felt most appreciated...",
        "type": "open",
    },
    {
        "id": "open_5",
        "text": "Something I wish my partner knew about how I felt this week...",
        "type": "open",
    },
]

# Combined registry for lookup by id
_QUESTION_REGISTRY: Dict[str, Dict[str, Any]] = {}
for _q in SAFETY_QUESTIONS + CONNECTION_QUESTIONS + OPEN_QUESTIONS:
    _QUESTION_REGISTRY[_q["id"]] = _q


def get_question_by_id(question_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a question definition from the library by its stable ID."""
    return _QUESTION_REGISTRY.get(question_id)


# ─────────────────────────────────────────────────────────────────────────────
# Question Set Builder
# ─────────────────────────────────────────────────────────────────────────────


def _rotation_seed(user_id: str, week_start: date) -> int:
    """Deterministic seed for this user + week combination.

    Same user sees the same questions throughout the week.
    Different users get different rotations.
    """
    raw = f"{user_id}:{week_start.isoformat()}"
    return int(hashlib.md5(raw.encode()).hexdigest(), 16)


def build_weekly_question_set(user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """Build this week's question set: 1 safety + 1 connection + 1 open.

    Rotation strategy (designed for a future 12-week guided cycle):
      - Each pool is indexed by (seed mod pool_size).
      - The seed shifts differently per slot to reduce cross-slot correlation.
      - Current pool sizes (3 × 6 × 5) yield a 30-week natural cycle
        before exact repetition — sufficient for initial launch.

    This function is the single point of control for rotation logic.
    Future enhancements (weekly theme, intro message, estimated duration,
    encouragement text) can be added to the return value without changing
    the caller interface.
    """
    seed = _rotation_seed(user_id, week_start)

    safety_index = seed % len(SAFETY_QUESTIONS)
    connection_index = (seed >> 8) % len(CONNECTION_QUESTIONS)
    open_index = (seed >> 16) % len(OPEN_QUESTIONS)

    return [
        SAFETY_QUESTIONS[safety_index],
        CONNECTION_QUESTIONS[connection_index],
        OPEN_QUESTIONS[open_index],
    ]


def _question_set_id(questions: List[Dict[str, Any]]) -> str:
    """Generate a stable fingerprint for a particular question combination.

    Stored as metadata so we know exactly which questions were presented,
    even if the library evolves later.
    """
    ids = sorted(q["id"] for q in questions)
    return hashlib.md5(":".join(ids).encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Reflection Payload
# ─────────────────────────────────────────────────────────────────────────────

_REFLECTION_PAYLOAD_VERSION = 1  # Increment when stored schema changes


def _build_reflection_payload(
    responses: List[Dict[str, str]],
    question_set_id: str,
    submitted_at: datetime,
) -> Dict[str, Any]:
    """Build the JSONB payload stored in weekly_reflections.responses.

    Structure (forward-compatible):
      version          — schema version of this payload
      question_set_id  — fingerprint of the presented question combination
      submitted_at     — ISO timestamp (independent of DB created_at)
      answers          — list of {question_id, answer}

    Question text is resolved from the library at read time.
    Historical data remains stable if wording is refined later.
    """
    answers = [
        {"question_id": r["question_id"], "answer": r["answer"]}
        for r in responses
    ]
    return {
        "version": _REFLECTION_PAYLOAD_VERSION,
        "question_set_id": question_set_id,
        "submitted_at": submitted_at.isoformat(),
        "answers": answers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Submission Confirmation
# ─────────────────────────────────────────────────────────────────────────────

_SUBMISSION_MESSAGE = (
    "Thank you. Every reflection helps you understand "
    "your relationship a little better."
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared SQL Fragments
# ─────────────────────────────────────────────────────────────────────────────

_SQL_JOURNEY_STATE = """
    SELECT started_at
    FROM public.journey_state
    WHERE connection_id = $1 AND user_id = $2
"""

_SQL_THIS_WEEK_EXISTS = """
    SELECT EXISTS(
        SELECT 1 FROM public.weekly_reflections
        WHERE connection_id = $1 AND user_id = $2 AND week_start = $3
    )
"""

_SQL_REFLECTION_STATS = """
    SELECT COUNT(*) AS total, MAX(created_at) AS last_at
    FROM public.weekly_reflections
    WHERE connection_id = $1 AND user_id = $2
"""

_SQL_INSERT_REFLECTION = """
    INSERT INTO public.weekly_reflections
        (connection_id, user_id, week_number, week_start, responses)
    VALUES ($1, $2, $3, $4, $5::jsonb)
    RETURNING id, created_at
"""

_SQL_REFLECTION_HISTORY = """
    SELECT id, week_number, week_start, responses, created_at
    FROM public.weekly_reflections
    WHERE connection_id = $1 AND user_id = $2
    ORDER BY created_at DESC
    LIMIT $3
"""


# ─────────────────────────────────────────────────────────────────────────────
# Service Functions
# ─────────────────────────────────────────────────────────────────────────────


async def get_journey(pool: Any, user_id: str) -> Dict[str, Any]:
    """Get current journey state including phase and insight.

    Assumes journey_state row already exists for active journeys.
    Returns active=False if no connection or no journey_state row found.

    Response includes:
      active, current_week, journey_started_at, total_reflections,
      last_reflection_at, this_week_submitted, journey_phase,
      user_name, partner_name, insight
    """
    async with pool.acquire() as conn:
        resolved = await _resolve_connection(conn, user_id)
        if not resolved:
            return _inactive_journey_response("", "")

        connection_id, _, partner_id = resolved
        user_name, partner_name = await _fetch_display_names(conn, user_id, partner_id)

        state_row = await conn.fetchrow(_SQL_JOURNEY_STATE, connection_id, user_id)
        if not state_row:
            return _inactive_journey_response(user_name, partner_name)

        started_at = state_row["started_at"]
        current_week = _week_number_since(started_at)

        stats = await conn.fetchrow(_SQL_REFLECTION_STATS, connection_id, user_id)
        total_reflections = stats["total"] if stats else 0
        last_reflection_at = stats["last_at"] if stats else None

        week_start = _current_week_start()
        this_week_submitted = await conn.fetchval(
            _SQL_THIS_WEEK_EXISTS, connection_id, user_id, week_start
        )

        # Generate insight from recent reflections
        insight_data = await _build_journey_insight(conn, connection_id, user_id, total_reflections)

        # Generate weekly relationship summary (both partners' current week)
        sync_summary = await _build_weekly_sync(conn, connection_id, user_id, partner_id, week_start)

        return {
            "active": True,
            "current_week": current_week,
            "journey_started_at": started_at.isoformat() if started_at else None,
            "total_reflections": total_reflections,
            "last_reflection_at": last_reflection_at.isoformat() if last_reflection_at else None,
            "this_week_submitted": bool(this_week_submitted),
            "journey_phase": _determine_journey_phase(total_reflections),
            "user_name": user_name,
            "partner_name": partner_name,
            "insight": insight_data,
            "weekly_sync": sync_summary,
        }


async def get_questions(pool: Any, user_id: str) -> Dict[str, Any]:
    """Get this week's reflection questions.

    Returns 3 questions (1 safety + 1 connection + 1 open).
    Also indicates whether this week's reflection has already been submitted.

    Raises NoConnectionError if no accepted partnership exists.
    """
    async with pool.acquire() as conn:
        resolved = await _resolve_connection(conn, user_id)
        if not resolved:
            raise NoConnectionError()

        connection_id, _, _ = resolved
        week_start = _current_week_start()

        already_submitted = await conn.fetchval(
            _SQL_THIS_WEEK_EXISTS, connection_id, user_id, week_start
        )

        state_row = await conn.fetchrow(_SQL_JOURNEY_STATE, connection_id, user_id)
        current_week = _week_number_since(state_row["started_at"]) if state_row else 1

        questions = build_weekly_question_set(user_id, week_start)

        return {
            "week_number": current_week,
            "questions": questions,
            "already_submitted": bool(already_submitted),
        }


async def submit_reflection(pool: Any, user_id: str, responses: List[Dict[str, str]]) -> Dict[str, Any]:
    """Submit a weekly reflection.

    Validates:
      - User has an active connection
      - User hasn't already submitted this week

    Stores a versioned payload with question_id + answer only.
    Question text is NOT stored — resolved from the library at read time.

    Raises:
      NoConnectionError: No accepted partnership
      ReflectionAlreadySubmittedError: Already submitted this week
    """
    async with pool.acquire() as conn:
        resolved = await _resolve_connection(conn, user_id)
        if not resolved:
            raise NoConnectionError()

        connection_id, _, _ = resolved
        week_start = _current_week_start()

        already_exists = await conn.fetchval(
            _SQL_THIS_WEEK_EXISTS, connection_id, user_id, week_start
        )
        if already_exists:
            raise ReflectionAlreadySubmittedError()

        state_row = await conn.fetchrow(_SQL_JOURNEY_STATE, connection_id, user_id)
        current_week = _week_number_since(state_row["started_at"]) if state_row else 1

        questions = build_weekly_question_set(user_id, week_start)
        question_set_fingerprint = _question_set_id(questions)
        submitted_at = _now()
        payload = _build_reflection_payload(responses, question_set_fingerprint, submitted_at)

        row = await conn.fetchrow(
            _SQL_INSERT_REFLECTION,
            connection_id,
            user_id,
            current_week,
            week_start,
            json.dumps(payload),
        )

        return {
            "id": str(row["id"]),
            "week_number": current_week,
            "week_start": week_start.isoformat(),
            "created_at": row["created_at"].isoformat(),
            "message": _SUBMISSION_MESSAGE,
        }


async def get_history(pool: Any, user_id: str, limit: int = 20) -> Dict[str, Any]:
    """Get chronological list of past reflections (most recent first).

    Enriches stored answers with question text from the current library.
    If a question_id is no longer in the library (removed/renamed), the
    text falls back to an empty string — the answer is still preserved.
    """
    async with pool.acquire() as conn:
        resolved = await _resolve_connection(conn, user_id)
        if not resolved:
            raise NoConnectionError()

        connection_id, _, _ = resolved

        rows = await conn.fetch(
            _SQL_REFLECTION_HISTORY, connection_id, user_id, limit
        )

        reflections = [_format_history_entry(row) for row in rows]

        return {
            "reflections": reflections,
            "total": len(reflections),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Response Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _inactive_journey_response(user_name: str, partner_name: str) -> Dict[str, Any]:
    """Standard response when journey is not active."""
    return {
        "active": False,
        "current_week": 0,
        "journey_started_at": None,
        "total_reflections": 0,
        "last_reflection_at": None,
        "this_week_submitted": False,
        "journey_phase": "EARLY",
        "user_name": user_name,
        "partner_name": partner_name,
        "insight": None,
        "weekly_sync": None,
    }


async def _load_recent_reflections(conn, connection_id: str, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Load and normalize recent reflections from the database.

    Handles all SQL and JSONB parsing. Returns a list of plain Python dicts
    suitable for passing to generate_insight() (most recent first).

    Each entry: {week_number: int, responses: [{question_id, answer}]}
    """
    rows = await conn.fetch(
        _SQL_REFLECTION_HISTORY, connection_id, user_id, limit
    )

    reflections = []
    for row in rows:
        raw = row["responses"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
        reflections.append({
            "week_number": row["week_number"],
            "responses": answers,
        })

    return reflections


async def _build_journey_insight(conn, connection_id: str, user_id: str, total_reflections: int) -> Optional[Dict[str, Any]]:
    """Load reflections → normalize → generate insight.

    Orchestrates the pipeline:
      1. Load recent reflections from DB (via _load_recent_reflections)
      2. Pass normalized data to generate_insight() (pure function)
      3. Return the insight dict

    Returns the insight for insufficient data too (with a placeholder message).
    """
    from .insights import generate_insight

    if total_reflections < 3:
        return generate_insight([])

    reflections = await _load_recent_reflections(conn, connection_id, user_id)
    return generate_insight(reflections)


async def _build_weekly_sync(conn, connection_id: str, user_id: str, partner_id: str, week_start) -> Optional[Dict[str, Any]]:
    """Load both partners' current-week reflections and generate a relationship summary.

    Orchestrates:
      1. Load user's reflection for current week
      2. Load partner's reflection for current week
      3. Pass both to generate_weekly_relationship_summary() (pure function)
      4. Return the summary dict
    """
    from .relationship_sync import generate_weekly_relationship_summary

    user_answers = await _load_week_answers(conn, connection_id, user_id, week_start)
    partner_answers = await _load_week_answers(conn, connection_id, partner_id, week_start)

    return generate_weekly_relationship_summary(user_answers, partner_answers)


async def _load_week_answers(conn, connection_id: str, user_id: str, week_start) -> Optional[List[Dict[str, str]]]:
    """Load a single user's answers for a specific week. Returns None if not submitted."""
    row = await conn.fetchrow(
        """
        SELECT responses FROM public.weekly_reflections
        WHERE connection_id = $1 AND user_id = $2 AND week_start = $3
        """,
        connection_id, user_id, week_start,
    )
    if not row:
        return None

    raw = row["responses"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
    return answers


def _format_history_entry(row) -> Dict[str, Any]:
    """Format a database row into a history entry with enriched question text."""
    raw = row["responses"]
    if isinstance(raw, str):
        raw = json.loads(raw)

    # Support both v1 versioned payload and any legacy flat format
    answers = raw.get("answers", raw) if isinstance(raw, dict) else raw

    enriched = []
    for entry in answers:
        question_id = entry.get("question_id", "")
        question_def = get_question_by_id(question_id)
        enriched.append({
            "question_id": question_id,
            "question_text": question_def["text"] if question_def else "",
            "answer": entry.get("answer", ""),
        })

    return {
        "id": str(row["id"]),
        "week_number": row["week_number"],
        "week_start": row["week_start"].isoformat(),
        "responses": enriched,
        "created_at": row["created_at"].isoformat(),
    }
