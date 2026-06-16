# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C request-id middleware
(kiro/supabase_auth/request_id_middleware.py, M6).

Drives the middleware through a minimal Starlette app + TestClient: id is
generated when absent, preserved (and sanitized) when inbound, echoed on the
response, and exposed on request.state.
"""

import uuid

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kiro.supabase_auth.request_id_middleware import (
    RequestIdMiddleware,
    REQUEST_ID_HEADER,
)
from kiro.supabase_auth.context import get_request_id


async def _echo(request):
    # Surface what the middleware put on request.state and in the context.
    return JSONResponse(
        {
            "state_request_id": getattr(request.state, "request_id", None),
            "ctx_request_id": get_request_id(),
        }
    )


def make_client() -> TestClient:
    app = Starlette(routes=[Route("/echo", _echo)])
    app.add_middleware(RequestIdMiddleware)
    return TestClient(app)


class TestRequestIdMiddleware:
    def test_generates_id_when_absent(self):
        client = make_client()
        resp = client.get("/echo")
        assert resp.status_code == 200
        rid = resp.headers.get(REQUEST_ID_HEADER)
        assert rid is not None
        # Generated ids are uuid4.
        assert str(uuid.UUID(rid)) == rid
        # Same id on response header, request.state, and context.
        assert resp.json()["state_request_id"] == rid
        assert resp.json()["ctx_request_id"] == rid

    def test_preserves_clean_inbound_id(self):
        client = make_client()
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: "trace-abc_123"})
        assert resp.headers[REQUEST_ID_HEADER] == "trace-abc_123"
        assert resp.json()["state_request_id"] == "trace-abc_123"

    def test_replaces_malformed_inbound_id(self):
        client = make_client()
        # Newline injection attempt must be discarded and a fresh id generated.
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: "bad\nid"})
        rid = resp.headers[REQUEST_ID_HEADER]
        assert rid != "bad\nid"
        assert "\n" not in rid
        assert str(uuid.UUID(rid)) == rid  # fell back to generated uuid4

    def test_echoes_on_response(self):
        client = make_client()
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: "abc123"})
        assert resp.headers[REQUEST_ID_HEADER] == "abc123"

    def test_distinct_ids_across_requests(self):
        client = make_client()
        r1 = client.get("/echo").headers[REQUEST_ID_HEADER]
        r2 = client.get("/echo").headers[REQUEST_ID_HEADER]
        assert r1 != r2

    def test_context_cleared_after_request(self):
        client = make_client()
        client.get("/echo")
        # Outside any request the context must not retain the last id.
        assert get_request_id() is None
