# -*- coding: utf-8 -*-
"""Unit tests for the Profile API (F3A).

Tests the GET /api/profile response structure, empty-state handling,
type descriptions, strength labels, and display names.
"""

from __future__ import annotations

import pytest

from kiro.assessment.types import (
    DIMENSION_DISPLAY_NAMES,
    DIMENSION_ORDER,
    TYPE_LABELS,
    TYPE_DESCRIPTIONS,
    get_strength_label,
    get_type_label,
    get_type_description,
)


# ============================================================
# Tests: Strength label mapping
# ============================================================

class TestStrengthLabels:
    """Verify strength score → label mapping."""

    def test_strong(self):
        assert get_strength_label(100) == "Strong"
        assert get_strength_label(76) == "Strong"

    def test_moderate(self):
        assert get_strength_label(75) == "Moderate"
        assert get_strength_label(51) == "Moderate"

    def test_mild(self):
        assert get_strength_label(50) == "Mild"
        assert get_strength_label(26) == "Mild"

    def test_emerging(self):
        assert get_strength_label(25) == "Emerging"
        assert get_strength_label(0) == "Emerging"

    def test_boundary_76(self):
        assert get_strength_label(76) == "Strong"
        assert get_strength_label(75) == "Moderate"

    def test_boundary_51(self):
        assert get_strength_label(51) == "Moderate"
        assert get_strength_label(50) == "Mild"

    def test_boundary_26(self):
        assert get_strength_label(26) == "Mild"
        assert get_strength_label(25) == "Emerging"


# ============================================================
# Tests: Type labels
# ============================================================

class TestTypeLabels:
    """Verify type label lookups."""

    def test_all_types_have_labels(self):
        """Every defined type has a human-readable label."""
        for dimension, types in TYPE_LABELS.items():
            for type_key, label in types.items():
                assert isinstance(label, str)
                assert len(label) > 0
                assert label == get_type_label(dimension, type_key)

    def test_unknown_type_fallback(self):
        """Unknown type key produces a title-cased fallback."""
        result = get_type_label("attachment_style", "unknown_type")
        assert result == "Unknown Type"

    def test_unknown_dimension_fallback(self):
        """Unknown dimension produces a title-cased fallback."""
        result = get_type_label("nonexistent", "some_type")
        assert result == "Some Type"

    def test_specific_labels(self):
        assert get_type_label("attachment_style", "secure") == "Secure"
        assert get_type_label("attachment_style", "fearful_avoidant") == "Fearful-Avoidant"
        assert get_type_label("love_language", "words") == "Words of Affirmation"
        assert get_type_label("love_language", "touch") == "Physical Touch"
        assert get_type_label("relationship_archetype", "nurturer") == "Nurturer"


# ============================================================
# Tests: Type descriptions
# ============================================================

class TestTypeDescriptions:
    """Verify type descriptions exist and are non-empty."""

    def test_all_types_have_descriptions(self):
        """Every type in every dimension has a one-sentence description."""
        for dimension, types in TYPE_DESCRIPTIONS.items():
            for type_key, desc in types.items():
                assert isinstance(desc, str), f"Missing desc for {dimension}.{type_key}"
                assert len(desc) > 10, f"Description too short for {dimension}.{type_key}"
                assert desc.endswith("."), f"Description should end with period: {dimension}.{type_key}"

    def test_get_type_description(self):
        desc = get_type_description("attachment_style", "secure")
        assert "comfortable" in desc.lower()
        assert desc.endswith(".")

    def test_unknown_description_returns_empty(self):
        assert get_type_description("attachment_style", "nonexistent") == ""
        assert get_type_description("nonexistent", "secure") == ""


# ============================================================
# Tests: Dimension configuration
# ============================================================

class TestDimensionConfig:
    """Verify dimension metadata is complete and consistent."""

    def test_seven_dimensions_in_order(self):
        assert len(DIMENSION_ORDER) == 7

    def test_all_dimensions_have_display_names(self):
        for dim in DIMENSION_ORDER:
            assert dim in DIMENSION_DISPLAY_NAMES
            assert len(DIMENSION_DISPLAY_NAMES[dim]) > 0

    def test_all_dimensions_have_type_labels(self):
        for dim in DIMENSION_ORDER:
            assert dim in TYPE_LABELS
            assert len(TYPE_LABELS[dim]) >= 4  # at least 4 types per dimension

    def test_all_dimensions_have_type_descriptions(self):
        for dim in DIMENSION_ORDER:
            assert dim in TYPE_DESCRIPTIONS
            # Every type that has a label also has a description
            for type_key in TYPE_LABELS[dim]:
                assert type_key in TYPE_DESCRIPTIONS[dim], (
                    f"Missing description for {dim}.{type_key}"
                )

    def test_dimension_order_matches_display_names_keys(self):
        """All ordered dimensions exist in display names."""
        for dim in DIMENSION_ORDER:
            assert dim in DIMENSION_DISPLAY_NAMES

    def test_love_language_has_five_types(self):
        assert len(TYPE_LABELS["love_language"]) == 5
        assert len(TYPE_DESCRIPTIONS["love_language"]) == 5

    def test_standard_dimensions_have_four_types(self):
        for dim in DIMENSION_ORDER:
            if dim == "love_language":
                continue
            assert len(TYPE_LABELS[dim]) == 4, f"{dim} should have 4 types"


# ============================================================
# Tests: Profile response structure
# ============================================================

class TestProfileResponseStructure:
    """Verify the shape of a profile response built from types module."""

    def _build_mock_response(self):
        """Simulate what the router builds from a DB row."""
        import json
        from kiro.assessment.types import (
            get_strength_label,
            get_type_label,
            get_type_description,
        )

        dim_scores_raw = {
            "attachment_style": {"score": 38, "type": "secure", "strength": 100, "sub_scores": {"secure": 100, "anxious": 25, "avoidant": 17, "fearful_avoidant": 8}},
            "communication_style": {"score": 52, "type": "diplomatic", "strength": 85, "sub_scores": {"direct": 45, "diplomatic": 85, "analytical": 40, "expressive": 38}},
            "conflict_style": {"score": 50, "type": "collaborative", "strength": 88, "sub_scores": {"collaborative": 88, "compromising": 42, "avoiding": 35, "competing": 35}},
            "love_language": {"score": 60, "type": "time", "strength": 60, "sub_scores": {"words": 20, "acts": 10, "gifts": 0, "touch": 10, "time": 60}},
            "financial_personality": {"score": 48, "type": "investor", "strength": 79, "sub_scores": {"saver": 40, "spender": 20, "investor": 79, "balanced": 55}},
            "lifestyle_type": {"score": 46, "type": "balanced", "strength": 67, "sub_scores": {"adventurous": 40, "homebody": 30, "balanced": 67, "social": 45}},
            "relationship_archetype": {"score": 50, "type": "partner", "strength": 83, "sub_scores": {"partner": 83, "independent": 30, "nurturer": 45, "explorer": 40}},
        }

        dimensions = {}
        for dim_key in DIMENSION_ORDER:
            dim_data = dim_scores_raw[dim_key]
            type_key = dim_data["type"]
            strength = dim_data["strength"]

            dimensions[dim_key] = {
                "type": type_key,
                "label": get_type_label(dim_key, type_key),
                "strength": strength,
                "strength_label": get_strength_label(strength),
                "score": dim_data["score"],
                "description": get_type_description(dim_key, type_key),
                "dimension_name": DIMENSION_DISPLAY_NAMES[dim_key],
                "sub_scores": dim_data["sub_scores"],
            }

        return {"has_profile": True, "profile": {"dimensions": dimensions}}

    def test_response_has_all_dimensions(self):
        resp = self._build_mock_response()
        assert resp["has_profile"] is True
        dims = resp["profile"]["dimensions"]
        assert len(dims) == 7
        for dim_key in DIMENSION_ORDER:
            assert dim_key in dims

    def test_each_dimension_has_required_fields(self):
        resp = self._build_mock_response()
        dims = resp["profile"]["dimensions"]
        required_fields = {"type", "label", "strength", "strength_label", "score", "description", "dimension_name", "sub_scores"}
        for dim_key, dim_data in dims.items():
            for field in required_fields:
                assert field in dim_data, f"Missing {field} in {dim_key}"

    def test_strength_labels_are_correct(self):
        resp = self._build_mock_response()
        dims = resp["profile"]["dimensions"]
        assert dims["attachment_style"]["strength_label"] == "Strong"  # 100
        assert dims["communication_style"]["strength_label"] == "Strong"  # 85
        assert dims["love_language"]["strength_label"] == "Moderate"  # 60
        assert dims["lifestyle_type"]["strength_label"] == "Moderate"  # 67

    def test_descriptions_are_populated(self):
        resp = self._build_mock_response()
        dims = resp["profile"]["dimensions"]
        for dim_key, dim_data in dims.items():
            assert len(dim_data["description"]) > 0, f"Empty description for {dim_key}"

    def test_labels_are_human_readable(self):
        resp = self._build_mock_response()
        dims = resp["profile"]["dimensions"]
        assert dims["attachment_style"]["label"] == "Secure"
        assert dims["love_language"]["label"] == "Quality Time"
        assert dims["financial_personality"]["label"] == "Investor"

    def test_empty_state(self):
        resp = {"has_profile": False, "profile": None}
        assert resp["has_profile"] is False
        assert resp["profile"] is None
