# -*- coding: utf-8 -*-
"""Automatic compatibility report generation triggers (F5E).

Provides a non-raising function that attempts to generate a compatibility
report when prerequisites are met (accepted connection + both profiles exist).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .engine import compute_compatibility

logger = logging.getLogger(__name__)


async def try_generate_compatibility_report(
    pool: Any,
    connection_id: str,
) -> bool:
    """
    Attempt to generate (or regenerate) a compatibility report for a connection.

    Returns True if a report was successfully generated/regenerated.
    Returns False if prerequisites are not met (missing profiles, wrong status, etc.).
    Never raises — all errors are caught and logged.
    """
    try:
        return await _do_generate(pool, connection_id)
    except Exception:
        logger.exception(
            "Failed to auto-generate compatibility report for connection %s",
            connection_id,
        )
        return False


async def _do_generate(pool: Any, connection_id: str) -> bool:
    """Core logic for auto-generating a compatibility report."""
    async with pool.acquire() as conn:
        # 1. Verify connection exists and is accepted
        connection = await conn.fetchrow(
            """
            SELECT id, inviter_id, invitee_id, status
            FROM public.partner_connections
            WHERE id = $1
            """,
            connection_id,
        )

        if not connection:
            logger.debug("Connection %s not found", connection_id)
            return False

        if connection["status"] != "accepted":
            logger.debug("Connection %s not accepted (status=%s)", connection_id, connection["status"])
            return False

        inviter_id = str(connection["inviter_id"])
        invitee_id = str(connection["invitee_id"])

        # 2. Check both users have profiles
        inviter_profile = await conn.fetchrow(
            "SELECT id, dimension_scores, created_at FROM public.profiles WHERE user_id = $1",
            inviter_id,
        )
        if not inviter_profile:
            logger.debug("Inviter %s has no profile, skipping report generation", inviter_id)
            return False

        invitee_profile = await conn.fetchrow(
            "SELECT id, dimension_scores, created_at FROM public.profiles WHERE user_id = $1",
            invitee_id,
        )
        if not invitee_profile:
            logger.debug("Invitee %s has no profile, skipping report generation", invitee_id)
            return False

        # 3. Parse dimension scores
        inviter_dims = inviter_profile["dimension_scores"]
        invitee_dims = invitee_profile["dimension_scores"]
        if isinstance(inviter_dims, str):
            inviter_dims = json.loads(inviter_dims)
        if isinstance(invitee_dims, str):
            invitee_dims = json.loads(invitee_dims)

        # 4. Compute compatibility (pure function)
        result = compute_compatibility(inviter_dims, invitee_dims)

        # 5. Build dimension_scores JSONB for storage
        dim_scores_json = {}
        for dim_key, dim in result.dimensions.items():
            dim_scores_json[dim_key] = {
                "score": dim.score,
                "base_score": dim.base_score,
                "label": dim.label,
                "dimension_name": dim.dimension_name,
                "user_a_type": dim.user_a_type,
                "user_b_type": dim.user_b_type,
                "recommendation": dim.recommendation,
            }

        # 6. UPSERT compatibility report
        report_row = await conn.fetchrow(
            """
            INSERT INTO public.compatibility_reports (
                connection_id, user_a_profile_id, user_b_profile_id,
                overall_score, dimension_scores, improvement_potential,
                report_version, generated_from_profile_a_at, generated_from_profile_b_at
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'v1', $7, $8)
            ON CONFLICT (connection_id) DO UPDATE SET
                user_a_profile_id = EXCLUDED.user_a_profile_id,
                user_b_profile_id = EXCLUDED.user_b_profile_id,
                overall_score = EXCLUDED.overall_score,
                dimension_scores = EXCLUDED.dimension_scores,
                improvement_potential = EXCLUDED.improvement_potential,
                report_version = EXCLUDED.report_version,
                generated_from_profile_a_at = EXCLUDED.generated_from_profile_a_at,
                generated_from_profile_b_at = EXCLUDED.generated_from_profile_b_at,
                created_at = now()
            RETURNING id
            """,
            connection_id,
            inviter_profile["id"],
            invitee_profile["id"],
            result.overall_score,
            json.dumps(dim_scores_json),
            result.improvement_potential,
            inviter_profile["created_at"],
            invitee_profile["created_at"],
        )

        # 7. Delete old improvement plans and insert new ones
        await conn.execute(
            "DELETE FROM public.improvement_plans WHERE report_id = $1",
            report_row["id"],
        )

        for plan in result.challenge_plans:
            await conn.execute(
                """
                INSERT INTO public.improvement_plans (
                    report_id, dimension, severity, challenge_description,
                    action_plan, weekly_exercise
                )
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                """,
                report_row["id"],
                plan["dimension"],
                plan["severity"],
                plan["challenge_description"],
                json.dumps(plan["action_plan"]),
                plan["weekly_exercise"],
            )

        logger.info(
            "Auto-generated compatibility report for connection %s (report_id=%s)",
            connection_id,
            report_row["id"],
        )
        return True
