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
Pure, source-agnostic rate-limiter primitive for Phase C (milestone M3, M3-D5).

This is the *mechanism* for auth-failure throttling (review S3, "non-deferrable").
It is intentionally FastAPI-free and source-agnostic: callers pass an opaque
string key (an IP, a token-subject, etc.). M7 wires it by feeding the real
client source as that key — only the *wiring* is deferred, not the mechanism.

Design:
  - Fixed-window counter per key: up to ``limit`` allowed events per
    ``window_seconds``; the (limit+1)th in a window is rejected; the window
    resets once it elapses.
  - Bounded memory: a hard LRU cap on the number of tracked keys, so the limiter
    itself cannot become a memory-DoS vector under a distinct-key flood.
  - Deterministic time via an injected ``time_fn`` (tests advance a fake clock;
    no real sleeps).

Not safe to share across event loops; safe within one (operations are synchronous
and atomic from the event loop's perspective — no awaits inside).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable, Tuple


class FixedWindowRateLimiter:
    """
    Allow up to ``limit`` events per ``window_seconds`` per opaque key.

    ``allow(key)`` returns True if the event is within budget (and records it),
    False if the key has exhausted its budget for the current window.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        max_keys: int = 10000,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._time_fn = time_fn
        # key -> (window_start, count); ordered for LRU eviction.
        self._state: "OrderedDict[str, Tuple[float, int]]" = OrderedDict()

    def allow(self, key: str) -> bool:
        """
        Record an event for ``key`` and report whether it is within budget.

        Returns True and counts the event when within the limit; returns False
        (without exceeding the recorded count beyond the limit) when the key has
        already used its full budget for the current window.
        """
        now = self._time_fn()
        window_start, count = self._state.get(key, (now, 0))

        if (now - window_start) >= self._window:
            # Window elapsed → reset.
            window_start, count = now, 0

        if count >= self._limit:
            self._state[key] = (window_start, count)
            self._state.move_to_end(key)
            self._evict_if_needed()
            return False

        self._state[key] = (window_start, count + 1)
        self._state.move_to_end(key)
        self._evict_if_needed()
        return True

    def reset(self, key: str) -> None:
        """Forget any state for ``key`` (e.g. after a successful auth)."""
        self._state.pop(key, None)

    def _evict_if_needed(self) -> None:
        while len(self._state) > self._max_keys:
            self._state.popitem(last=False)  # evict least-recently-used
