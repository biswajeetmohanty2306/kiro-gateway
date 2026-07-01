# -*- coding: utf-8 -*-
"""Unit tests for the AI Relationship Coach Provider Adapter (J7-G).

Tests use mocked HTTP — never calls the real LLM provider.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from kiro.coach.provider import generate_response
from kiro.coach.types import PromptPackage
from kiro.coach.exceptions import ProviderError


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _package() -> PromptPackage:
    return PromptPackage(
        system_prompt="You are a coach.",
        messages=[{"role": "user", "content": "Hello"}],
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        temperature=0.7,
    )


def _success_response() -> httpx.Response:
    """Mock a successful Anthropic Messages API response."""
    body = {
        "content": [{"type": "text", "text": "I hear you. Tell me more about that."}],
        "model": "claude-sonnet-4-20250514",
        "stop_reason": "end_turn",
    }
    resp = httpx.Response(200, json=body)
    return resp


def _error_response(status: int) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": "Error"}})


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Successful Response
# ─────────────────────────────────────────────────────────────────────────────


class TestSuccessfulResponse:
    """Provider returns assistant text on success."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_returns_text(self):
        """Extracts text content from successful response."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_success_response())

        result = await generate_response(_package(), http_client=client)

        assert result == "I hear you. Tell me more about that."

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_sends_correct_payload(self):
        """Sends properly formatted request to provider."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_success_response())

        await generate_response(_package(), http_client=client)

        call_kwargs = client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "claude-sonnet-4-20250514"
        assert payload["max_tokens"] == 1500
        assert payload["system"] == "You are a coach."
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_sends_auth_header(self):
        """Includes API key in headers."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_success_response())

        await generate_response(_package(), http_client=client)

        call_kwargs = client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["x-api-key"] == "test-key"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Timeout
# ─────────────────────────────────────────────────────────────────────────────


class TestTimeout:
    """Timeout is translated to ProviderError after retries."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_timeout_raises_provider_error(self):
        """Timeout after retries raises ProviderError."""
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_timeout_retries(self):
        """Timeout triggers retries (3 attempts total)."""
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 3  # initial + 2 retries


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Rate Limit
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimit:
    """Rate limit (429) is retried then raises ProviderError."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_rate_limit_retries_then_fails(self):
        """429 response triggers retries then ProviderError."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(429))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 3

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_rate_limit_then_success(self):
        """429 followed by success returns text."""
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            _error_response(429),
            _success_response(),
        ])

        result = await generate_response(_package(), http_client=client)
        assert result == "I hear you. Tell me more about that."
        assert client.post.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Auth Failure
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthFailure:
    """Authentication errors are NOT retried."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "bad-key"})
    async def test_401_no_retry(self):
        """401 raises ProviderError immediately (no retry)."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(401))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 1  # no retry

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": ""})
    async def test_missing_key_raises(self):
        """Missing API key raises ProviderError before HTTP."""
        client = AsyncMock()

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        client.post.assert_not_called()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {}, clear=True)
    async def test_no_env_var_raises(self):
        """No COACH_API_KEY env var raises ProviderError."""
        client = AsyncMock()

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Malformed Response
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedResponse:
    """Malformed responses are translated to ProviderError."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_empty_content(self):
        """Empty content array raises ProviderError."""
        body = {"content": []}
        client = AsyncMock()
        client.post = AsyncMock(return_value=httpx.Response(200, json=body))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_no_text_blocks(self):
        """Content without text blocks raises ProviderError."""
        body = {"content": [{"type": "image", "source": {}}]}
        client = AsyncMock()
        client.post = AsyncMock(return_value=httpx.Response(200, json=body))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_invalid_json(self):
        """Non-JSON response raises ProviderError."""
        client = AsyncMock()
        resp = httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})
        client.post = AsyncMock(return_value=resp)

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Retry Behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestRetryBehavior:
    """Retry logic handles transient vs permanent failures correctly."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_500_retried(self):
        """500 is retried."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(500))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 3

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_503_retried(self):
        """503 is retried."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(503))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 3

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_400_not_retried(self):
        """400 is NOT retried."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(400))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 1

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"COACH_API_KEY": "test-key"})
    async def test_403_not_retried(self):
        """403 is NOT retried."""
        client = AsyncMock()
        client.post = AsyncMock(return_value=_error_response(403))

        with pytest.raises(ProviderError):
            await generate_response(_package(), http_client=client)

        assert client.post.call_count == 1
