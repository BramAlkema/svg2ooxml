"""Shared SVG gradient coordinate parsing helpers."""

from __future__ import annotations

from typing import Any

from svg2ooxml.common.units import UnitConverter

_UNIT_CONVERTER = UnitConverter()


def normalize_gradient_units(value: str | None) -> str:
    """Return the canonical SVG gradientUnits token."""

    token = (value or "").strip()
    if token.lower() == "userspaceonuse":
        return "userSpaceOnUse"
    return "objectBoundingBox"


def parse_number_or_percent(value: str | None, default: float = 0.0) -> float:
    """Parse a bare SVG number or percent fraction."""

    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        if token.endswith("%"):
            return float(token[:-1]) / 100.0
        return float(token)
    except ValueError:
        return default


def parse_gradient_coordinate(
    value: str | None,
    *,
    units: str | None,
    axis: str,
    default: str,
    context: Any | None = None,
    unit_converter: Any | None = None,
) -> float:
    """Resolve an SVG gradient coordinate in final gradientUnits context.

    ``objectBoundingBox`` coordinates are fractions. ``userSpaceOnUse``
    coordinates are SVG lengths, so absolute units resolve to px and
    percentages use the supplied viewport context when one is available.
    """

    token = value if value is not None and value.strip() else default
    fallback = parse_number_or_percent(default, 0.0)
    if normalize_gradient_units(units) != "userSpaceOnUse":
        return parse_number_or_percent(token, fallback)

    converter = unit_converter or _UNIT_CONVERTER
    try:
        return float(converter.to_px(token, context, axis=axis))
    except (AttributeError, TypeError, ValueError):
        return parse_number_or_percent(token, fallback)


def parse_gradient_offset(value: str | None) -> float:
    """Parse and clamp an SVG gradient stop offset."""

    offset = parse_number_or_percent(value, 0.0)
    return max(0.0, min(1.0, offset))
