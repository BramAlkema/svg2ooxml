"""Shared lightweight math helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def finite_float(value: Any, default: float | None = None) -> float | None:
    """Return ``value`` as a finite float, otherwise ``default``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def coerce_float(value: Any, default: float) -> float:
    """Return ``value`` as a finite float, falling back to ``default``."""

    number = finite_float(value)
    return default if number is None else number


def coerce_positive_float(value: Any, default: float) -> float:
    """Return ``value`` as a positive finite float, otherwise ``default``."""

    number = finite_float(value)
    if number is not None and number > 0:
        return number
    return default


def coerce_int(value: Any, default: int | None = None) -> int | None:
    """Return ``value`` as an int, falling back on invalid or non-finite input."""

    try:
        number = int(value)
    except (OverflowError, TypeError, ValueError):
        return default
    return int(number)


def coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce common config tokens into a boolean with a controlled fallback."""

    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off"}:
            return False
        return default
    return bool(value)


def clamp01(value: float) -> float:
    """Clamp a scalar to the inclusive ``0.0``-``1.0`` range."""

    return max(0.0, min(1.0, value))


def population_variance(values: Sequence[float]) -> float:
    """Population variance of *values*, returning 0.0 for empty input."""
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return sum((v - m) ** 2 for v in values) / len(values)


__all__ = [
    "clamp01",
    "coerce_bool",
    "coerce_float",
    "coerce_int",
    "coerce_positive_float",
    "finite_float",
    "population_variance",
]
