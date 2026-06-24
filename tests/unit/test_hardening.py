# -*- coding: utf-8 -*-
"""Unit tests for production hardening (F7A).

Tests:
- Security headers middleware
- Response timing middleware
- Global exception handler
- Health check endpoint
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from kiro.hardening import (
    SecurityHeadersMiddleware,
    ResponseTimingMiddleware,
    register_global_exception_handler,
    register_health_endpoint,
    SLOW_REQUEST_THRESHOLD_MS,
)


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with hardening middleware."""
    app = FastAPI()
    app.add_middleware(ResponseTimingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    register_global_exception_handler(app)
    register_health_endpoint(app)

    @app.get("/test-ok")
    async def test_ok():
        return {"message": "ok"}

    @app.get("/test-error")
    async def test_error():
        raise RuntimeError("Something went wrong internally")

    @app.get("/test-value-error")
    async def test_value_error():
        raise ValueError("Bad value")

    return app


# =============================================================================
# Security Headers
# =============================================================================

class TestSecurityHeaders:
    """Verify security headers are present on all responses."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)

    def test_x_content_type_options(self):
        """X-Content-Type-Options: nosniff is set."""
        r = self.client.get("/test-ok")
        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self):
        """X-Frame-Options: DENY is set."""
        r = self.client.get("/test-ok")
        assert r.headers["X-Frame-Options"] == "DENY"

    def test_referrer_policy(self):
        """Referrer-Policy is set."""
        r = self.client.get("/test-ok")
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_x_xss_protection(self):
        """X-XSS-Protection: 0 (disabled for modern browsers)."""
        r = self.client.get("/test-ok")
        assert r.headers["X-XSS-Protection"] == "0"

    def test_headers_on_404(self):
        """Security headers present on 404."""
        r = self.client.get("/nonexistent-route")
        assert r.headers["X-Content-Type-Options"] == "nosniff"


# =============================================================================
# Response Timing
# =============================================================================

class TestResponseTiming:
    """Verify X-Response-Time header is present."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)

    def test_response_time_header_present(self):
        """X-Response-Time header is present on responses."""
        r = self.client.get("/test-ok")
        assert "X-Response-Time" in r.headers

    def test_response_time_format(self):
        """X-Response-Time has ms suffix."""
        r = self.client.get("/test-ok")
        value = r.headers["X-Response-Time"]
        assert value.endswith("ms")
        # Should be a valid number
        ms_value = float(value.replace("ms", ""))
        assert ms_value >= 0

    def test_response_time_on_normal_requests(self):
        """X-Response-Time present on successful responses."""
        r = self.client.get("/test-ok")
        assert "X-Response-Time" in r.headers


# =============================================================================
# Global Exception Handler
# =============================================================================

class TestGlobalExceptionHandler:
    """Verify unhandled exceptions return structured JSON."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_unhandled_runtime_error_returns_500(self):
        """RuntimeError returns 500 with structured body."""
        r = self.client.get("/test-error")
        assert r.status_code == 500
        body = r.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert body["message"] == "An unexpected error occurred. Please try again."

    def test_unhandled_value_error_returns_500(self):
        """ValueError also caught by global handler."""
        r = self.client.get("/test-value-error")
        assert r.status_code == 500
        body = r.json()
        assert body["code"] == "INTERNAL_ERROR"

    def test_no_stack_trace_in_response(self):
        """Response body never contains stack trace or internal details."""
        r = self.client.get("/test-error")
        body_str = r.text
        assert "Traceback" not in body_str
        assert "RuntimeError" not in body_str
        assert "Something went wrong internally" not in body_str

    def test_normal_request_not_affected(self):
        """Normal successful requests still return 200."""
        r = self.client.get("/test-ok")
        assert r.status_code == 200
        assert r.json() == {"message": "ok"}


# =============================================================================
# Health Check Endpoint
# =============================================================================

class TestHealthEndpoint:
    """Verify health check endpoint."""

    def test_health_returns_200_with_db(self):
        """Health endpoint returns 200 when DB is available."""
        app = _create_test_app()

        # Mock supabase_auth with a working pool
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        class MockPool:
            @asynccontextmanager
            async def acquire(self):
                yield mock_conn

        mock_auth = MagicMock()
        mock_auth._audit_pool = MockPool()
        app.state.supabase_auth = mock_auth

        client = TestClient(app)
        r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "connected"
        assert "version" in body

    def test_health_returns_503_when_db_fails(self):
        """Health endpoint returns 503 when DB is unreachable."""
        app = _create_test_app()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=Exception("Connection refused"))

        class MockPool:
            @asynccontextmanager
            async def acquire(self):
                yield mock_conn

        mock_auth = MagicMock()
        mock_auth._audit_pool = MockPool()
        app.state.supabase_auth = mock_auth

        client = TestClient(app)
        r = client.get("/health")

        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["db"] == "error"

    def test_health_returns_503_when_no_auth(self):
        """Health endpoint returns 503 when supabase_auth is None."""
        app = _create_test_app()
        app.state.supabase_auth = None

        client = TestClient(app)
        r = client.get("/health")

        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["db"] == "disconnected"

    def test_health_has_security_headers(self):
        """Health endpoint also gets security headers."""
        app = _create_test_app()
        app.state.supabase_auth = None

        client = TestClient(app)
        r = client.get("/health")

        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_health_has_response_time(self):
        """Health endpoint also gets response timing."""
        app = _create_test_app()
        app.state.supabase_auth = None

        client = TestClient(app)
        r = client.get("/health")

        assert "X-Response-Time" in r.headers
