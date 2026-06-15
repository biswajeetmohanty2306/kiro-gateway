# -*- coding: utf-8 -*-

"""
Unit tests for the pure rate-limiter primitive (kiro/supabase_auth/ratelimit.py).

M3-D5: this is the source-agnostic mechanism for auth-failure throttling; the
per-IP wiring is M7. Timing is deterministic via an injected clock.
"""

import pytest

from kiro.supabase_auth.ratelimit import FixedWindowRateLimiter


def make_limiter(limit=3, window=60, max_keys=1000, clock=None):
    kwargs = {"max_keys": max_keys}
    if clock is not None:
        kwargs["time_fn"] = clock
    return FixedWindowRateLimiter(limit, window, **kwargs)


class TestBudget:
    def test_allows_up_to_limit_then_rejects(self):
        clock = {"t": 0.0}
        rl = make_limiter(limit=3, window=60, clock=lambda: clock["t"])
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False  # 4th in window rejected

    def test_window_resets(self):
        clock = {"t": 0.0}
        rl = make_limiter(limit=2, window=60, clock=lambda: clock["t"])
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False

        clock["t"] += 60  # window elapsed
        assert rl.allow("ip-1") is True

    def test_distinct_keys_independent(self):
        clock = {"t": 0.0}
        rl = make_limiter(limit=1, window=60, clock=lambda: clock["t"])
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False
        assert rl.allow("ip-2") is True  # a different source is unaffected

    def test_reset_clears_key(self):
        clock = {"t": 0.0}
        rl = make_limiter(limit=1, window=60, clock=lambda: clock["t"])
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False
        rl.reset("ip-1")
        assert rl.allow("ip-1") is True


class TestBoundedMemory:
    def test_max_keys_bounded_lru(self):
        clock = {"t": 0.0}
        rl = make_limiter(limit=5, window=60, max_keys=4, clock=lambda: clock["t"])
        for i in range(20):
            rl.allow(f"ip-{i}")
        assert len(rl._state) == 4  # bounded; the limiter is not a memory-DoS


class TestConstruction:
    @pytest.mark.parametrize(
        "limit,window,max_keys",
        [(0, 60, 10), (-1, 60, 10), (3, 0, 10), (3, -1, 10), (3, 60, 0)],
    )
    def test_invalid_construction_rejected(self, limit, window, max_keys):
        with pytest.raises(ValueError):
            FixedWindowRateLimiter(limit, window, max_keys=max_keys)
