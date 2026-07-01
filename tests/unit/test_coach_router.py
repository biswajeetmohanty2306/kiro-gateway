# -*- coding: utf-8 -*-
"""Unit tests for the AI Relationship Coach Router (J7-H)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.coach.router import router
from kiro.coach.exceptions import (
    CoachError,
    ConversationCompletedError,
    ConversationLimitError,
    ConversationNotFoundError,
    NoConnectionError,
    ProviderError,
    TurnLimitError,
    MessageTooLongError,
    RateLimitError,
)
from kiro.supabase_auth.dependencies import get_current_user_profile
from kiro.supabase_auth.profile import UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

MOCK_USER = UserProfile(user_id="user-1", email="alice@test.com", name="Alice", onboarding_completed=True)


def _create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    mock_auth = MagicMock()
    mock_auth._audit_pool = MagicMock()
    app.state.supabase_auth = mock_auth

    @app.exception_handler(CoachError)
    async def _handle(request, exc: CoachError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})

    return app


def _authenticated_app() -> FastAPI:
    app = _create_app()
    app.dependency_overrides[get_current_user_profile] = lambda: MOCK_USER
    return app


def _unauthenticated_app() -> FastAPI:
    from kiro.supabase_auth.exceptions import InvalidTokenError, SupabaseAuthError
    app = _create_app()

    @app.exception_handler(SupabaseAuthError)
    async def _auth(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"code": "INVALID_TOKEN", "message": str(exc)})

    app.dependency_overrides[get_current_user_profile] = lambda: (_ for _ in ()).throw(InvalidTokenError("No auth"))
    return app


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/coach/conversations — Start
# ─────────────────────────────────────────────────────────────────────────────


class TestStartConversation:

    @patch("kiro.coach.router.start_conversation", new_callable=AsyncMock)
    def test_success(self, mock_svc):
        mock_svc.return_value = {"conversation_id": "c1", "status": "active", "greeting": "Hi Alice.", "started_at": "2026-07-01T10:00:00Z"}
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations")
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "c1"
        assert resp.json()["greeting"] == "Hi Alice."

    @patch("kiro.coach.router.start_conversation", new_callable=AsyncMock)
    def test_no_connection_404(self, mock_svc):
        mock_svc.side_effect = NoConnectionError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations")
        assert resp.status_code == 404

    @patch("kiro.coach.router.start_conversation", new_callable=AsyncMock)
    def test_limit_409(self, mock_svc):
        mock_svc.side_effect = ConversationLimitError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations")
        assert resp.status_code == 409

    def test_unauthenticated_401(self):
        client = TestClient(_unauthenticated_app())
        resp = client.post("/api/coach/conversations")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/coach/conversations — List
# ─────────────────────────────────────────────────────────────────────────────


class TestListConversations:

    @patch("kiro.coach.router.list_conversations", new_callable=AsyncMock)
    def test_success(self, mock_svc):
        mock_svc.return_value = {"conversations": [{"id": "c1", "status": "active", "turn_count": 3, "started_at": "2026-07-01T10:00:00Z"}]}
        client = TestClient(_authenticated_app())
        resp = client.get("/api/coach/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) == 1

    @patch("kiro.coach.router.list_conversations", new_callable=AsyncMock)
    def test_empty(self, mock_svc):
        mock_svc.return_value = {"conversations": []}
        client = TestClient(_authenticated_app())
        resp = client.get("/api/coach/conversations")
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []

    def test_unauthenticated_401(self):
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/coach/conversations")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/coach/conversations/{id} — Get
# ─────────────────────────────────────────────────────────────────────────────


class TestGetConversation:

    @patch("kiro.coach.router.get_conversation", new_callable=AsyncMock)
    def test_success(self, mock_svc):
        mock_svc.return_value = {
            "id": "c1", "status": "active", "turn_count": 2, "started_at": "2026-07-01T10:00:00Z",
            "messages": [{"role": "user", "content": "Hi", "turn_number": 1}],
        }
        client = TestClient(_authenticated_app())
        resp = client.get("/api/coach/conversations/c1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "c1"
        assert len(resp.json()["messages"]) == 1

    @patch("kiro.coach.router.get_conversation", new_callable=AsyncMock)
    def test_not_found_404(self, mock_svc):
        mock_svc.side_effect = ConversationNotFoundError()
        client = TestClient(_authenticated_app())
        resp = client.get("/api/coach/conversations/bad")
        assert resp.status_code == 404

    def test_unauthenticated_401(self):
        client = TestClient(_unauthenticated_app())
        resp = client.get("/api/coach/conversations/c1")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/coach/conversations/{id}/messages — Send
# ─────────────────────────────────────────────────────────────────────────────


class TestSendMessage:

    @patch("kiro.coach.router.send_message", new_callable=AsyncMock)
    def test_success(self, mock_svc):
        mock_svc.return_value = {"conversation_id": "c1", "response": "I hear you.", "turn_number": 4, "safety_action": None}
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "I feel disconnected."})
        assert resp.status_code == 200
        assert resp.json()["response"] == "I hear you."

    @patch("kiro.coach.router.send_message", new_callable=AsyncMock)
    def test_not_found_404(self, mock_svc):
        mock_svc.side_effect = ConversationNotFoundError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/bad/messages", json={"message": "Hi"})
        assert resp.status_code == 404

    @patch("kiro.coach.router.send_message", new_callable=AsyncMock)
    def test_completed_409(self, mock_svc):
        mock_svc.side_effect = ConversationCompletedError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "Hi"})
        assert resp.status_code == 409

    @patch("kiro.coach.router.send_message", new_callable=AsyncMock)
    def test_turn_limit_409(self, mock_svc):
        mock_svc.side_effect = TurnLimitError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "Hi"})
        assert resp.status_code == 409

    @patch("kiro.coach.router.send_message", new_callable=AsyncMock)
    def test_provider_503(self, mock_svc):
        mock_svc.side_effect = ProviderError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "Hi"})
        assert resp.status_code == 503

    def test_empty_message_422(self):
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": ""})
        assert resp.status_code == 422

    def test_missing_message_422(self):
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={})
        assert resp.status_code == 422

    def test_too_long_message_422(self):
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "x" * 2001})
        assert resp.status_code == 422

    def test_unauthenticated_401(self):
        client = TestClient(_unauthenticated_app())
        resp = client.post("/api/coach/conversations/c1/messages", json={"message": "Hi"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/coach/conversations/{id}/complete — Complete
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteConversation:

    @patch("kiro.coach.router.complete_conversation", new_callable=AsyncMock)
    def test_success(self, mock_svc):
        mock_svc.return_value = {"conversation_id": "c1", "status": "completed"}
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @patch("kiro.coach.router.complete_conversation", new_callable=AsyncMock)
    def test_not_found_404(self, mock_svc):
        mock_svc.side_effect = ConversationNotFoundError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/bad/complete")
        assert resp.status_code == 404

    @patch("kiro.coach.router.complete_conversation", new_callable=AsyncMock)
    def test_already_completed_409(self, mock_svc):
        mock_svc.side_effect = ConversationCompletedError()
        client = TestClient(_authenticated_app())
        resp = client.post("/api/coach/conversations/c1/complete")
        assert resp.status_code == 409

    def test_unauthenticated_401(self):
        client = TestClient(_unauthenticated_app())
        resp = client.post("/api/coach/conversations/c1/complete")
        assert resp.status_code == 401
