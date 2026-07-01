# -*- coding: utf-8 -*-
"""Unit tests for the Journey Timeline API endpoint (J6-B)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.journey.router import router
from kiro.journey.exceptions import JourneyError, NoConnectionError
from kiro.supabase_auth.dependencies import get_current_user_profile
from kiro.supabase_auth.profile import UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

MOCK_USER = UserProfile(
    user_id="user-123",
    email="alice@example.com",
    name="Alice",
    onboarding_completed=True,
)

TIMELINE_WITH_EVENTS = {
    "events": [
        {
            "event_type": "relationship_started",
            "title": "Relationship Started",
            "description": "You connected as partners.",
            "occurred_at": "2026-04-28",
            "week_number": None,
            "is_current": False,
            "metadata": None,
        },
        {
            "event_type": "report_generated",
            "title": "Compatibility Report Generated",
            "description": "Your first shared understanding.",
            "occurred_at": "2026-05-01",
            "week_number": None,
            "is_current": False,
            "metadata": None,
        },
        {
            "event_type": "journey_started",
            "title": "Journey Began",
            "description": "Weekly reflections started.",
            "occurred_at": "2026-05-01",
            "week_number": 1,
            "is_current": False,
            "metadata": None,
        },
        {
            "event_type": "reflection",
            "title": "Week 1 Reflection",
            "description": "Weekly check-in completed.",
            "occurred_at": "2026-05-08",
            "week_number": 1,
            "is_current": False,
            "metadata": None,
        },
        {
            "event_type": "current_week",
            "title": "Week 5",
            "description": "This is where you are now.",
            "occurred_at": "2026-06-01",
            "week_number": 5,
            "is_current": True,
            "metadata": None,
        },
        {
            "event_type": "upcoming",
            "title": "1 Month Together",
            "description": "A month of paying attention to each other.",
            "occurred_at": None,
            "week_number": None,
            "is_current": False,
            "metadata": {"days_remaining": 10},
        },
    ],
}

TIMELINE_EMPTY = {"events": []}


def _create_app() -> FastAPI:
    """Build a minimal FastAPI app with the journey router and exception handler."""
    app = FastAPI()
    app.include_router(router)

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
    app = _create_app()
    app.dependency_overrides[get_current_user_profile] = lambda: MOCK_USER
    return app


def _unauthenticated_app() -> FastAPI:
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
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTimeline:
    """Tests for GET /api/journey/timeline."""

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_timeline_with_events(self, mock_service):
        """Returns timeline events when journey is active."""
        mock_service.return_value = TIMELINE_WITH_EVENTS
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/timeline")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert len(data["events"]) == 6

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_empty_timeline(self, mock_service):
        """Returns empty events list when no journey data exists."""
        mock_service.return_value = TIMELINE_EMPTY
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/timeline")

        assert resp.status_code == 200
        assert resp.json()["events"] == []

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_chronological_ordering(self, mock_service):
        """Events are in chronological order."""
        mock_service.return_value = TIMELINE_WITH_EVENTS
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/timeline").json()
        dates = [e["occurred_at"] for e in data["events"] if e["occurred_at"]]
        assert dates == sorted(dates)

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_event_structure(self, mock_service):
        """Each event has all required fields."""
        mock_service.return_value = TIMELINE_WITH_EVENTS
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/timeline").json()
        required_keys = {"event_type", "title", "description", "occurred_at", "week_number", "is_current", "metadata"}
        for event in data["events"]:
            assert set(event.keys()) == required_keys

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_current_week_marker(self, mock_service):
        """Timeline contains exactly one current week marker."""
        mock_service.return_value = TIMELINE_WITH_EVENTS
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/timeline").json()
        current_events = [e for e in data["events"] if e["is_current"]]
        assert len(current_events) == 1
        assert current_events[0]["event_type"] == "current_week"

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_upcoming_event_metadata(self, mock_service):
        """Upcoming events have metadata with remaining count."""
        mock_service.return_value = TIMELINE_WITH_EVENTS
        client = TestClient(_authenticated_app())

        data = client.get("/api/journey/timeline").json()
        upcoming = [e for e in data["events"] if e["event_type"] == "upcoming"]
        assert len(upcoming) == 1
        assert upcoming[0]["metadata"]["days_remaining"] == 10

    @patch("kiro.journey.router.get_timeline", new_callable=AsyncMock)
    def test_no_connection_404(self, mock_service):
        """Returns 404 when no partner connection exists."""
        mock_service.side_effect = NoConnectionError()
        client = TestClient(_authenticated_app())

        resp = client.get("/api/journey/timeline")

        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_CONNECTION"

    def test_unauthenticated(self):
        """Returns 401 when not authenticated."""
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/journey/timeline")
        assert resp.status_code == 401
