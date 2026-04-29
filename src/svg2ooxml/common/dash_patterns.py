"""Shared SVG dash pattern normalization helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from svg2ooxml.common.units import ConversionContext, UnitConverter
from svg2ooxml.common.units.lengths import (
    parse_number,
    parse_number_or_percent,
    resolve_length_px,
    split_length_list,
)

_UNIT_CONVERTER = UnitConverter()
_LENGTH_CONTEXT = _UNIT_CONVERTER.create_context(
    width=0.0,
    height=0.0,
    font_size=12.0,
    root_font_size=12.0,
)


def parse_dash_array(
    value: str | None,
    *,
    context: ConversionContext | None = _LENGTH_CONTEXT,
    axis: str = "font-size",
    unit_converter: UnitConverter | None = _UNIT_CONVERTER,
) -> list[float] | None:
    """Parse an SVG ``stroke-dasharray`` value into resolved dash lengths."""

    if not value:
        return None
    token = value.strip()
    if not token or token.lower() == "none":
        return None

    numbers: list[float] = []
    for part in split_length_list(token):
        length = parse_dash_length(
            part,
            context=context,
            axis=axis,
            unit_converter=unit_converter,
        )
        if length is None:
            return None
        numbers.append(length)
    return numbers or None


def parse_dash_length(
    value: str | None,
    *,
    context: ConversionContext | None = _LENGTH_CONTEXT,
    axis: str = "font-size",
    unit_converter: UnitConverter | None = _UNIT_CONVERTER,
) -> float | None:
    """Parse one SVG dash component, treating percentages as SVG percent units."""

    if value is None:
        return None
    token = value.strip()
    if not token:
        return None

    fraction = parse_number_or_percent(token, math.nan)
    if not math.isnan(fraction) and (
        token.endswith("%") or token.lower().startswith("calc(")
    ):
        return fraction * 100.0

    resolved = resolve_length_px(
        token,
        context,
        axis=axis,
        default=math.nan,
        unit_converter=unit_converter,
    )
    if math.isnan(resolved):
        return None
    return resolved


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
        value = abs(parse_number(raw_value, math.nan))
        if math.isnan(value):
            continue
        if math.isfinite(value) and value > 0:
            normalized.append(value)

    if len(normalized) % 2 == 1:
        normalized += normalized
    return normalized


__all__ = ["normalize_dash_array", "parse_dash_array", "parse_dash_length"]
