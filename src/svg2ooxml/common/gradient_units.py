"""Shared SVG gradient coordinate parsing helpers."""

from __future__ import annotations

from typing import Any

from svg2ooxml.common.math_utils import finite_float
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import (
    parse_number_or_percent,
    parse_percentage,
    resolve_length_px,
)

_UNIT_CONVERTER = UnitConverter()


def normalize_gradient_units(value: str | None) -> str:
    """Return the canonical SVG gradientUnits token."""

    token = (value or "").strip()
    if token.lower() == "userspaceonuse":
        return "userSpaceOnUse"
    return "objectBoundingBox"


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
    fallback = _finite_number(parse_number_or_percent(default, 0.0), 0.0)
    if normalize_gradient_units(units) != "userSpaceOnUse":
        return _finite_number(parse_number_or_percent(token, fallback), fallback)

    if context is None:
        percent_value = _parse_simple_percent(token)
        if percent_value is not None:
            return percent_value

    converter = unit_converter or _UNIT_CONVERTER
    return _finite_number(
        resolve_length_px(
            token,
            context,
            axis=axis,
            default=fallback,
            unit_converter=converter,
        ),
        fallback,
    )


def parse_gradient_offset(value: str | None) -> float:
    """Parse and clamp an SVG gradient stop offset."""

    offset = _finite_number(parse_number_or_percent(value, 0.0), 0.0)
    return max(0.0, min(1.0, offset))


def _parse_simple_percent(value: str) -> float | None:
    percent = parse_percentage(value, float("nan"))
    if percent != percent:
        return None
    return percent


def _finite_number(value: object, default: float) -> float:
    number = finite_float(value)
    return default if number is None else number
