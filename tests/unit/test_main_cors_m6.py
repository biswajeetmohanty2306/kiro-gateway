# -*- coding: utf-8 -*-

"""
M6 regression: CORS headers survive the post-M6 middleware ordering on the REAL
app (main.app), where CORS is now outermost (CORS -> RequestId -> Debug, M6-D4).

These exercise main.app directly (not the minimal app in test_cors_policy.py) to
prove the reorder did not strip Access-Control-Allow-Origin from:
  1. a successful response (/health), and
  2. a 422 validation-error response (an existing endpoint).

Auth-failure CORS is intentionally NOT tested here: no authenticated route exists
yet and HTTP auth mapping belongs to M7.

TestClient is used WITHOUT the context manager on purpose, so the heavy lifespan
(account/token initialization) does not run — neither path under test touches
app.state, so the wiring is irrelevant to these assertions.
"""

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import pytest

import main
from kiro.config import PROXY_API_KEY

LISTED_ORIGIN = "https://app.example.com"


@pytest.fixture
def client_with_listed_origin():
    """
    Configure main.app's CORS middleware with a listed origin for the duration of
    the test, then restore it. main.app is built with an empty allowlist in the
    test environment; a real deployment sets USER_AUTH_CORS_ALLOWED_ORIGINS, which
    is exactly the state we reproduce here. Mutating the registered middleware's
    kwargs and clearing middleware_stack forces FastAPI to rebuild the stack with
    the new origin on next request.
    """
    cors_mw = next(
        mw for mw in main.app.user_middleware if mw.cls is CORSMiddleware
    )
    original = cors_mw.kwargs.get("allow_origins")
    cors_mw.kwargs["allow_origins"] = [LISTED_ORIGIN]
    main.app.middleware_stack = None  # force rebuild with the new origin

    # No `with` => lifespan does NOT run (avoids account/token startup).
    client = TestClient(main.app)
    try:
        yield client
    finally:
        cors_mw.kwargs["allow_origins"] = original
        main.app.middleware_stack = None  # rebuild back to the original policy


class TestCorsHeadersOnMainApp:
    """ACAO present on success and on a 422, with CORS now outermost (M6-D4)."""

    def test_acao_present_on_successful_response(self, client_with_listed_origin):
        # 1. Successful path: /health (no auth, no app.state).
        resp = client_with_listed_origin.get(
            "/health", headers={"Origin": LISTED_ORIGIN}
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == LISTED_ORIGIN

    def test_acao_present_on_validation_error(self, client_with_listed_origin):
        # 2. Validation-error path: a valid API key gets past verify_api_key (which
        #    would otherwise 401 before validation); an invalid body then yields a
        #    422 from validation_exception_handler. CORS, being outermost, must
        #    still stamp ACAO on that 422.
        resp = client_with_listed_origin.post(
            "/v1/chat/completions",
            headers={
                "Origin": LISTED_ORIGIN,
                "Authorization": f"Bearer {PROXY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"not_a_valid": "chat completion request"},  # missing required fields
        )
        assert resp.status_code == 422  # validation error, not auth/other
        assert resp.headers.get("access-control-allow-origin") == LISTED_ORIGIN

    def test_request_id_echoed_alongside_cors(self, client_with_listed_origin):
        # Sanity that the new middleware coexists: X-Request-Id is also present.
        resp = client_with_listed_origin.get(
            "/health", headers={"Origin": LISTED_ORIGIN}
        )
        assert resp.headers.get("access-control-allow-origin") == LISTED_ORIGIN
        assert resp.headers.get("x-request-id")  # RequestIdMiddleware ran too
