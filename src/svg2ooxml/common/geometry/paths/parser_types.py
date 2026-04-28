"""Shared types and constants for SVG path parsing."""

from __future__ import annotations

Token = str | float
_MAX_CACHED_PATH_CHARS = 8192


class PathParseError(ValueError):
    """Raised when path data contains unsupported commands or malformed numbers."""


__all__ = ["PathParseError", "Token"]
