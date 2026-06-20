# -*- coding: utf-8 -*-
"""Progress-specific exceptions (F6)."""

from __future__ import annotations


class ProgressError(Exception):
    """Base exception for progress operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
