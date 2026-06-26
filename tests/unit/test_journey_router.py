# -*- coding: utf-8 -*-
"""Unit tests for the Journey API router (J2-D).

Tests the HTTP contract: routing, authentication, request validation,
exception mapping, and response serialization.

Business logic is NOT tested here — that belongs to the service layer.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.journey.router import router
from kiro.journey.exceptions import JourneyError, NoConnectionError, ReflectionAlreadySubmittedError
from kiro.supabase_auth.dependencies import get_current_user_profile
from kiro.supabase_auth.profile import UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures
# ─────────────────────────────────────────────────────────────────────────────

MOCK_USER = UserProfile(
    user_id="user-123",
    email="alice@example.com",
    name="Alice",
    onboarding_completed=True,
)

JOURNEY_ACTIVE = {
    "active": True,
    "current_week": 3,
    "journey_started_at": "2026-06-08T12:00:00+00:00",
    "total_reflections": 2,
    "last_reflection_at": "2026-06-20T18:30:00+00:00",
    "this_week_submitted": False,
    "journey_phase": "EARLY",
    "user_name": "Alice",
    "partner_name": "Bob",
}

JOURNEY_INACTIVE = {
    "active": False,
    "current_week": 0,
    "journey_started_at": None,
    "total_reflections": 0,
    "last_reflection_at": None,
    "this_week_submitted": False,
    "journey_phase": "EARLY",
    "user_name": "Alice",
    "partner_name": "",
}

QUESTIONS_RESPONSE = {
    "week_number": 3,
    "questions": [
        {"id": "safety_1", "text": "How emotionally safe did this week feel?", "type": "scale",
         "options": {"min_label": "Not safe", "max_label": "Very safe", "min_value": 1, "max_value": 5}},
        {"id": "conn_2", "text": "Did you have a good conversation?", "type": "yes_no", "options": None},
        {"id": "open_1", "text": "One thing I noticed...", "type": "open", "options": None},
    ],
    "already_submitted": False,
}

QUESTIONS_ALREADY_SUBMITTED = {
    "week_number": 3,
    "questions": QUESTIONS_RESPONSE["questions"],
    "already_submitted": True,
}

SUBMISSION_RESPONSE = {
    "id": "refl-uuid-1",
    "week_number": 3,
    "week_start": "2026-06-22",
    "created_at": "2026-06-26T10:00:00+00:00",
    "message": "Thank you. Every reflection helps you understand your relationship a little better.",
}

HISTORY_RESPONSE = {
    "reflections": [
        {
            "id": "refl-2",
            "week_number": 2,
            "week_start": "2026-06-15",
            "responses": [
                {"question_id": "safety_1", "question_text": "How safe?", "answer": "4"},
            ],
            "created_at": "2026-06-18T09:00:00+00:00",
        },
        {
            "id": "refl-1",
            "week_number": 1,
            "week_start": "2026-06-08",
            "responses": [
                {"question_id": "safety_2", "question_text": "How comfortable?", "answer": "3"},
            ],
            "created_at": "2026-06-11T09:00:00+00:00",
        },
    ],
    "total": 2,
}

HISTORY_EMPTY = {"reflections": [], "total": 0}


def _create_app() -> FastAPI:
    """Build a minimal FastAPI app with the journey router and exception handler."""
    app = FastAPI()
    app.include_router(router)

    # Mock the app.state.supabase_auth._audit_pool so _get_pool() works
    mock_auth = MagicMock()
    mock_auth._audit_pool = MagicMock()
    app.state.supabase_auth = mock_auth

    @app.exception_handler(JourneyError)
    async def _handle(request, exc: JourneyError):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    return app


def _authenticated_app() -> FastAPI:
    """App with auth dependency overridden to return a mock user."""
    app = _create_app()
    app.dependency_overrides[get_current_user_profile] = lambda: MOCK_USER
    return app


def _unauthenticated_app() -> FastAPI:
    """App with auth dependency that raises (simulating 401)."""
    from kiro.supabase_auth.exceptions import InvalidTokenError, SupabaseAuthError

    def _deny():
        raise InvalidTokenError("Missing or malformed Authorization header.")

    app = _create_app()

    @app.exception_handler(SupabaseAuthError)
    async def _auth_handler(request, exc: SupabaseAuthError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"code": "INVALID_TOKEN", "message": str(exc)})

    app.dependency_overrides[get_current_user_profile] = _deny
    return app


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/journey
# ─────────────────────────────────────────────────────────────────────────────


class TestGetJourney:
    """Tests for GET /api/journey."""

    @patch("kiro.journey.router.get_journey", new_callable=AsyncMock)
    def test_active_journey(self, mock_service):
        """Returns journey state with all fields when active."""
        mock_service.return_value = JOURNEY_ACTIVE
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["current_week"] == 3
        assert data["journey_phase"] == "EARLY"
        assert data["user_name"] == "Alice"
        assert data["partner_name"] == "Bob"
        assert data["this_week_submitted"] is False

    @patch("kiro.journey.router.get_journey", new_callable=AsyncMock)
    def test_inactive_journey(self, mock_service):
        """Returns active=False when no journey exists."""
        mock_service.return_value = JOURNEY_INACTIVE
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["current_week"] == 0
        assert data["journey_phase"] == "EARLY"

    @patch("kiro.journey.router.get_journey", new_callable=AsyncMock)
    def test_response_schema(self, mock_service):
        """Response matches JourneyStateResponse schema fields."""
        mock_service.return_value = JOURNEY_ACTIVE
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey").json()

        expected_keys = {
            "active", "current_week", "journey_started_at",
            "total_reflections", "last_reflection_at", "this_week_submitted",
            "journey_phase", "user_name", "partner_name",
        }
        assert set(data.keys()) == expected_keys

    @patch("kiro.journey.router.get_journey", new_callable=AsyncMock)
    def test_journey_phase_values(self, mock_service):
        """journey_phase is one of the valid literals."""
        for phase in ("EARLY", "BUILDING", "GROWING", "ESTABLISHED"):
            mock_service.return_value = {**JOURNEY_ACTIVE, "journey_phase": phase}
            client = TestClient(_authenticated_app())
            data = client.get("/api/journey").json()
            assert data["journey_phase"] == phase

    def test_unauthenticated(self):
        """Returns 401 when not authenticated."""
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/journey")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/journey/questions
# ─────────────────────────────────────────────────────────────────────────────


class TestGetQuestions:
    """Tests for GET /api/journey/questions."""

    @patch("kiro.journey.router.get_questions", new_callable=AsyncMock)
    def test_successful_response(self, mock_service):
        """Returns questions when journey is active."""
        mock_service.return_value = QUESTIONS_RESPONSE
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/questions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["week_number"] == 3
        assert len(data["questions"]) == 3
        assert data["already_submitted"] is False

    @patch("kiro.journey.router.get_questions", new_callable=AsyncMock)
    def test_already_submitted(self, mock_service):
        """Returns already_submitted=True when reflection exists for this week."""
        mock_service.return_value = QUESTIONS_ALREADY_SUBMITTED
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/questions").json()
        assert data["already_submitted"] is True

    @patch("kiro.journey.router.get_questions", new_callable=AsyncMock)
    def test_no_connection_404(self, mock_service):
        """Returns 404 when no partner connection exists."""
        mock_service.side_effect = NoConnectionError()
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/questions")

        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_CONNECTION"

    def test_unauthenticated(self):
        """Returns 401 when not authenticated."""
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/journey/questions")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/journey/reflections
# ─────────────────────────────────────────────────────────────────────────────


class TestSubmitReflection:
    """Tests for POST /api/journey/reflections."""

    VALID_PAYLOAD = {
        "responses": [
            {"question_id": "safety_1", "answer": "4"},
            {"question_id": "conn_2", "answer": "yes"},
            {"question_id": "open_1", "answer": "We talked more this week."},
        ]
    }

    @patch("kiro.journey.router.submit_reflection", new_callable=AsyncMock)
    def test_successful_submission(self, mock_service):
        """Returns confirmation on successful submission."""
        mock_service.return_value = SUBMISSION_RESPONSE
        client = TestClient(_authenticated_app())

        resp = client.post("/api/journey/reflections", json=self.VALID_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "refl-uuid-1"
        assert data["week_number"] == 3
        assert data["week_start"] == "2026-06-22"
        assert "message" in data

    @patch("kiro.journey.router.submit_reflection", new_callable=AsyncMock)
    def test_response_schema(self, mock_service):
        """Response matches ReflectionSubmissionResponse schema."""
        mock_service.return_value = SUBMISSION_RESPONSE
        client = TestClient(_authenticated_app())

        data = client.post("/api/journey/reflections", json=self.VALID_PAYLOAD).json()

        expected_keys = {"id", "week_number", "week_start", "created_at", "message"}
        assert set(data.keys()) == expected_keys

    @patch("kiro.journey.router.submit_reflection", new_callable=AsyncMock)
    def test_duplicate_submission_409(self, mock_service):
        """Returns 409 when reflection already submitted this week."""
        mock_service.side_effect = ReflectionAlreadySubmittedError()
        client = TestClient(_authenticated_app())

        resp = client.post("/api/journey/reflections", json=self.VALID_PAYLOAD)

        assert resp.status_code == 409
        assert resp.json()["code"] == "REFLECTION_ALREADY_SUBMITTED"

    @patch("kiro.journey.router.submit_reflection", new_callable=AsyncMock)
    def test_no_connection_404(self, mock_service):
        """Returns 404 when no partner connection exists."""
        mock_service.side_effect = NoConnectionError()
        client = TestClient(_authenticated_app())

        resp = client.post("/api/journey/reflections", json=self.VALID_PAYLOAD)

        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_CONNECTION"

    def test_empty_responses_422(self):
        """Returns 422 when responses array is empty."""
        client = TestClient(_authenticated_app())
        resp = client.post("/api/journey/reflections", json={"responses": []})
        assert resp.status_code == 422

    def test_missing_responses_422(self):
        """Returns 422 when responses field is missing."""
        client = TestClient(_authenticated_app())
        resp = client.post("/api/journey/reflections", json={})
        assert resp.status_code == 422

    def test_empty_answer_422(self):
        """Returns 422 when an answer is empty string."""
        client = TestClient(_authenticated_app())
        payload = {"responses": [{"question_id": "safety_1", "answer": ""}]}
        resp = client.post("/api/journey/reflections", json=payload)
        assert resp.status_code == 422

    def test_missing_question_id_422(self):
        """Returns 422 when question_id is missing."""
        client = TestClient(_authenticated_app())
        payload = {"responses": [{"answer": "4"}]}
        resp = client.post("/api/journey/reflections", json=payload)
        assert resp.status_code == 422

    def test_too_many_responses_422(self):
        """Returns 422 when more than 5 responses are submitted."""
        client = TestClient(_authenticated_app())
        payload = {"responses": [{"question_id": f"q_{i}", "answer": "x"} for i in range(6)]}
        resp = client.post("/api/journey/reflections", json=payload)
        assert resp.status_code == 422

    def test_unauthenticated(self):
        """Returns 401 when not authenticated."""
        client = TestClient(_unauthenticated_app())
        resp = client.post("/api/journey/reflections", json=self.VALID_PAYLOAD)
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/journey/history
# ─────────────────────────────────────────────────────────────────────────────


class TestGetHistory:
    """Tests for GET /api/journey/history."""

    @patch("kiro.journey.router.get_history", new_callable=AsyncMock)
    def test_successful_history(self, mock_service):
        """Returns reflection history in order."""
        mock_service.return_value = HISTORY_RESPONSE
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["reflections"]) == 2
        assert data["reflections"][0]["week_number"] == 2  # most recent first

    @patch("kiro.journey.router.get_history", new_callable=AsyncMock)
    def test_empty_history(self, mock_service):
        """Returns empty list when no reflections exist."""
        mock_service.return_value = HISTORY_EMPTY
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/history").json()
        assert data["total"] == 0
        assert data["reflections"] == []

    @patch("kiro.journey.router.get_history", new_callable=AsyncMock)
    def test_limit_query_parameter(self, mock_service):
        """Passes limit query parameter to service."""
        mock_service.return_value = HISTORY_EMPTY
        client = TestClient(_authenticated_app())

        client.get("/api/journey/history?limit=5")

        # Verify the service was called with limit=5
        _, kwargs = mock_service.call_args
        assert kwargs.get("limit") == 5

    @patch("kiro.journey.router.get_history", new_callable=AsyncMock)
    def test_limit_default(self, mock_service):
        """Default limit is 20 when not specified."""
        mock_service.return_value = HISTORY_EMPTY
        client = TestClient(_authenticated_app())

        client.get("/api/journey/history")

        _, kwargs = mock_service.call_args
        assert kwargs.get("limit") == 20

    def test_limit_too_high_422(self):
        """Returns 422 when limit exceeds maximum (50)."""
        client = TestClient(_authenticated_app())
        resp = client.get("/api/journey/history?limit=100")
        assert resp.status_code == 422

    def test_limit_too_low_422(self):
        """Returns 422 when limit is less than 1."""
        client = TestClient(_authenticated_app())
        resp = client.get("/api/journey/history?limit=0")
        assert resp.status_code == 422

    @patch("kiro.journey.router.get_history", new_callable=AsyncMock)
    def test_no_connection_404(self, mock_service):
        """Returns 404 when no partner connection exists."""
        mock_service.side_effect = NoConnectionError()
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/history")

        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_CONNECTION"

    def test_unauthenticated(self):
        """Returns 401 when not authenticated."""
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/journey/history")
        assert resp.status_code == 401
