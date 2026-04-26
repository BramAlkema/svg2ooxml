"""Paint/gradient normalisation scaffolding."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from svg2ooxml.color.parsers import parse_color
from svg2ooxml.common.conversions.opacity import parse_opacity


@dataclass(slots=True)
class SolidPaint:
    color: tuple[float, float, float]
    opacity: float = 1.0


@dataclass(slots=True)
class GradientStop:
    offset: float
    color: tuple[float, float, float]
    opacity: float = 1.0


@dataclass(slots=True)
class LinearGradient:
    stops: Sequence[GradientStop]
    start: tuple[float, float]
    end: tuple[float, float]
    transform: np.ndarray


@dataclass(slots=True)
class RadialGradient:
    stops: Sequence[GradientStop]
    center: tuple[float, float]
    radius: float
    focal_point: tuple[float, float] | None
    transform: np.ndarray


@dataclass(slots=True)
class PatternPaint:
    pattern_id: str
    transform: np.ndarray


@dataclass(slots=True)
class StrokePaint:
    paint: SolidPaint | LinearGradient | RadialGradient | PatternPaint | None
    width: float | None
    opacity: float = 1.0
    line_cap: str | None = None
    line_join: str | None = None
    miter_limit: float | None = None


def compute_paints(
    style: Mapping[str, str],
    element,
    definitions: Mapping[str, object],
) -> tuple[object | None, StrokePaint | None]:
    """Compute fill/stroke paints from style, including gradient/pattern references."""

    opacity = _parse_opacity(style.get("opacity"), default=1.0)
    current_color = _parse_color(style.get("color"), 1.0, current_color=None)

    fill_value = style.get("fill")
    fill_opacity = _parse_opacity(style.get("fill-opacity"), default=1.0) * opacity
    fill_paint = _resolve_paint(fill_value, fill_opacity, definitions, element, current_color)

    stroke_value = style.get("stroke")
    stroke_opacity = _parse_opacity(style.get("stroke-opacity"), default=1.0) * opacity
    stroke_width = _parse_length(style.get("stroke-width"))
    stroke_paint_value = _resolve_paint(stroke_value, stroke_opacity, definitions, element, current_color)
    if stroke_paint_value is None and stroke_width is None:
        stroke_paint = None
    else:
        stroke_paint = StrokePaint(
            paint=stroke_paint_value,
            width=stroke_width,
            opacity=stroke_opacity,
            line_cap=style.get("stroke-linecap"),
            line_join=style.get("stroke-linejoin"),
            miter_limit=_parse_length(style.get("stroke-miterlimit")),
        )

    return fill_paint, stroke_paint


def _parse_opacity(value: str | None, *, default: float) -> float:
    return parse_opacity(value, default=default)


def _parse_length(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_paint(
    value: str | None,
    opacity: float,
    definitions: Mapping[str, object],
    element,
    current_color: object | None,
) -> object | None:
    if value is None:
        return None
    value = value.strip()
    lowered = value.lower()
    if not value or lowered in {"none", "transparent"}:
        return None
    if lowered.startswith("url("):
        ref = _extract_url(value)
        if not ref:
            return None
        definition = definitions.get(ref)
        if definition is None:
            return None
        source = getattr(definition, "source", None)
        if source is None:
            return None
        if definition.tag == "linearGradient":
            return _apply_opacity_to_paint(_parse_linear_gradient(source, definitions), opacity)
        if definition.tag == "radialGradient":
            return _apply_opacity_to_paint(_parse_radial_gradient(source, definitions), opacity)
        if definition.tag == "pattern":
            return _parse_pattern(source)
        return None
    color = _parse_color(value, opacity, current_color=current_color)
    if color is not None:
        return SolidPaint(color=(color.r, color.g, color.b), opacity=color.a)
    return None


def _parse_color(value: str | None, opacity: float, *, current_color: object | None):
    parsed = parse_color(value, current_color=current_color)
    if parsed is None:
        return None
    return parsed.with_alpha(_clamp_opacity(parsed.a * opacity))


def _clamp_opacity(value: float) -> float:
    return max(0.0, min(1.0, value))


def _extract_url(token: str) -> str | None:
    token = token.strip()
    if token.startswith("url(") and token.endswith(")"):
        inner = token[4:-1].strip().strip("\"'")
    else:
        inner = token
    if inner.startswith("#"):
        return inner[1:]
    return inner or None


def _parse_linear_gradient(element, definitions) -> LinearGradient | None:
    transform = _matrix_to_np(element.get("gradientTransform"))
    units = (element.get("gradientUnits") or "objectBoundingBox").lower()
    x1 = _parse_coordinate(element.get("x1"), fallback=0.0)
    y1 = _parse_coordinate(element.get("y1"), fallback=0.0)
    x2 = _parse_coordinate(element.get("x2"), fallback=1.0 if units == "objectboundingbox" else 0.0)
    y2 = _parse_coordinate(element.get("y2"), fallback=0.0)
    stops = _parse_gradient_stops(element, definitions)
    if not stops:
        return None
    return LinearGradient(
        stops=tuple(stops),
        start=(x1, y1),
        end=(x2, y2),
        transform=transform,
    )


def _parse_radial_gradient(element, definitions) -> RadialGradient | None:
    transform = _matrix_to_np(element.get("gradientTransform"))
    units = (element.get("gradientUnits") or "objectBoundingBox").lower()
    cx = _parse_coordinate(element.get("cx"), fallback=0.5 if units == "objectboundingbox" else 0.0)
    cy = _parse_coordinate(element.get("cy"), fallback=0.5 if units == "objectboundingbox" else 0.0)
    r = _parse_coordinate(element.get("r"), fallback=0.5 if units == "objectboundingbox" else 0.0)
    fx = _parse_coordinate(element.get("fx"), fallback=cx)
    fy = _parse_coordinate(element.get("fy"), fallback=cy)
    stops = _parse_gradient_stops(element, definitions)
    if not stops or r <= 0:
        return None
    return RadialGradient(
        stops=tuple(stops),
        center=(cx, cy),
        radius=r,
        focal_point=(fx, fy),
        transform=transform,
    )


def _parse_gradient_stops(element, definitions) -> list[GradientStop]:
    stops: list[GradientStop] = []
    href = element.get("{http://www.w3.org/1999/xlink}href") or element.get("href")
    if href:
        ref = _extract_url(href)
        if ref and ref in definitions:
            stops.extend(_parse_gradient_stops(definitions[ref].source, definitions))
    for child in element:
        if _local_name(child.tag) != "stop":
            continue
        offset = _parse_coordinate(child.get("offset"), fallback=0.0)
        stop_style = {}
        for attr in ("stop-color", "stop-opacity"):
            if attr in child.attrib:
                stop_style[attr] = child.attrib[attr]
        stop_style.update(_parse_style_attribute(child.get("style") or ""))
        color_value = stop_style.get("stop-color")
        opacity = _parse_opacity(stop_style.get("stop-opacity"), default=1.0)
        paint = _resolve_paint(color_value, opacity, {}, child, None)
        if isinstance(paint, SolidPaint):
            stops.append(
                GradientStop(
                    offset=max(0.0, min(1.0, offset)),
                    color=paint.color,
                    opacity=paint.opacity,
                )
            )
    return stops


def _apply_opacity_to_paint(paint: object | None, opacity: float) -> object | None:
    if isinstance(paint, LinearGradient):
        return LinearGradient(
            stops=tuple(
                GradientStop(
                    offset=stop.offset,
                    color=stop.color,
                    opacity=_clamp_opacity(stop.opacity * opacity),
                )
                for stop in paint.stops
            ),
            start=paint.start,
            end=paint.end,
            transform=paint.transform,
        )
    if isinstance(paint, RadialGradient):
        return RadialGradient(
            stops=tuple(
                GradientStop(
                    offset=stop.offset,
                    color=stop.color,
                    opacity=_clamp_opacity(stop.opacity * opacity),
                )
                for stop in paint.stops
            ),
            center=paint.center,
            radius=paint.radius,
            focal_point=paint.focal_point,
            transform=paint.transform,
        )
    return paint


def _parse_pattern(element) -> PatternPaint | None:
    transform = _matrix_to_np(element.get("patternTransform"))
    pattern_id = element.get("id") or ""
    return PatternPaint(pattern_id=pattern_id, transform=transform)


def _matrix_to_np(transform_attr: str | None) -> np.ndarray:
    from svg2ooxml.common.geometry import parse_transform_list

    matrix = parse_transform_list(transform_attr)
    return np.array(
        [
            [matrix.a, matrix.c, matrix.e],
            [matrix.b, matrix.d, matrix.f],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _parse_coordinate(value: str | None, *, fallback: float) -> float:
    if value is None:
        return fallback
    value = value.strip()
    if value.endswith("%"):
        try:
            return float(value[:-1]) / 100.0
        except ValueError:
            return fallback
    try:
        return float(value)
    except ValueError:
        return fallback


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_style_attribute(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in style.split(";"):
        if not chunk.strip() or ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        result[name.strip()] = value.strip()
    return result


__all__ = [
    "SolidPaint",
    "GradientStop",
    "LinearGradient",
    "RadialGradient",
    "PatternPaint",
    "StrokePaint",
    "compute_paints",
]
