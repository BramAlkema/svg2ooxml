"""Huey application configuration (optional dependency).

This mirrors svg2pptx's SQLite-backed Huey setup while keeping Huey optional so
core parser usage does not require the package.
"""

from __future__ import annotations

try:
    from huey import MemoryHuey  # type: ignore
except Exception:  # pragma: no cover - huey is optional
    MemoryHuey = None  # type: ignore


def _create_huey() -> object | None:
    if MemoryHuey is None:
        return None
    options = {
        "immediate": os.getenv("SVG2OOXML_HUEY_IMMEDIATE", "false").lower() == "true",
        "utc": True,
    }
    return MemoryHuey(
        name="svg2ooxml",
        **options,
    )


huey = _create_huey()

__all__ = ["huey"]
