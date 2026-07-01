# -*- coding: utf-8 -*-
"""AI Relationship Coach LLM Provider Adapter (J7-G).

Handles all communication with the LLM API.
Translates PromptPackage into HTTP requests and returns plain text.

Responsibilities:
  ✓ HTTP request to LLM provider
  ✓ Authentication via environment variable
  ✓ Timeout handling
  ✓ Retry for transient failures
  ✓ Error translation to ProviderError

Must NEVER know about:
  - Compatibility, journey, relationships, conversations
  - SQL, database, FastAPI
  - Prompt construction logic

Receives PromptPackage. Returns assistant text.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from .exceptions import ProviderError
from .types import PromptPackage


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

_API_KEY_ENV = "COACH_API_KEY"
_API_URL_ENV = "COACH_API_URL"
_DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

_TIMEOUT_SECONDS = 60.0
_MAX_RETRIES = 2
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 529})
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404})


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def generate_response(package: PromptPackage, http_client: httpx.AsyncClient = None) -> str:
    """Send a PromptPackage to the LLM and return the assistant's response text.

    Args:
        package: Complete prompt ready for submission.
        http_client: Optional pre-configured async HTTP client.
            If None, creates a temporary client for this request.

    Returns:
        Plain text response from the assistant.

    Raises:
        ProviderError: On any provider failure (timeout, auth, rate limit, etc.)
    """
    api_key = _get_api_key()
    api_url = os.environ.get(_API_URL_ENV, _DEFAULT_API_URL)
    headers = _build_headers(api_key)
    payload = _build_payload(package)

    return await _execute_with_retry(api_url, headers, payload, http_client)


# ─────────────────────────────────────────────────────────────────────────────
# Request Building
# ─────────────────────────────────────────────────────────────────────────────


def _get_api_key() -> str:
    """Read API key from environment. Raises ProviderError if missing."""
    key = os.environ.get(_API_KEY_ENV, "")
    if not key:
        raise ProviderError()
    return key


def _build_headers(api_key: str) -> Dict[str, str]:
    """Build HTTP headers for the Anthropic Messages API."""
    return {
        "x-api-key": api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }


def _build_payload(package: PromptPackage) -> Dict[str, Any]:
    """Convert PromptPackage into the provider's request body format."""
    return {
        "model": package.model,
        "max_tokens": package.max_tokens,
        "temperature": package.temperature,
        "system": package.system_prompt,
        "messages": package.messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Execution with Retry
# ─────────────────────────────────────────────────────────────────────────────


async def _execute_with_retry(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    http_client: httpx.AsyncClient = None,
) -> str:
    """Execute the HTTP request with retry logic for transient failures.

    Retry policy:
      - Retries on: 429, 500, 502, 503, 529
      - Does NOT retry on: 400, 401, 403, 404
      - Max retries: 2 (3 attempts total)
      - No backoff (provider rate limits handled by caller)
    """
    last_error: Exception = ProviderError()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response_text = await _send_request(url, headers, payload, http_client)
            return response_text
        except _RetryableError as e:
            last_error = e
            if attempt >= _MAX_RETRIES:
                raise ProviderError() from e
            continue
        except _NonRetryableError as e:
            raise ProviderError() from e

    raise ProviderError() from last_error


async def _send_request(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    http_client: httpx.AsyncClient = None,
) -> str:
    """Send a single HTTP request and parse the response.

    Raises:
      _RetryableError: For transient failures (will be retried)
      _NonRetryableError: For permanent failures (will not be retried)
    """
    try:
        if http_client:
            response = await http_client.post(
                url, headers=headers, json=payload, timeout=_TIMEOUT_SECONDS
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, headers=headers, json=payload, timeout=_TIMEOUT_SECONDS
                )
    except httpx.TimeoutException as e:
        raise _RetryableError("Request timed out") from e
    except httpx.RequestError as e:
        raise _RetryableError(f"Network error: {e}") from e

    # Handle HTTP status
    if response.status_code in _RETRYABLE_STATUS_CODES:
        raise _RetryableError(f"Provider returned {response.status_code}")

    if response.status_code in _NON_RETRYABLE_STATUS_CODES:
        raise _NonRetryableError(f"Provider returned {response.status_code}")

    if response.status_code != 200:
        raise _NonRetryableError(f"Unexpected status {response.status_code}")

    # Parse response
    return _extract_text(response)


def _extract_text(response: httpx.Response) -> str:
    """Extract assistant text from the provider response.

    Expects Anthropic Messages API format:
      {"content": [{"type": "text", "text": "..."}]}
    """
    try:
        body = response.json()
    except Exception as e:
        raise _NonRetryableError("Malformed JSON response") from e

    content = body.get("content", [])
    if not content:
        raise _NonRetryableError("Empty response content")

    # Extract text from content blocks
    texts: List[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                texts.append(text)

    if not texts:
        raise _NonRetryableError("No text content in response")

    return "\n".join(texts)


# ─────────────────────────────────────────────────────────────────────────────
# Internal Error Types (never leak outside this module)
# ─────────────────────────────────────────────────────────────────────────────


class _RetryableError(Exception):
    """Transient failure that should be retried."""
    pass


class _NonRetryableError(Exception):
    """Permanent failure that should not be retried."""
    pass
