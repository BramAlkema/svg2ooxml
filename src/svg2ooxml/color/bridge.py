"""Bridging helpers between the lightweight colour model and the advanced engine."""

from __future__ import annotations

from typing import Sequence, Union

from .models import Color
from .advanced.engine import (
    AdvancedColor,
    COLOR_ENGINE_AVAILABLE as ADVANCED_COLOR_ENGINE_AVAILABLE,
    require_color_engine as _require_advanced_color_engine,
)

BasicColorInput = Union[Color, str, Sequence[float], Sequence[int], AdvancedColor]


def ensure_advanced_color_engine() -> None:
    """Raise a useful error when the optional colour stack is unavailable."""

    if not ADVANCED_COLOR_ENGINE_AVAILABLE:
        _require_advanced_color_engine()


def to_advanced_color(value: BasicColorInput) -> AdvancedColor:
    """Promote an input value to the fluent ``AdvancedColor`` representation."""

    ensure_advanced_color_engine()

    if isinstance(value, AdvancedColor):
        return value

    if isinstance(value, Color):
        rgb = tuple(int(round(component * 255)) for component in (value.r, value.g, value.b))
        advanced = AdvancedColor(rgb)
        if value.a != 1.0:
            advanced = advanced.alpha(value.a)
        return advanced

    if isinstance(value, str):
        return AdvancedColor(value)

    seq = tuple(value)
    if len(seq) not in (3, 4):
        raise ValueError("Colour sequences must contain 3 or 4 components.")

    first = seq[0]
    if isinstance(first, float):
        rgb = tuple(int(round(float(component) * 255)) for component in seq[:3])
        alpha_value = float(seq[3]) if len(seq) == 4 else None
    else:
        rgb = tuple(int(component) for component in seq[:3])
        alpha_value = None
        if len(seq) == 4:
            raw_alpha = seq[3]
            if isinstance(raw_alpha, int) and raw_alpha > 1:
                alpha_value = float(raw_alpha) / 255.0
            else:
                alpha_value = float(raw_alpha)

    advanced = AdvancedColor(rgb)
    if alpha_value is not None:
        advanced = advanced.alpha(alpha_value)
    return advanced


def from_advanced_color(color: AdvancedColor) -> Color:
    """Convert an ``AdvancedColor`` back to the lightweight dataclass."""

    ensure_advanced_color_engine()
    r, g, b, a = color.rgba()
    return Color(r / 255.0, g / 255.0, b / 255.0, a)


__all__ = [
    "ADVANCED_COLOR_ENGINE_AVAILABLE",
    "BasicColorInput",
    "ensure_advanced_color_engine",
    "to_advanced_color",
    "from_advanced_color",
]
