"""Shared constants for converter helpers."""

from __future__ import annotations

from typing import Final

# Tolerance used for floating point comparisons across converter helpers.
DEFAULT_TOLERANCE: Final = 1e-6

__all__ = ["DEFAULT_TOLERANCE"]
