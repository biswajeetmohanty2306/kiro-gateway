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
Request-id correlation middleware for Phase C (milestone M6).

For every request it:
  1. reads an inbound ``X-Request-Id`` header, sanitizing it (untrusted input);
     if absent/unacceptable, generates a fresh uuid4;
  2. binds the id to the context (``context.set_request_id``) so any log line or
     best-effort audit task in the request's flow carries it;
  3. stores it on ``request.state.request_id`` for handlers/dependencies;
  4. echoes it back on the response ``X-Request-Id`` header for client/proxy
     correlation.

App-wide by design (M6-D3): every request — including the existing ``/v1``
routes and any future auth failure — becomes correlatable. The middleware reads
and sets only a header and a context value; it never touches the response body.

Ordering (M6-D4, resolved): CORS (outermost) → RequestIdMiddleware →
DebugLoggerMiddleware, so debug log lines already carry the request id.

This mirrors the existing ``DebugLoggerMiddleware`` (``BaseHTTPMiddleware``).
"""

from __future__ import annotations

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .context import (
    generate_request_id,
    sanitize_request_id,
    set_request_id,
    reset_request_id,
)

# Canonical header name used for both the inbound read and the outbound echo.
REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a correlation id per request (see module docstring)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Resolve the id: prefer a clean inbound header, else generate.
        inbound = request.headers.get(REQUEST_ID_HEADER)
        request_id = sanitize_request_id(inbound) or generate_request_id()

        # 2. Bind to the context (resettable token to avoid cross-task bleed).
        token = set_request_id(request_id)
        # 3. Expose on request.state for handlers/dependencies.
        request.state.request_id = request_id

        # 4. Bind to loguru for the duration of this request so every line in
        #    the flow carries request_id, then always reset the context.
        try:
            with logger.contextualize(request_id=request_id):
                response = await call_next(request)
        finally:
            reset_request_id(token)

        # 5. Echo for client/proxy correlation.
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
