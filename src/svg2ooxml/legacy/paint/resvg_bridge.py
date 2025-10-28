"""Bridge helpers between resvg paint styles and the svg2ooxml IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

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
    stroke_paint = resolve_stroke_style(node.stroke, tree)
    return NormalizedPaints(fill=fill_paint, stroke=stroke_paint)


def resolve_fill_paint(fill: FillStyle | None, tree: Tree) -> Paint:
    """Convert a resvg FillStyle into an svg2ooxml Paint object."""

    if fill is None:
        return None
    if fill.color is not None:
        return _color_to_solid(fill.color, fill.opacity)
    if fill.reference is not None:
        return _resolve_paint_reference(fill.reference, tree)
    return None


def resolve_stroke_style(stroke: StrokeStyle | None, tree: Tree) -> Stroke | None:
    """Convert a resvg StrokeStyle into an svg2ooxml Stroke."""

    if stroke is None:
        return None

    paint: Paint
    if stroke.color is not None:
        paint = _color_to_solid(stroke.color, stroke.opacity)
    elif stroke.reference is not None:
        paint = _resolve_paint_reference(stroke.reference, tree)
    else:
        paint = None

    width = stroke.width if stroke.width is not None else 0.0
    if paint is None and width <= 0.0:
        return None

    return Stroke(
        paint=paint,
        width=width,
        join=StrokeJoin.MITER,
        cap=StrokeCap.BUTT,
        miter_limit=4.0,
        dash_array=None,
        dash_offset=0.0,
        opacity=stroke.opacity,
    )


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
    return [
        GradientStop(
            offset=stop.offset,
            rgb=_color_to_hex(stop.color),
            opacity=stop.color.a,
        )
        for stop in stops
    ]


def _color_to_solid(color: Color, opacity: float | None) -> SolidPaint:
    return SolidPaint(
        rgb=_color_to_hex(color),
        opacity=opacity if opacity is not None else color.a,
    )


def _color_to_hex(color: Color) -> str:
    r = _clamp_byte(color.r * 255.0)
    g = _clamp_byte(color.g * 255.0)
    b = _clamp_byte(color.b * 255.0)
    return f"{r:02X}{g:02X}{b:02X}"


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _matrix_to_array(matrix: ResvgMatrix | None) -> Optional[np.ndarray]:
    if matrix is None:
        return None
    return np.array(
        [
            [matrix.a, matrix.c, matrix.e],
            [matrix.b, matrix.d, matrix.f],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


__all__ = [
    "NormalizedPaints",
    "resolve_fill_paint",
    "resolve_paints_for_node",
    "resolve_stroke_style",
]
