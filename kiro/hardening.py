# -*- coding: utf-8 -*-
"""Production hardening middleware and utilities (F7A).

Provides:
- Security headers middleware
- Request timing middleware (X-Response-Time header + slow request logging)
- Global unhandled exception handler
- Health check endpoint
"""

from __future__ import annotations

import time
import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Threshold for slow request warning (milliseconds)
SLOW_REQUEST_THRESHOLD_MS = 1000


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses.

    Headers:
    - X-Content-Type-Options: nosniff (prevent MIME-type sniffing)
    - X-Frame-Options: DENY (prevent clickjacking)
    - Referrer-Policy: strict-origin-when-cross-origin
    - X-XSS-Protection: 0 (disabled — modern browsers use CSP instead)
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # Let exception propagate to the exception handler, but still
            # need to raise it so FastAPI's handler can produce the response.
            raise
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        return response


class ResponseTimingMiddleware(BaseHTTPMiddleware):
    """
    Measures request processing time and adds X-Response-Time header.

    Logs a warning for requests exceeding SLOW_REQUEST_THRESHOLD_MS.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log timing even on exceptions, then re-raise for exception handler
            duration_ms = (time.perf_counter() - start) * 1000
            if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
                logger.warning(
                    "Slow request (failed): %s %s took %.0fms",
                    request.method, request.url.path, duration_ms,
                )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "Slow request: %s %s took %.0fms",
                request.method,
                request.url.path,
                duration_ms,
            )

        return response


def register_global_exception_handler(app: FastAPI) -> None:
    """
    Register a catch-all handler for unhandled exceptions.

    Ensures:
    - Structured JSON response (never raw stack traces)
    - 500 status code
    - Logs the full exception for debugging
    - Never exposes internal details to clients
    """

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the full exception with traceback
        logger.exception(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
            },
        )


def register_health_endpoint(app: FastAPI) -> None:
    """
    Register the health check endpoint at GET /health.

    Returns service status including DB connectivity.
    """
    from kiro.config import APP_VERSION

    @app.get("/health", tags=["Health"])
    async def health_check(request: Request) -> dict:
        """Health check endpoint. Returns service status."""
        db_status = "disconnected"

        # Check DB pool availability
        supabase_auth = getattr(request.app.state, "supabase_auth", None)
        if supabase_auth is not None:
            pool = getattr(supabase_auth, "_audit_pool", None)
            if pool is not None:
                try:
                    async with pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    db_status = "connected"
                except Exception:
                    db_status = "error"

        status = "ok" if db_status == "connected" else "degraded"
        status_code = 200 if status == "ok" else 503

        response = {
            "status": status,
            "db": db_status,
            "version": APP_VERSION,
        }

        if status_code != 200:
            return JSONResponse(status_code=status_code, content=response)

        return response
