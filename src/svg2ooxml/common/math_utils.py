"""Shared lightweight math helpers."""

from __future__ import annotations

from collections.abc import Sequence


def population_variance(values: Sequence[float]) -> float:
    """Population variance of *values*, returning 0.0 for empty input."""
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return sum((v - m) ** 2 for v in values) / len(values)
