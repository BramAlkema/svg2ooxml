"""Shared SVG dash pattern normalization helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


def normalize_dash_array(values: Iterable[Any] | None) -> list[float]:
    """Return positive finite dash intervals, doubled when SVG requires it.

    SVG repeats odd-length dash arrays to form dash/gap pairs. Invalid,
    non-finite, and zero-length entries are ignored here so renderers do not
    serialize malformed DrawingML or pass invalid intervals to raster backends.
    """

    if values is None:
        return []

    normalized: list[float] = []
    for raw_value in values:
        try:
            value = abs(float(raw_value))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            normalized.append(value)

    if len(normalized) % 2 == 1:
        normalized += normalized
    return normalized


__all__ = ["normalize_dash_array"]
