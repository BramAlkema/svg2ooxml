"""Time parsing utilities shared across animation and scheduling modules."""

from __future__ import annotations

Numeric = int | float


def parse_time_value(time_str: str | None) -> float:
    """Convert SMIL/CSS time strings into seconds."""
    if not time_str:
        return 0.0

    candidate = time_str.strip().lower()
    if not candidate:
        return 0.0

    if candidate.endswith("ms"):
        return float(candidate[:-2]) / 1000.0
    if candidate.endswith("s"):
        return float(candidate[:-1])
    if candidate.endswith("min"):
        return float(candidate[:-3]) * 60.0
    if candidate.endswith("h"):
        return float(candidate[:-1]) * 3600.0

    try:
        return float(candidate)
    except ValueError:
        return 0.0


__all__ = ["parse_time_value"]
