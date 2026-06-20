# -*- coding: utf-8 -*-
"""Compatibility service (F5C) — orchestrates report generation and retrieval.

Reads partner connections + profiles, invokes the pure engine, and persists
results to compatibility_reports + improvement_plans.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .engine import compute_compatibility
from .exceptions import (
    NoPartnerError,
    PartnerNoProfileError,
    PlanNotFoundError,
    ReportNotFoundError,
    UserNoProfileError,
)


async def get_report(pool: Any, user_id: str) -> dict:
    """
    Get the current compatibility report for the user's partnership.
    Returns has_report=True with full breakdown, or has_report=False with reason.
    """
    async with pool.acquire() as conn:
        # Find accepted connection
        connection = await conn.fetchrow(
            """
            SELECT id, inviter_id, invitee_id
            FROM public.partner_connections
            WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
            LIMIT 1
            """,
            user_id,
        )

        if not connection:
            return {"has_report": False, "reason": "no_partner"}

        # Check for existing report
        report = await conn.fetchrow(
            """
            SELECT id, overall_score, dimension_scores, improvement_potential,
                   report_version, created_at
            FROM public.compatibility_reports
            WHERE connection_id = $1
            """,
            connection["id"],
        )

        if not report:
            # Check if partner has a profile (to distinguish states)
            inviter_id = str(connection["inviter_id"])
            invitee_id = str(connection["invitee_id"])
            partner_id = invitee_id if inviter_id == user_id else inviter_id

            partner_profile = await conn.fetchrow(
                "SELECT id FROM public.profiles WHERE user_id = $1",
                partner_id,
            )
            user_profile = await conn.fetchrow(
                "SELECT id FROM public.profiles WHERE user_id = $1",
                user_id,
            )

            if not user_profile:
                return {"has_report": False, "reason": "user_no_profile"}
            if not partner_profile:
                return {"has_report": False, "reason": "partner_no_profile"}
            # Both profiles exist but no report — shouldn't happen with auto-gen,
            # but allow manual generation as fallback
            return {"has_report": False, "reason": "not_generated"}

        # Parse dimension scores
        dim_scores = report["dimension_scores"]
        if isinstance(dim_scores, str):
            dim_scores = json.loads(dim_scores)

        return {
            "has_report": True,
            "report": {
                "report_id": str(report["id"]),
                "overall_score": float(report["overall_score"]),
                "improvement_potential": float(report["improvement_potential"]),
                "report_version": report["report_version"],
                "created_at": report["created_at"].isoformat(),
                "dimensions": dim_scores,
            },
        }


async def generate_report(pool: Any, user_id: str) -> dict:
    """
    Generate (or regenerate) a compatibility report.

    Validates eligibility, computes scores, and UPSERTs the report + plans.
    """
    async with pool.acquire() as conn:
        # 1. Find accepted connection
        connection = await conn.fetchrow(
            """
            SELECT id, inviter_id, invitee_id
            FROM public.partner_connections
            WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
            LIMIT 1
            """,
            user_id,
        )

        if not connection:
            raise NoPartnerError()

        inviter_id = str(connection["inviter_id"])
        invitee_id = str(connection["invitee_id"])
        partner_id = invitee_id if inviter_id == user_id else inviter_id

        # 2. Get both profiles
        user_profile = await conn.fetchrow(
            "SELECT id, dimension_scores, created_at FROM public.profiles WHERE user_id = $1",
            user_id,
        )
        if not user_profile:
            raise UserNoProfileError()

        partner_profile = await conn.fetchrow(
            "SELECT id, dimension_scores, created_at FROM public.profiles WHERE user_id = $1",
            partner_id,
        )
        if not partner_profile:
            raise PartnerNoProfileError()

        # 3. Parse dimension scores
        user_dims = user_profile["dimension_scores"]
        partner_dims = partner_profile["dimension_scores"]
        if isinstance(user_dims, str):
            user_dims = json.loads(user_dims)
        if isinstance(partner_dims, str):
            partner_dims = json.loads(partner_dims)

        # 4. Compute compatibility (pure function)
        result = compute_compatibility(user_dims, partner_dims)

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
            RETURNING id, created_at
            """,
            connection["id"],
            user_profile["id"],
            partner_profile["id"],
            result.overall_score,
            json.dumps(dim_scores_json),
            result.improvement_potential,
            user_profile["created_at"],
            partner_profile["created_at"],
        )

        # 7. Delete old improvement plans (CASCADE would handle on report delete,
        #    but UPSERT keeps the row, so delete plans manually)
        await conn.execute(
            "DELETE FROM public.improvement_plans WHERE report_id = $1",
            report_row["id"],
        )

        # 8. Insert new improvement plans (3 challenges)
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

        return {
            "report_id": str(report_row["id"]),
            "overall_score": result.overall_score,
            "overall_label": result.overall_label,
            "improvement_potential": result.improvement_potential,
            "created_at": report_row["created_at"].isoformat(),
            "dimensions": dim_scores_json,
            "challenge_plans": result.challenge_plans,
        }


async def get_improvement_plans(pool: Any, user_id: str) -> dict:
    """Get improvement plans for the user's current compatibility report."""
    async with pool.acquire() as conn:
        # Find connection
        connection = await conn.fetchrow(
            """
            SELECT id FROM public.partner_connections
            WHERE (inviter_id = $1 OR invitee_id = $1) AND status = 'accepted'
            LIMIT 1
            """,
            user_id,
        )
        if not connection:
            raise NoPartnerError()

        # Find report
        report = await conn.fetchrow(
            "SELECT id FROM public.compatibility_reports WHERE connection_id = $1",
            connection["id"],
        )
        if not report:
            raise ReportNotFoundError()

        # Fetch plans
        rows = await conn.fetch(
            """
            SELECT id, dimension, severity, challenge_description,
                   action_plan, weekly_exercise, completed, completed_at, created_at
            FROM public.improvement_plans
            WHERE report_id = $1
            ORDER BY created_at
            """,
            report["id"],
        )

        plans = []
        for row in rows:
            action_plan = row["action_plan"]
            if isinstance(action_plan, str):
                action_plan = json.loads(action_plan)
            plans.append({
                "id": str(row["id"]),
                "dimension": row["dimension"],
                "severity": row["severity"],
                "challenge_description": row["challenge_description"],
                "action_plan": action_plan,
                "weekly_exercise": row["weekly_exercise"],
                "completed": row["completed"],
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            })

        return {"plans": plans, "total": len(plans)}


async def complete_plan(pool: Any, user_id: str, plan_id: str) -> dict:
    """Mark an improvement plan task as completed."""
    async with pool.acquire() as conn:
        # Verify the plan belongs to the user's partnership
        row = await conn.fetchrow(
            """
            SELECT ip.id, ip.completed
            FROM public.improvement_plans ip
            JOIN public.compatibility_reports cr ON cr.id = ip.report_id
            JOIN public.partner_connections pc ON pc.id = cr.connection_id
            WHERE ip.id = $1
              AND (pc.inviter_id = $2 OR pc.invitee_id = $2)
              AND pc.status = 'accepted'
            """,
            plan_id,
            user_id,
        )

        if not row:
            raise PlanNotFoundError()

        # Toggle to complete
        updated = await conn.fetchrow(
            """
            UPDATE public.improvement_plans
            SET completed = true, completed_at = now()
            WHERE id = $1
            RETURNING id, completed, completed_at
            """,
            plan_id,
        )

        return {
            "id": str(updated["id"]),
            "completed": updated["completed"],
            "completed_at": updated["completed_at"].isoformat(),
        }
