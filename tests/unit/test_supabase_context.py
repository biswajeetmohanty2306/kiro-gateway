# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C request-id context primitive
(kiro/supabase_auth/context.py, M6).

No framework, no app — pure ContextVar behavior, generation, and the
sanitization that defends the log stream against a forged X-Request-Id.
"""

import uuid

from kiro.supabase_auth.context import (
    generate_request_id,
    sanitize_request_id,
    set_request_id,
    reset_request_id,
    get_request_id,
)


class TestGenerate:
    def test_generate_is_valid_uuid(self):
        rid = generate_request_id()
        # Parses as a uuid4 string.
        assert str(uuid.UUID(rid)) == rid

    def test_generate_is_unique(self):
        assert generate_request_id() != generate_request_id()


class TestSanitize:
    def test_accepts_uuid(self):
        rid = generate_request_id()
        assert sanitize_request_id(rid) == rid

    def test_accepts_trace_like_ids(self):
        for good in ("abc123", "a.b_c-1", "0af7651916cd43dd8448eb211c80319c"):
            assert sanitize_request_id(good) == good

    def test_trims_whitespace(self):
        assert sanitize_request_id("  abc-123  ") == "abc-123"

    def test_rejects_none_and_empty(self):
        assert sanitize_request_id(None) is None
        assert sanitize_request_id("") is None
        assert sanitize_request_id("   ") is None

    def test_rejects_non_str(self):
        assert sanitize_request_id(12345) is None

    def test_rejects_injection_chars(self):
        # Newlines, ANSI, control, spaces, and exotic punctuation must be refused
        # so a forged header cannot inject into the log stream.
        for bad in (
            "abc\ndef",
            "abc\r\ndef",
            "abc\x1b[31m",
            "has space",
            "semi;colon",
            "quote\"x",
            "slash/x",
        ):
            assert sanitize_request_id(bad) is None

    def test_rejects_overlong(self):
        assert sanitize_request_id("a" * 129) is None
        assert sanitize_request_id("a" * 128) == "a" * 128  # boundary ok


class TestContextVar:
    def test_default_is_none(self):
        # Fresh-ish context: after a reset there is no id.
        token = set_request_id("temp")
        reset_request_id(token)
        assert get_request_id() is None

    def test_set_and_get(self):
        token = set_request_id("req-xyz")
        try:
            assert get_request_id() == "req-xyz"
        finally:
            reset_request_id(token)

    def test_reset_restores_previous(self):
        t1 = set_request_id("outer")
        t2 = set_request_id("inner")
        assert get_request_id() == "inner"
        reset_request_id(t2)
        assert get_request_id() == "outer"
        reset_request_id(t1)

    def test_reset_with_bad_token_does_not_raise(self):
        token = set_request_id("x")
        reset_request_id(token)
        # Reusing an already-used token must not raise (best-effort cleanup).
        reset_request_id(token)
