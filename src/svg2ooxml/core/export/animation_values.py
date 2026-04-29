"""Shared parsing helpers for export-time animation values."""

from __future__ import annotations

import math
from typing import Any

from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.ir.animation import AnimationDefinition


def animation_axis(attribute: str) -> str:
    """Return the length axis used by a positional animation attribute."""

    return "y" if attribute in {"y", "cy", "ppt_y", "y1", "y2"} else "x"


def parse_animation_length_px(
    value: Any,
    *,
    axis: str,
    default: float = math.nan,
) -> float:
    return resolve_length_px(value, None, axis=axis, default=default)


def animation_length_delta_px(
    animation: AnimationDefinition,
    *,
    axis: str | None = None,
) -> float | None:
    axis = axis or animation_axis(animation.target_attribute)
    start, end = animation_length_bounds_px(animation, axis=axis)
    if start is None or end is None:
        return None
    return end - start


def animation_length_bounds_px(
    animation: AnimationDefinition,
    *,
    axis: str | None = None,
) -> tuple[float, float] | tuple[None, None]:
    axis = axis or animation_axis(animation.target_attribute)
    start = parse_animation_length_px(animation.values[0], axis=axis)
    end = parse_animation_length_px(animation.values[-1], axis=axis)
    if not math.isfinite(start) or not math.isfinite(end):
        return (None, None)
    return (start, end)


def animation_length_bounds_or_default(
    animation: AnimationDefinition | None,
    *,
    axis: str,
    default: float,
) -> tuple[float, float]:
    if animation is None:
        return (default, default)
    start, end = animation_length_bounds_px(animation, axis=axis)
    if start is None or end is None:
        return (default, default)
    return (start, end)


__all__ = [
    "animation_axis",
    "animation_length_bounds_or_default",
    "animation_length_bounds_px",
    "animation_length_delta_px",
    "parse_animation_length_px",
]
