"""Parse common SVG color representations."""

from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping, MutableMapping

from svg2ooxml.color import Color
from svg2ooxml.color import parse_color as _parse_global_color

_REGISTERED_COLORS: MutableMapping[str, Color] = {}


def parse_color(
    value: str,
    *,
    current_color: tuple[float, float, float, float] | None = None,
    palette: Mapping[str, tuple[float, float, float, float] | str] | None = None,
) -> tuple[float, float, float, float] | None:
    """Parser façade that keeps the legacy tuple-based return type."""

    palette_map: Mapping[str, Color | str] | None = None
    if palette:
        palette_map = {key.lower(): _coerce_palette_value(val) for key, val in palette.items()}

    combined_palette = None
    if palette_map and _REGISTERED_COLORS:
        combined_palette = ChainMap(palette_map, _REGISTERED_COLORS)
    elif palette_map:
        combined_palette = palette_map
    elif _REGISTERED_COLORS:
        combined_palette = _REGISTERED_COLORS

    color = _parse_global_color(
        value,
        current_color=_tuple_to_color(current_color),
        palette=combined_palette,
    )
    if color is None:
        return None
    clamped = color.clamp()
    return (clamped.r, clamped.g, clamped.b, clamped.a)


def register_palette(colors: Mapping[str, tuple[float, float, float, float] | str]) -> None:
    for name, value in colors.items():
        parsed = _coerce_palette_value(value)
        if isinstance(parsed, Color):
            _REGISTERED_COLORS[name.lower()] = parsed.clamp()
        else:
            fallback = _parse_global_color(parsed)
            if fallback is not None:
                _REGISTERED_COLORS[name.lower()] = fallback.clamp()


def _tuple_to_color(value: tuple[float, float, float, float] | None) -> Color | None:
    if value is None:
        return None
    return Color(*value).clamp()


def _coerce_palette_value(value: tuple[float, float, float, float] | str) -> Color | str:
    if isinstance(value, tuple):
        if len(value) == 3:
            return Color(value[0], value[1], value[2], 1.0)
        if len(value) == 4:
            return Color(*value)
        raise ValueError("palette tuples must be RGB or RGBA")
    return value


__all__ = ["parse_color", "register_palette"]
