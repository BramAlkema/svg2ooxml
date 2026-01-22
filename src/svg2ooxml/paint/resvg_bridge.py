"""Bridge helpers between resvg paint styles and the svg2ooxml IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from svg2ooxml.core.parser.colors import parse_color as parse_svg_color
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop as ResvgGradientStop,
    LinearGradient,
    PatternPaint as ResvgPatternPaint,
    RadialGradient,
)
from svg2ooxml.core.resvg.painting.paint import (
    Color,
    FillStyle,
    PaintReference,
    StrokeStyle,
)
from svg2ooxml.core.resvg.usvg_tree import BaseNode, Tree
from svg2ooxml.ir.numpy_compat import np
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    Paint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)


@dataclass(slots=True)
class NormalizedPaints:
    """Resolved fill and stroke paints for a usvg tree node."""

    fill: Paint
    stroke: Stroke | None


def resolve_paints_for_node(node: BaseNode, tree: Tree) -> NormalizedPaints:
    """Return svg2ooxml IR paint objects for the given node."""

    fill_paint = resolve_fill_paint(node.fill, tree)
    stroke_result = resolve_stroke_style(node.stroke, tree)

    presentation = getattr(node, "presentation", None)

    if fill_paint is None and presentation is not None and presentation.fill:
        fallback_fill = _solid_paint_from_presentation(
            presentation.fill,
            fill_opacity=presentation.fill_opacity,
            element_opacity=presentation.opacity,
        )
        if fallback_fill is not None:
            fill_paint = fallback_fill

    needs_stroke_fallback = (
        (stroke_result is None)
        or (stroke_result.paint is None)
    )
    if needs_stroke_fallback and presentation is not None and presentation.stroke:
        fallback_stroke_paint = _solid_paint_from_presentation(
            presentation.stroke,
            fill_opacity=presentation.stroke_opacity,
            element_opacity=presentation.opacity,
        )
        if fallback_stroke_paint is not None:
            stroke_style = getattr(node, "stroke", None)
            width = 0.0
            opacity = 1.0
            if stroke_style is not None and stroke_style.width is not None:
                width = stroke_style.width
                opacity = stroke_style.opacity
            else:
                if presentation.stroke_width is not None:
                    width = presentation.stroke_width
                if presentation.stroke_opacity is not None:
                    opacity = presentation.stroke_opacity
                if presentation.opacity is not None:
                    opacity *= presentation.opacity
            stroke_result = Stroke(
                paint=fallback_stroke_paint,
                width=width,
                join=StrokeJoin.MITER,
                cap=StrokeCap.BUTT,
                miter_limit=4.0,
                dash_array=None,
                dash_offset=0.0,
                opacity=_clamp01(opacity),
            )
    return NormalizedPaints(fill=fill_paint, stroke=stroke_result)


def resolve_fill_paint(fill: FillStyle | None, tree: Tree) -> Paint:
    """Convert a resvg FillStyle into an svg2ooxml Paint object."""

    if fill is None:
        return None
    if fill.color is not None:
        return _color_to_solid(fill.color, _clamp01(fill.opacity))
    if fill.reference is not None:
        return _resolve_paint_reference(fill.reference, tree)
    return None


def resolve_stroke_style(stroke: StrokeStyle | None, tree: Tree) -> Stroke | None:
    """Convert a resvg StrokeStyle into an svg2ooxml Stroke."""

    if stroke is None:
        return None

    paint: Paint
    if stroke.color is not None:
        paint = _color_to_solid(stroke.color, _clamp01(_coerce_float(getattr(stroke, "opacity", 1.0), 1.0)))
    elif stroke.reference is not None:
        paint = _resolve_paint_reference(stroke.reference, tree)
    else:
        paint = None

    width = _coerce_float(getattr(stroke, "width", None), 0.0)



    if paint is None and width <= 0.0:
        return None

    result = Stroke(
        paint=paint,
        width=width,
        join=StrokeJoin.MITER,
        cap=StrokeCap.BUTT,
        miter_limit=4.0,
        dash_array=None,
        dash_offset=0.0,
        opacity=_clamp01(_coerce_float(getattr(stroke, "opacity", 1.0), 1.0)),
    )



    return result


def _resolve_paint_reference(reference: PaintReference, tree: Tree) -> Paint:
    server = tree.resolve_paint(reference)
    if server is None:
        return None
    server_id = reference.href.lstrip("#")

    if isinstance(server, LinearGradient):
        return _convert_linear_gradient(server_id, server)
    if isinstance(server, RadialGradient):
        return _convert_radial_gradient(server_id, server)
    if isinstance(server, ResvgPatternPaint):
        return _convert_pattern(server_id, server)

    return None


def _convert_linear_gradient(definition_id: str, gradient: LinearGradient) -> LinearGradientPaint:
    stops = _convert_stops(gradient.stops)
    transform = _matrix_to_array(gradient.transform)
    return LinearGradientPaint(
        stops=stops,
        start=(gradient.x1, gradient.y1),
        end=(gradient.x2, gradient.y2),
        transform=transform,
        gradient_id=definition_id,
    )


def _convert_radial_gradient(definition_id: str, gradient: RadialGradient) -> RadialGradientPaint:
    stops = _convert_stops(gradient.stops)
    transform = _matrix_to_array(gradient.transform)
    focal = (gradient.fx, gradient.fy) if (gradient.fx, gradient.fy) != (gradient.cx, gradient.cy) else None
    return RadialGradientPaint(
        stops=stops,
        center=(gradient.cx, gradient.cy),
        radius=gradient.r,
        focal_point=focal,
        transform=transform,
        gradient_id=definition_id,
    )


def _convert_pattern(definition_id: str, pattern: ResvgPatternPaint) -> PatternPaint:
    transform = _matrix_to_array(pattern.transform)
    return PatternPaint(
        pattern_id=definition_id,
        transform=transform,
        preset=None,
        foreground=None,
        background=None,
    )


def _convert_stops(stops: Iterable[ResvgGradientStop]) -> list[GradientStop]:
    parsed = [
        GradientStop(
            offset=stop.offset,
            rgb=_color_to_hex(stop.color),
            opacity=stop.color.a,
        )
        for stop in stops
    ]
    if len(parsed) == 1:
        first = parsed[0]
        return [
            GradientStop(offset=0.0, rgb=first.rgb, opacity=first.opacity),
            GradientStop(offset=1.0, rgb=first.rgb, opacity=first.opacity),
        ]
    return parsed


def _color_to_solid(color: Color, opacity: float | None) -> SolidPaint | None:
    hex_value = _color_to_hex(color)
    if hex_value is None:
        return None
    alpha = _coerce_float(getattr(color, "a", None), 1.0)
    effective_opacity = alpha if opacity is None else opacity
    return SolidPaint(rgb=hex_value, opacity=_coerce_float(effective_opacity, 1.0))


def _matrix_to_array(matrix: ResvgMatrix | None):
    if matrix is None:
        return None
    return np.array([
        [matrix.a, matrix.c, matrix.e],
        [matrix.b, matrix.d, matrix.f],
        [0.0, 0.0, 1.0],
    ])


def _color_to_hex(color: Color) -> str | None:
    try:
        r = float(getattr(color, "r"))
        g = float(getattr(color, "g"))
        b = float(getattr(color, "b"))
    except (TypeError, ValueError, AttributeError):
        return None
    try:
        return f"{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
    except (TypeError, ValueError):
        return None


def _coerce_float(value: float | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _solid_paint_from_presentation(
    value: str,
    *,
    fill_opacity: float | None,
    element_opacity: float | None,
) -> SolidPaint | None:
    rgba = parse_svg_color(value)
    if rgba is None:
        return None

    r, g, b, a = rgba
    effective_opacity = _coerce_float(a, 1.0)
    if fill_opacity is not None:
        effective_opacity *= _coerce_float(fill_opacity, 1.0)
    if element_opacity is not None:
        effective_opacity *= _coerce_float(element_opacity, 1.0)
    effective_opacity = _clamp01(effective_opacity)
    return SolidPaint(
        rgb=_tuple_to_hex(r, g, b),
        opacity=effective_opacity,
    )


def _tuple_to_hex(r: float, g: float, b: float) -> str:
    return f"{_float_channel_to_hex(r)}{_float_channel_to_hex(g)}{_float_channel_to_hex(b)}"


def _float_channel_to_hex(value: float) -> str:
    clamped = _clamp01(value)
    return f"{int(round(clamped * 255)):02X}"


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


__all__ = [
    "NormalizedPaints",
    "resolve_paints_for_node",
    "resolve_fill_paint",
    "resolve_stroke_style",
]
