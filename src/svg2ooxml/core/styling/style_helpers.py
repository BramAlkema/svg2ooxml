"""Pure helper functions extracted from style_extractor."""

from __future__ import annotations

from typing import Any

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.ir.numpy_compat import NUMPY_AVAILABLE, np


def extract_url_id(token: str) -> str | None:
    if not token.startswith("url("):
        return None
    inner = token[4:-1].strip().strip('"\'')
    if inner.startswith("#"):
        return inner[1:]
    return inner or None


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
    parts = token.replace(",", " ").split()
    numbers: list[float] = []
    for part in parts:
        try:
            numbers.append(float(part))
        except ValueError:
            continue
    return numbers or None


def parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_style_attr(style: str | None) -> dict[str, str]:
    if not style:
        return {}
    declarations = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        declarations[name.strip()] = value.strip()
    return declarations


def parse_percentage(value: str) -> float:
    token = value.strip()
    if token.endswith("%"):
        try:
            return float(token[:-1]) / 100.0
        except ValueError:
            return 0.0
    try:
        return float(token)
    except ValueError:
        return 0.0


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


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def apply_stroke_opacity(paint, opacity: float):
    from svg2ooxml.ir.paint import (
        GradientStop,
        LinearGradientPaint,
        RadialGradientPaint,
        SolidPaint,
    )

    opacity = max(0.0, min(1.0, opacity))
    if isinstance(paint, SolidPaint):
        return SolidPaint(rgb=paint.rgb, opacity=max(0.0, min(1.0, paint.opacity * opacity)))
    if isinstance(paint, LinearGradientPaint):
        if opacity >= 0.999:
            return paint
        scaled_stops = [
            GradientStop(stop.offset, stop.rgb, max(0.0, min(1.0, stop.opacity * opacity)))
            for stop in paint.stops
        ]
        return LinearGradientPaint(
            stops=scaled_stops,
            start=paint.start,
            end=paint.end,
            transform=paint.transform,
            gradient_id=paint.gradient_id,
        )
    if isinstance(paint, RadialGradientPaint):
        if opacity >= 0.999:
            return paint
        scaled_stops = [
            GradientStop(stop.offset, stop.rgb, max(0.0, min(1.0, stop.opacity * opacity)))
            for stop in paint.stops
        ]
        return RadialGradientPaint(
            stops=scaled_stops,
            center=paint.center,
            radius=paint.radius,
            focal_point=paint.focal_point,
            transform=paint.transform,
            gradient_id=paint.gradient_id,
        )
    return paint


def clean_color(value: str | None, fallback: str | None = None) -> str | None:
    if not value:
        return fallback
    normalized = normalize_hex(value)
    if normalized is None:
        return fallback
    return normalized


def parse_offset(value: str) -> float:
    token = value.strip()
    if token.endswith("%"):
        try:
            return max(0.0, min(1.0, float(token[:-1]) / 100.0))
        except ValueError:
            return 0.0
    try:
        return max(0.0, min(1.0, float(token)))
    except ValueError:
        return 0.0


def parse_stop_color(stop_element, style_parser=None) -> tuple[str, float]:
    style_attrs = parse_style_attr(stop_element.get("style")) if style_parser is None else style_parser(stop_element.get("style"))
    color = stop_element.get("stop-color") or style_attrs.get("stop-color") or "#000000"
    color = normalize_hex(color) or "000000"
    opacity_str = stop_element.get("stop-opacity") or style_attrs.get("stop-opacity")
    try:
        opacity = float(opacity_str) if opacity_str is not None else 1.0
    except ValueError:
        opacity = 1.0
    opacity = max(0.0, min(1.0, opacity))
    return color, opacity
