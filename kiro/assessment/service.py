# -*- coding: utf-8 -*-
"""Assessment business logic (F2A) — start, answer, progress.

All DB operations use the service-role pool (bypasses RLS) because the
assessment module needs to read questions (admin-only via RLS) and write
answers with pre-computed scores (which requires server-side score lookup).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .exceptions import (
    AssessmentAlreadyCompletedError,
    AssessmentNotFoundError,
    InvalidQuestionError,
)
from .schemas import AnswerItem


async def get_or_create_assessment(
    pool: Any, user_id: str
) -> Tuple[dict, bool]:
    """
    Return existing in-progress assessment or create a new one.

    Returns:
        (assessment_dict, created): assessment data and whether it was newly created.
    """
    async with pool.acquire() as conn:
        # Check for existing in-progress
        row = await conn.fetchrow(
            """
            SELECT id, status, started_at, created_at
            FROM public.assessments
            WHERE user_id = $1 AND status = 'in_progress'
            LIMIT 1
            """,
            user_id,
        )

        if row:
            # Count answers
            count = await conn.fetchval(
                "SELECT count(*) FROM public.answers WHERE assessment_id = $1",
                row["id"],
            )
            return {
                "assessment_id": str(row["id"]),
                "status": row["status"],
                "started_at": row["started_at"].isoformat(),
                "progress": {"answered": count, "total": 68},
            }, False

        # Create new assessment
        new_row = await conn.fetchrow(
            """
            INSERT INTO public.assessments (user_id, assessment_type, status)
            VALUES ($1, 'core_compatibility', 'in_progress')
            RETURNING id, status, started_at
            """,
            user_id,
        )
        return {
            "assessment_id": str(new_row["id"]),
            "status": new_row["status"],
            "started_at": new_row["started_at"].isoformat(),
            "progress": {"answered": 0, "total": 68},
        }, True


async def get_questions(pool: Any) -> List[dict]:
    """
    Fetch all active questions ordered by order_index.

    Returns client-safe question data (no scores, weights, or sub-scales exposed).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category, order_index, text, answer_options
            FROM public.questions
            WHERE active = true
            ORDER BY order_index
            """
        )

    questions = []
    for row in rows:
        import json

        options_raw = row["answer_options"]
        if isinstance(options_raw, str):
            options_raw = json.loads(options_raw)

        # Strip scores from options — client only sees text + index
        options = [
            {"text": opt["text"], "index": i}
            for i, opt in enumerate(options_raw)
        ]

        questions.append({
            "id": row["id"],
            "category": row["category"],
            "order_index": row["order_index"],
            "text": row["text"],
            "answer_options": options,
        })

    return questions


async def submit_answers(
    pool: Any,
    user_id: str,
    assessment_id: str,
    answers: List[AnswerItem],
) -> dict:
    """
    Submit one or more answers to an in-progress assessment.

    Computes scores server-side and UPSERTs into the answers table.
    Returns the number of accepted answers and updated progress.
    """
    async with pool.acquire() as conn:
        # Validate assessment ownership and status
        assessment = await conn.fetchrow(
            """
            SELECT id, status, user_id
            FROM public.assessments
            WHERE id = $1
            """,
            assessment_id,
        )

        if not assessment or str(assessment["user_id"]) != user_id:
            raise AssessmentNotFoundError()

        if assessment["status"] == "completed":
            raise AssessmentAlreadyCompletedError()

        if assessment["status"] != "in_progress":
            raise AssessmentNotFoundError()

        # Fetch question metadata for score computation
        question_ids = [a.question_id for a in answers]
        question_rows = await conn.fetch(
            """
            SELECT id, answer_options, reverse_scored
            FROM public.questions
            WHERE id = ANY($1) AND active = true
            """,
            question_ids,
        )

        question_map: Dict[str, dict] = {
            row["id"]: row for row in question_rows
        }

        # Validate all question IDs exist
        for answer in answers:
            if answer.question_id not in question_map:
                raise InvalidQuestionError(answer.question_id)

        # Compute scores and upsert answers
        import json

        for answer in answers:
            q = question_map[answer.question_id]
            options = q["answer_options"]
            if isinstance(options, str):
                options = json.loads(options)

            raw_score = options[answer.selected_option_index]["score"]

            # Apply reverse scoring
            if q["reverse_scored"]:
                score = 6 - raw_score
            else:
                score = raw_score

            await conn.execute(
                """
                INSERT INTO public.answers (assessment_id, question_id, selected_option_index, score)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (assessment_id, question_id) DO UPDATE SET
                    selected_option_index = EXCLUDED.selected_option_index,
                    score = EXCLUDED.score,
                    answered_at = now()
                """,
                assessment_id,
                answer.question_id,
                answer.selected_option_index,
                score,
            )

        # Count total answers for progress
        count = await conn.fetchval(
            "SELECT count(*) FROM public.answers WHERE assessment_id = $1",
            assessment_id,
        )

    return {
        "accepted": len(answers),
        "progress": {"answered": count, "total": 68},
    }


async def get_progress(pool: Any, user_id: str, assessment_id: Optional[str] = None) -> dict:
    """
    Get assessment progress. If no assessment_id provided, returns current in-progress.
    """
    async with pool.acquire() as conn:
        if assessment_id:
            row = await conn.fetchrow(
                """
                SELECT id, status, started_at, user_id
                FROM public.assessments
                WHERE id = $1
                """,
                assessment_id,
            )
            if not row or str(row["user_id"]) != user_id:
                raise AssessmentNotFoundError()
        else:
            row = await conn.fetchrow(
                """
                SELECT id, status, started_at
                FROM public.assessments
                WHERE user_id = $1 AND status = 'in_progress'
                LIMIT 1
                """,
                user_id,
            )
            if not row:
                raise AssessmentNotFoundError()

        count = await conn.fetchval(
            "SELECT count(*) FROM public.answers WHERE assessment_id = $1",
            row["id"],
        )

    return {
        "assessment_id": str(row["id"]),
        "status": row["status"],
        "started_at": row["started_at"].isoformat(),
        "progress": {"answered": count, "total": 68},
    }


async def complete_assessment(
    pool: Any,
    user_id: str,
    assessment_id: str,
    question_cache: List[dict],
) -> dict:
    """
    Complete an assessment: validate, score, and generate profile atomically.

    This function runs inside a single transaction (using asyncpg's transaction
    context manager for auto-rollback on any exception).

    Args:
        pool: The privileged DB pool.
        user_id: User's UUID from JWT.
        assessment_id: The assessment to complete.
        question_cache: Pre-loaded question metadata (all active questions).

    Returns:
        dict with assessment_id, status, completed_at, score, profile_generated.

    Raises:
        AssessmentNotFoundError: assessment doesn't exist or isn't owned by user.
        AssessmentAlreadyCompletedError: assessment already completed.
        AssessmentIncompleteError: fewer than required answers.
        ScoringError: scoring pipeline failed.
    """
    from .exceptions import AssessmentIncompleteError
    from .scoring import score_assessment
    from .profile_gen import upsert_profile

    total_questions = len(question_cache)

    async with pool.acquire() as conn:
        # Use transaction context manager for auto-rollback (EC-2 audit recommendation)
        async with conn.transaction():
            # Step 1: Lock assessment row (prevents concurrent completion)
            assessment = await conn.fetchrow(
                """
                SELECT id, status, user_id
                FROM public.assessments
                WHERE id = $1
                FOR UPDATE
                """,
                assessment_id,
            )

            if not assessment or str(assessment["user_id"]) != user_id:
                raise AssessmentNotFoundError()

            if assessment["status"] == "completed":
                raise AssessmentAlreadyCompletedError()

            if assessment["status"] != "in_progress":
                raise AssessmentNotFoundError()

            # Step 2: Fetch answers INSIDE transaction (EC-1 audit recommendation)
            answer_rows = await conn.fetch(
                """
                SELECT question_id, score, selected_option_index
                FROM public.answers
                WHERE assessment_id = $1
                """,
                assessment_id,
            )

            # Step 3: Validate completeness
            if len(answer_rows) < total_questions:
                missing = total_questions - len(answer_rows)
                raise AssessmentIncompleteError(missing)

            # Step 4: Score (pure computation, no I/O)
            answers_for_scoring = [
                {
                    "question_id": row["question_id"],
                    "score": row["score"],
                    "selected_option_index": row["selected_option_index"],
                }
                for row in answer_rows
            ]

            try:
                scoring_result = score_assessment(answers_for_scoring, question_cache)
            except Exception as exc:
                from .exceptions import AssessmentError
                raise AssessmentError(
                    "SCORING_ERROR",
                    "Unable to generate results. Please try again.",
                    500,
                ) from exc

            # Step 5: Post-scoring validation
            _validate_scoring_result(scoring_result)

            # Step 6: Update assessment status
            completed_row = await conn.fetchrow(
                """
                UPDATE public.assessments
                SET status = 'completed', completed_at = now(), score = $2
                WHERE id = $1
                RETURNING completed_at
                """,
                assessment_id,
                scoring_result.overall_score,
            )

            # Step 7: UPSERT profile
            is_new_profile = await upsert_profile(
                conn, user_id, assessment_id, scoring_result
            )

    # Transaction committed successfully
    return {
        "assessment_id": str(assessment_id),
        "status": "completed",
        "completed_at": completed_row["completed_at"].isoformat(),
        "score": scoring_result.overall_score,
        "profile_generated": True,
    }


def _validate_scoring_result(result) -> None:
    """
    Post-scoring defensive validation. Raises if scoring produced invalid data.
    """
    from .constants import TIE_BREAK_ORDER
    from .exceptions import AssessmentError

    if len(result.dimensions) != 7:
        raise AssessmentError(
            "SCORING_ERROR",
            f"Expected 7 dimensions, got {len(result.dimensions)}",
            500,
        )

    for category, dim in result.dimensions.items():
        if category not in TIE_BREAK_ORDER:
            raise AssessmentError(
                "SCORING_ERROR",
                f"Unknown dimension: {category}",
                500,
            )
        if dim.type not in TIE_BREAK_ORDER[category]:
            raise AssessmentError(
                "SCORING_ERROR",
                f"Invalid type '{dim.type}' for {category}",
                500,
            )
        if not (0 <= dim.score <= 100):
            raise AssessmentError(
                "SCORING_ERROR",
                f"Score out of range for {category}: {dim.score}",
                500,
            )
        if not (0 <= dim.strength <= 100):
            raise AssessmentError(
                "SCORING_ERROR",
                f"Strength out of range for {category}: {dim.strength}",
                500,
            )

    if not (0 <= result.overall_score <= 100):
        raise AssessmentError(
            "SCORING_ERROR",
            f"Overall score out of range: {result.overall_score}",
            500,
        )
