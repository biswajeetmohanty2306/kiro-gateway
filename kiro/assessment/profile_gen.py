# -*- coding: utf-8 -*-
"""Profile generation (F2C) — UPSERT a relationship profile from scoring results.

This module handles the DB write that persists a ScoringResult into the
profiles table. It is called within the completion transaction.
"""

from __future__ import annotations

import json
from typing import Any

from .scoring import ScoringResult


async def upsert_profile(
    conn: Any,
    user_id: str,
    assessment_id: str,
    result: ScoringResult,
) -> bool:
    """
    UPSERT the user's relationship profile from scoring results.

    Uses ON CONFLICT (user_id) DO UPDATE to overwrite on reassessment.
    Preserves the row's id (PK) for FK stability.

    Args:
        conn: An active asyncpg connection (inside a transaction).
        user_id: The user's UUID (from JWT).
        assessment_id: The assessment that produced these scores.
        result: The ScoringResult from the scoring engine.

    Returns:
        True if this was an INSERT (new profile), False if UPDATE (reassessment).
    """
    # Build dimension_scores JSONB
    dimension_scores = {
        category: {
            "score": dim.score,
            "type": dim.type,
            "strength": dim.strength,
            "sub_scores": dim.sub_scores,
        }
        for category, dim in result.dimensions.items()
    }

    # Extract primary types for the individual columns
    dims = result.dimensions
    attachment = dims.get("attachment_style")
    communication = dims.get("communication_style")
    conflict = dims.get("conflict_style")
    love_lang = dims.get("love_language")
    financial = dims.get("financial_personality")
    lifestyle = dims.get("lifestyle_type")
    archetype = dims.get("relationship_archetype")

    row = await conn.fetchrow(
        """
        INSERT INTO public.profiles (
            user_id, assessment_id,
            attachment_style, communication_style, conflict_style,
            love_language, financial_personality, lifestyle_type,
            relationship_archetype, dimension_scores
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
        ON CONFLICT (user_id) DO UPDATE SET
            assessment_id = EXCLUDED.assessment_id,
            attachment_style = EXCLUDED.attachment_style,
            communication_style = EXCLUDED.communication_style,
            conflict_style = EXCLUDED.conflict_style,
            love_language = EXCLUDED.love_language,
            financial_personality = EXCLUDED.financial_personality,
            lifestyle_type = EXCLUDED.lifestyle_type,
            relationship_archetype = EXCLUDED.relationship_archetype,
            dimension_scores = EXCLUDED.dimension_scores,
            created_at = now()
        RETURNING xmax
        """,
        user_id,
        assessment_id,
        attachment.type if attachment else "unknown",
        communication.type if communication else "unknown",
        conflict.type if conflict else "unknown",
        love_lang.type if love_lang else "unknown",
        financial.type if financial else "unknown",
        lifestyle.type if lifestyle else "unknown",
        archetype.type if archetype else "unknown",
        json.dumps(dimension_scores),
    )

    # xmax = 0 means INSERT (new row); xmax > 0 means UPDATE (existing row)
    is_insert = row["xmax"] == 0
    return is_insert
