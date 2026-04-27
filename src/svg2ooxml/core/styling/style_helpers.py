"""Pure helper functions extracted from style_extractor."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from svg2ooxml.color.parsers import parse_color
from svg2ooxml.common.conversions.colors import color_to_hex
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.gradient_units import parse_gradient_offset
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import reference_id
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import (
    parse_number_or_percent,
    resolve_length_px,
    split_length_list,
)
from svg2ooxml.ir.numpy_compat import NUMPY_AVAILABLE, np

_UNIT_CONVERTER = UnitConverter()
_LENGTH_CONTEXT = _UNIT_CONVERTER.create_context(
    width=0.0,
    height=0.0,
    font_size=12.0,
    root_font_size=12.0,
)


def extract_url_id(token: str) -> str | None:
    if not token.startswith("url("):
        return None
    return reference_id(token)


def normalize_hex(token: str) -> str | None:
    value = token.lstrip("#").strip()
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.upper()


def parse_dash_array(value: str | None) -> list[float] | None:
    if not value:
        return None
    token = value.strip()
    if not token or token.lower() == "none":
        return None
    numbers: list[float] = []
    for part in split_length_list(token):
        length = parse_length(part)
        if length is None:
            return None
        numbers.append(length)
    return numbers or None


def parse_length(value: str | None) -> float | None:
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    if token.endswith("%"):
        return parse_number_or_percent(token, 0.0) * 100.0
    resolved = resolve_length_px(
        token,
        _LENGTH_CONTEXT,
        axis="font-size",
        default=float("nan"),
        unit_converter=_UNIT_CONVERTER,
    )
    if resolved != resolved:
        return None
    return resolved


def parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_style_attr(style: str | None) -> dict[str, str]:
    return parse_style_declarations(style)[0]


def parse_percentage(value: str) -> float:
    return parse_number_or_percent(value, 0.0)


def matrix_tuple_is_identity(transform: Any) -> bool:
    if not isinstance(transform, (tuple, list)) or len(transform) != 6:
        return False
    identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    try:
        return all(abs(float(value) - identity[idx]) < 1e-9 for idx, value in enumerate(transform))
    except (TypeError, ValueError):
        return False


def apply_matrix_to_point(matrix: Matrix2D, point: tuple[float, float]) -> tuple[float, float]:
    applied = matrix.transform_points([point])
    if applied:
        p = applied[0]
        return (p.x, p.y)
    return point


def matrix2d_to_numpy(matrix: Matrix2D | None):
    if matrix is None or not NUMPY_AVAILABLE:
        return None
    return np.array([
        [matrix.a, matrix.c, matrix.e],
        [matrix.b, matrix.d, matrix.f],
        [0.0, 0.0, 1.0],
    ])


def descriptor_stop_colors(descriptor) -> list[str]:
    stops = getattr(descriptor, "stops", ())
    colors: set[str] = set()
    for stop in stops:
        color_value = getattr(stop, "color", "")
        if not isinstance(color_value, str):
            continue
        token = color_value.lstrip("#").upper()
        if token:
            colors.add(token)
    return sorted(colors)


def apply_stroke_opacity(paint, opacity: float):
    from svg2ooxml.ir.paint import (
        LinearGradientPaint,
        RadialGradientPaint,
        SolidPaint,
    )

    opacity = max(0.0, min(1.0, opacity))
    if isinstance(paint, SolidPaint):
        return replace(paint, opacity=max(0.0, min(1.0, paint.opacity * opacity)))
    if isinstance(paint, LinearGradientPaint):
        if opacity >= 0.999:
            return paint
        scaled_stops = [
            replace(stop, opacity=max(0.0, min(1.0, stop.opacity * opacity)))
            for stop in paint.stops
        ]
        return replace(paint, stops=scaled_stops)
    if isinstance(paint, RadialGradientPaint):
        if opacity >= 0.999:
            return paint
        scaled_stops = [
            replace(stop, opacity=max(0.0, min(1.0, stop.opacity * opacity)))
            for stop in paint.stops
        ]
        return replace(paint, stops=scaled_stops)
    return paint


def clean_color(value: str | None, fallback: str | None = None) -> str | None:
    if not value:
        return fallback
    normalized = normalize_hex(value)
    if normalized is None:
        return fallback
    return normalized


def parse_offset(value: str) -> float:
    return parse_gradient_offset(value)


def parse_stop_color(stop_element, style_parser=None) -> tuple[str, float]:
    style_attrs = parse_style_attr(stop_element.get("style")) if style_parser is None else style_parser(stop_element.get("style"))
    color = stop_element.get("stop-color") or style_attrs.get("stop-color") or "#000000"
    parsed_color = parse_color(color)
    color = color_to_hex(color, default="000000")
    opacity_str = stop_element.get("stop-opacity") or style_attrs.get("stop-opacity")
    color_alpha = float(getattr(parsed_color, "a", 1.0)) if parsed_color is not None else 1.0
    opacity = color_alpha * parse_opacity(opacity_str, default=1.0)
    return color, opacity
