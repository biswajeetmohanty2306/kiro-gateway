# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Request-id correlation primitive for Phase C (milestone M6).

A framework-agnostic ``ContextVar`` holding the current request's correlation
id, plus helpers to generate, sanitize, set, and read it. The
``RequestIdMiddleware`` (request_id_middleware.py) drives this per request; the
``get_current_user`` dependency reads it to thread ``request_id`` into audit
events (M5) and loguru lines.

Why correlation lives in a ContextVar (not only on ``request.state``): loguru
sinks and best-effort background audit tasks run outside the request handler's
direct call stack, so a context-local value is the reliable way for any log
line in the request's logical flow to carry the same id.

Security note: an inbound ``X-Request-Id`` header is UNTRUSTED. It is sanitized
(charset + length bounded) before use so it cannot inject newlines or control
characters into the log stream. A value that fails sanitization is discarded
and a fresh id is generated instead.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

# The current request's correlation id. ``None`` outside any request (e.g. at
# import time, in startup logs, or in a plain unit test that never set it).
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Inbound ids must be short and printable-safe. We allow the characters common
# to UUIDs and trace ids (hex, dashes, underscores, dots) and nothing else, so a
# forged header can never carry a newline / ANSI / control sequence into logs.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def generate_request_id() -> str:
    """Return a fresh, unique correlation id (uuid4 hex-with-dashes)."""
    return str(uuid.uuid4())


def sanitize_request_id(raw: Optional[str]) -> Optional[str]:
    """
    Return a safe-to-log inbound id, or ``None`` if it is absent/unacceptable.

    Trims surrounding whitespace, then accepts only a bounded printable charset
    (``[A-Za-z0-9._-]``, 1–128 chars). Anything else — empty, too long, or
    containing whitespace/control/injection characters — yields ``None`` so the
    caller falls back to :func:`generate_request_id`.
    """
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if _SAFE_REQUEST_ID.match(candidate):
        return candidate
    return None


def set_request_id(request_id: str):
    """
    Bind ``request_id`` to the current context.

    Returns the ContextVar ``Token`` so the caller (middleware) can reset the
    context after the request, preventing id bleed across tasks that reuse a
    context.
    """
    return _request_id_var.set(request_id)


def reset_request_id(token) -> None:
    """Restore the previous context value using a token from :func:`set_request_id`."""
    try:
        _request_id_var.reset(token)
    except (ValueError, LookupError, RuntimeError):
        # Token already used, or created in a different context (e.g. crossed
        # task boundaries in tests). Best-effort reset — never raise on cleanup.
        pass


def get_request_id() -> Optional[str]:
    """Return the current request's correlation id, or ``None`` if unset."""
    return _request_id_var.get()
