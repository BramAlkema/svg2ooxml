"""Compatibility helpers for third-party libraries."""

from __future__ import annotations

from .fonttools import ensure_fonttools_harfbuzz_patch

__all__ = ["ensure_fonttools_harfbuzz_patch"]
