# -*- coding: utf-8 -*-
"""Unit tests for the scoring engine (F2B).

Tests validated against F2ScoringValidationPlan.md and F2BAlgorithmWalkthrough.md.
All tests use the pure scoring function — no database, no I/O.
"""

from __future__ import annotations

import pytest

from kiro.assessment.scoring import (
    DimensionResult,
    ScoringResult,
    score_assessment,
    _score_standard_dimension,
    _score_love_language,
    _determine_primary_type,
)
from kiro.assessment.constants import TIE_BREAK_ORDER


# --- Helpers ---

def make_question(qid, category, sub_scale, weight=1.0, reverse=False, answer_options=None):
    """Create a minimal question dict for testing."""
    if answer_options is None:
        answer_options = [
            {"text": "A", "score": 5},
            {"text": "B", "score": 4},
            {"text": "C", "score": 3},
            {"text": "D", "score": 2},
            {"text": "E", "score": 1},
        ]
    return {
        "id": qid,
        "category": category,
        "sub_scale": sub_scale,
        "weight": weight,
        "reverse_scored": reverse,
        "answer_options": answer_options,
    }


def make_answer(question_id, score, selected_option_index=0):
    """Create a minimal answer dict for testing."""
    return {
        "question_id": question_id,
        "score": score,
        "selected_option_index": selected_option_index,
    }


def make_ll_question(qid, order=1):
    """Create a Love Language question with 5 language-tagged options."""
    return {
        "id": qid,
        "category": "love_language",
        "sub_scale": "words",
        "weight": 1.0,
        "reverse_scored": False,
        "answer_options": [
            {"text": "Words option", "score": 5, "language": "words"},
            {"text": "Acts option", "score": 5, "language": "acts"},
            {"text": "Gifts option", "score": 5, "language": "gifts"},
            {"text": "Touch option", "score": 5, "language": "touch"},
            {"text": "Time option", "score": 5, "language": "time"},
        ],
    }


# ============================================================
# TEST GROUP A: Algorithm unit tests (F2ScoringValidationPlan A-1 to A-12)
# ============================================================

class TestA1AllMaxSingleSubscale:
    """A-1: All max scores for one sub-scale → score = 100."""

    def test_all_max_secure(self):
        # 3 Secure questions all scored 5, weights: 0.5, 1.5, 1.0
        tuples = [
            ("secure", 0.5, 5),
            ("secure", 1.5, 5),
            ("secure", 1.0, 5),
            ("anxious", 1.0, 1),
            ("anxious", 1.5, 1),
            ("anxious", 1.0, 1),
        ]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 100
        assert result.type == "secure"


class TestA2AllMinSingleSubscale:
    """A-2: All min scores → score = 0."""

    def test_all_min_secure(self):
        tuples = [
            ("secure", 0.5, 1),
            ("secure", 1.5, 1),
            ("secure", 1.0, 1),
            ("anxious", 1.0, 1),
            ("anxious", 1.5, 1),
            ("anxious", 1.0, 1),
        ]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 0
        assert result.sub_scores["anxious"] == 0


class TestA3AllMiddle:
    """A-3: All scores = 3 → all sub-scores = 50."""

    def test_all_middle(self):
        tuples = [
            ("secure", 0.5, 3),
            ("secure", 1.5, 3),
            ("secure", 1.0, 3),
            ("anxious", 1.0, 3),
            ("anxious", 1.5, 3),
            ("anxious", 1.0, 3),
            ("avoidant", 1.0, 3),
            ("avoidant", 1.0, 3),
            ("avoidant", 1.0, 3),
            ("fearful_avoidant", 1.0, 3),
            ("fearful_avoidant", 1.0, 3),
            ("fearful_avoidant", 1.0, 3),
        ]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 50
        assert result.sub_scores["anxious"] == 50
        assert result.sub_scores["avoidant"] == 50
        assert result.sub_scores["fearful_avoidant"] == 50


class TestA4ReverseAlreadyApplied:
    """A-4: Reverse scoring already applied at insert time. Score stored as 1."""

    def test_reverse_score_low(self):
        # A reverse-scored Q where user "agreed" (raw 5 → stored 1)
        # The scoring engine just sees score=1, treats it normally
        tuples = [("secure", 1.0, 1)]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 0  # (1-1)/(5-1)*100 = 0


class TestA5ReverseHigh:
    """A-5: Reverse Q where user "disagreed" (raw 1 → stored 5)."""

    def test_reverse_score_high(self):
        tuples = [("secure", 1.0, 5)]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 100  # (5-1)/(5-1)*100 = 100


class TestA6WeightInfluence:
    """A-6: Weight 2.0 contributes 4× vs weight 0.5."""

    def test_weight_contribution(self):
        # Two sub-scales: one with heavy question (2.0), one with light (0.5)
        # Both scored 5, but different resulting weighted_sum
        tuples = [
            ("avoiding", 2.0, 5),  # weighted_sum = 10.0, total_weight = 2.0
            ("competing", 0.5, 5),  # weighted_sum = 2.5, total_weight = 0.5
        ]
        result = _score_standard_dimension("conflict_style", tuples)
        # Both normalize to 100 (max score regardless of weight)
        assert result.sub_scores["avoiding"] == 100
        assert result.sub_scores["competing"] == 100

    def test_weight_impact_on_mixed(self):
        # Heavy Q scored high, light Q scored low — same sub-scale
        tuples = [
            ("avoiding", 2.0, 5),  # 10.0
            ("avoiding", 0.5, 1),  # 0.5
            # total_weight = 2.5, weighted_sum = 10.5
            # min = 2.5, max = 12.5
            # (10.5 - 2.5) / (12.5 - 2.5) * 100 = 8.0/10.0 * 100 = 80
        ]
        result = _score_standard_dimension("conflict_style", tuples)
        assert result.sub_scores["avoiding"] == 80


class TestA7TiebreakAttachment:
    """A-7: Secure=60, Anxious=60 → Secure wins (first in priority)."""

    def test_two_way_tie(self):
        sub_scores = {"secure": 60, "anxious": 60, "avoidant": 30, "fearful_avoidant": 20}
        winner = _determine_primary_type(sub_scores, "attachment_style")
        assert winner == "secure"


class TestA8TiebreakAllEqual:
    """A-8: All sub-scores = 50 → first in priority wins."""

    def test_all_equal_attachment(self):
        sub_scores = {"secure": 50, "anxious": 50, "avoidant": 50, "fearful_avoidant": 50}
        assert _determine_primary_type(sub_scores, "attachment_style") == "secure"

    def test_all_equal_communication(self):
        sub_scores = {"direct": 50, "diplomatic": 50, "analytical": 50, "expressive": 50}
        assert _determine_primary_type(sub_scores, "communication_style") == "direct"

    def test_all_equal_conflict(self):
        sub_scores = {"collaborative": 50, "compromising": 50, "avoiding": 50, "competing": 50}
        assert _determine_primary_type(sub_scores, "conflict_style") == "collaborative"

    def test_all_equal_financial(self):
        sub_scores = {"saver": 50, "investor": 50, "balanced": 50, "spender": 50}
        assert _determine_primary_type(sub_scores, "financial_personality") == "saver"

    def test_all_equal_lifestyle(self):
        sub_scores = {"adventurous": 50, "social": 50, "balanced": 50, "homebody": 50}
        assert _determine_primary_type(sub_scores, "lifestyle_type") == "adventurous"

    def test_all_equal_archetype(self):
        sub_scores = {"partner": 50, "nurturer": 50, "independent": 50, "explorer": 50}
        assert _determine_primary_type(sub_scores, "relationship_archetype") == "partner"

    def test_all_equal_love_language(self):
        sub_scores = {"words": 20, "acts": 20, "gifts": 20, "touch": 20, "time": 20}
        assert _determine_primary_type(sub_scores, "love_language") == "words"


class TestA9LoveLangAllOne:
    """A-9: All 10 picks = Touch → Touch=100, others=0."""

    def test_all_touch(self):
        questions = [make_ll_question(f"q_lovelanguage_{i:02d}") for i in range(1, 11)]
        # All answers select option index 3 (Touch)
        answers = [
            make_answer(f"q_lovelanguage_{i:02d}", 5, selected_option_index=3)
            for i in range(1, 11)
        ]
        q_map = {q["id"]: q for q in questions}
        result = _score_love_language(answers, q_map)

        assert result.sub_scores["touch"] == 100
        assert result.sub_scores["words"] == 0
        assert result.sub_scores["acts"] == 0
        assert result.sub_scores["gifts"] == 0
        assert result.sub_scores["time"] == 0
        assert result.type == "touch"
        assert result.strength == 100


class TestA10LoveLangEvenSplit:
    """A-10: Even split (2 of each) → all=20, primary=Words (tie-break)."""

    def test_even_split(self):
        questions = [make_ll_question(f"q_lovelanguage_{i:02d}") for i in range(1, 11)]
        # 2 Words (idx 0), 2 Acts (idx 1), 2 Gifts (idx 2), 2 Touch (idx 3), 2 Time (idx 4)
        answers = [
            make_answer("q_lovelanguage_01", 5, 0),
            make_answer("q_lovelanguage_02", 5, 0),
            make_answer("q_lovelanguage_03", 5, 1),
            make_answer("q_lovelanguage_04", 5, 1),
            make_answer("q_lovelanguage_05", 5, 2),
            make_answer("q_lovelanguage_06", 5, 2),
            make_answer("q_lovelanguage_07", 5, 3),
            make_answer("q_lovelanguage_08", 5, 3),
            make_answer("q_lovelanguage_09", 5, 4),
            make_answer("q_lovelanguage_10", 5, 4),
        ]
        q_map = {q["id"]: q for q in questions}
        result = _score_love_language(answers, q_map)

        assert result.sub_scores == {"words": 20, "acts": 20, "gifts": 20, "touch": 20, "time": 20}
        assert result.type == "words"  # tie-break: first in priority


class TestA11OverallScore:
    """A-11: Overall score = average of 7 dimension scores."""

    def test_overall_average(self):
        # Create 7 dimensions with known scores
        questions = []
        answers = []
        dimensions = [
            ("attachment_style", "secure"),
            ("communication_style", "direct"),
            ("conflict_style", "collaborative"),
            ("financial_personality", "saver"),
            ("lifestyle_type", "adventurous"),
            ("relationship_archetype", "partner"),
        ]
        for i, (cat, sub) in enumerate(dimensions):
            qid = f"q_test_{i}"
            questions.append(make_question(qid, cat, sub, weight=1.0))
            answers.append(make_answer(qid, 3))  # score 3 → normalized 50

        # Add Love Language (all Words)
        for j in range(10):
            qid = f"q_ll_{j}"
            questions.append(make_ll_question(qid))
            answers.append(make_answer(qid, 5, selected_option_index=0))  # Words

        result = score_assessment(answers, questions)

        # Each standard dimension has one question: sub_score = (3-1)/(5-1)*100 = 50
        # Love Language: all Words → Words=100
        # Overall = (50+50+50+50+50+50+100) / 7 = 400/7 ≈ 57.14
        assert result.overall_score == pytest.approx(57.14, abs=0.01)


class TestA12Rounding:
    """A-12: Scores round to nearest integer."""

    def test_rounding_up(self):
        # Score that should round: (2.5-1.0)/(5.0-1.0)*100 = 1.5/4.0*100 = 37.5 → 38
        tuples = [("secure", 1.0, 2), ("secure", 1.0, 3)]
        # weighted_sum = 5.0, total_weight = 2.0
        # (5.0 - 2.0) / (10.0 - 2.0) * 100 = 3.0/8.0*100 = 37.5 → 38
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 38

    def test_rounding_down(self):
        # 3 questions: scores 4, 3, 2. weights all 1.0
        # weighted_sum=9, total_weight=3, min=3, max=15
        # (9-3)/(15-3)*100 = 6/12*100 = 50.0 → 50 (exact)
        tuples = [("secure", 1.0, 4), ("secure", 1.0, 3), ("secure", 1.0, 2)]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] == 50


# ============================================================
# TEST GROUP: Integration-style tests (full score_assessment calls)
# ============================================================

class TestFullAssessmentScoring:
    """Full pipeline tests using score_assessment with realistic data."""

    def test_user_a_attachment_walkthrough(self):
        """User A from F2BAlgorithmWalkthrough: Secure dominant."""
        questions = [
            make_question("q_a01", "attachment_style", "secure", 0.5),
            make_question("q_a02", "attachment_style", "secure", 1.5),
            make_question("q_a03", "attachment_style", "secure", 1.0, reverse=True),
            make_question("q_a04", "attachment_style", "anxious", 1.0),
            make_question("q_a05", "attachment_style", "anxious", 1.5),
            make_question("q_a06", "attachment_style", "anxious", 1.0),
            make_question("q_a07", "attachment_style", "avoidant", 1.0),
            make_question("q_a08", "attachment_style", "avoidant", 1.0),
            make_question("q_a09", "attachment_style", "avoidant", 1.0, reverse=True),
            make_question("q_a10", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q_a11", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q_a12", "attachment_style", "fearful_avoidant", 1.0),
        ]
        answers = [
            make_answer("q_a01", 5),  # secure, stored=5
            make_answer("q_a02", 5),  # secure, stored=5
            make_answer("q_a03", 5),  # secure (R), user picked raw=1→stored=5
            make_answer("q_a04", 2),  # anxious
            make_answer("q_a05", 2),  # anxious
            make_answer("q_a06", 2),  # anxious
            make_answer("q_a07", 2),  # avoidant
            make_answer("q_a08", 1),  # avoidant
            make_answer("q_a09", 2),  # avoidant (R), raw=4→stored=2
            make_answer("q_a10", 1),  # FA
            make_answer("q_a11", 2),  # FA
            make_answer("q_a12", 1),  # FA
        ]

        result = score_assessment(answers, questions)
        dim = result.dimensions["attachment_style"]

        assert dim.type == "secure"
        assert dim.strength == 100
        assert dim.sub_scores["secure"] == 100
        assert dim.sub_scores["anxious"] == 25
        assert dim.sub_scores["avoidant"] == 17
        assert dim.sub_scores["fearful_avoidant"] == 8

    def test_user_c_all_ties(self):
        """User C: all scores=3, all sub-scales tie at 50, tie-break wins."""
        questions = [
            make_question("q01", "attachment_style", "secure", 0.5),
            make_question("q02", "attachment_style", "secure", 1.5),
            make_question("q03", "attachment_style", "secure", 1.0),
            make_question("q04", "attachment_style", "anxious", 1.0),
            make_question("q05", "attachment_style", "anxious", 1.5),
            make_question("q06", "attachment_style", "anxious", 1.0),
            make_question("q07", "attachment_style", "avoidant", 1.0),
            make_question("q08", "attachment_style", "avoidant", 1.0),
            make_question("q09", "attachment_style", "avoidant", 1.0),
            make_question("q10", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q11", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q12", "attachment_style", "fearful_avoidant", 1.0),
        ]
        answers = [make_answer(f"q{i:02d}", 3) for i in range(1, 13)]

        result = score_assessment(answers, questions)
        dim = result.dimensions["attachment_style"]

        assert dim.sub_scores["secure"] == 50
        assert dim.sub_scores["anxious"] == 50
        assert dim.sub_scores["avoidant"] == 50
        assert dim.sub_scores["fearful_avoidant"] == 50
        assert dim.type == "secure"  # tie-break: first in priority

    def test_user_d_extremist_reverse_impact(self):
        """User D: all option 0 (score 5), reverse Qs store 1 after reversal."""
        questions = [
            make_question("q01", "attachment_style", "secure", 0.5),
            make_question("q02", "attachment_style", "secure", 1.5),
            make_question("q03", "attachment_style", "secure", 1.0, reverse=True),
            make_question("q04", "attachment_style", "anxious", 1.0),
            make_question("q05", "attachment_style", "anxious", 1.5),
            make_question("q06", "attachment_style", "anxious", 1.0),
            make_question("q07", "attachment_style", "avoidant", 1.0),
            make_question("q08", "attachment_style", "avoidant", 1.0),
            make_question("q09", "attachment_style", "avoidant", 1.0, reverse=True),
            make_question("q10", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q11", "attachment_style", "fearful_avoidant", 1.0),
            make_question("q12", "attachment_style", "fearful_avoidant", 1.0),
        ]
        # User D: all raw 5, but reverse Qs stored as 1 (6-5=1)
        answers = [
            make_answer("q01", 5),
            make_answer("q02", 5),
            make_answer("q03", 1),  # reverse: raw 5 → stored 1
            make_answer("q04", 5),
            make_answer("q05", 5),
            make_answer("q06", 5),
            make_answer("q07", 5),
            make_answer("q08", 5),
            make_answer("q09", 1),  # reverse: raw 5 → stored 1
            make_answer("q10", 5),
            make_answer("q11", 5),
            make_answer("q12", 5),
        ]

        result = score_assessment(answers, questions)
        dim = result.dimensions["attachment_style"]

        # Secure: (5×0.5 + 5×1.5 + 1×1.0) = 11.0; norm = (11-3)/(15-3)*100 = 67
        assert dim.sub_scores["secure"] == 67
        # Anxious: (5×1.0 + 5×1.5 + 5×1.0) = 17.5; norm = (17.5-3.5)/(17.5-3.5)*100 = 100
        assert dim.sub_scores["anxious"] == 100
        # Avoidant: (5×1.0 + 5×1.0 + 1×1.0) = 11.0; norm = (11-3)/(15-3)*100 = 67
        assert dim.sub_scores["avoidant"] == 67
        # FA: (5+5+5) = 15; norm = (15-3)/(15-3)*100 = 100
        assert dim.sub_scores["fearful_avoidant"] == 100
        # Tie at 100: anxious vs FA → anxious wins (priority)
        assert dim.type == "anxious"

    def test_user_e_all_zeros(self):
        """User E: all stored scores = 1 → all sub-scores = 0."""
        questions = [
            make_question("q01", "attachment_style", "secure", 0.5),
            make_question("q02", "attachment_style", "secure", 1.5),
            make_question("q03", "attachment_style", "secure", 1.0),
            make_question("q04", "attachment_style", "anxious", 1.0),
            make_question("q05", "attachment_style", "anxious", 1.5),
            make_question("q06", "attachment_style", "anxious", 1.0),
        ]
        answers = [make_answer(f"q{i:02d}", 1) for i in range(1, 7)]

        result = score_assessment(answers, questions)
        dim = result.dimensions["attachment_style"]

        assert dim.sub_scores["secure"] == 0
        assert dim.sub_scores["anxious"] == 0
        assert dim.type == "secure"  # tie at 0, first wins
        assert dim.strength == 0

    def test_no_negative_scores(self):
        """Scores must never be negative."""
        tuples = [("secure", 1.0, 1)]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] >= 0

    def test_no_scores_above_100(self):
        """Scores must never exceed 100."""
        tuples = [("secure", 2.0, 5)]
        result = _score_standard_dimension("attachment_style", tuples)
        assert result.sub_scores["secure"] <= 100

    def test_love_language_clear_primary(self):
        """LL: 7 Words + 3 Acts → Words primary at 70."""
        questions = [make_ll_question(f"q_ll_{i:02d}") for i in range(1, 11)]
        answers = (
            [make_answer(f"q_ll_{i:02d}", 5, 0) for i in range(1, 8)]  # 7 Words
            + [make_answer(f"q_ll_{i:02d}", 5, 1) for i in range(8, 11)]  # 3 Acts
        )
        q_map = {q["id"]: q for q in questions}
        result = _score_love_language(answers, q_map)

        assert result.type == "words"
        assert result.strength == 70
        assert result.sub_scores["words"] == 70
        assert result.sub_scores["acts"] == 30
        assert result.score == 70  # max sub-score

    def test_multi_dimension_overall_score(self):
        """Overall = average of all dimension scores."""
        questions = [
            make_question("q1", "attachment_style", "secure", 1.0),
            make_question("q2", "communication_style", "direct", 1.0),
        ]
        # Score 5 → sub-score 100 for each
        answers = [make_answer("q1", 5), make_answer("q2", 5)]

        result = score_assessment(answers, questions)

        # Both dimensions: single sub-scale at 100 → dim_score 100
        assert result.dimensions["attachment_style"].score == 100
        assert result.dimensions["communication_style"].score == 100
        assert result.overall_score == 100.0
