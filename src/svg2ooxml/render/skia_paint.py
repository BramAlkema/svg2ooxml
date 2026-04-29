"""Skia paint and shader helpers for the raster render pipeline."""

from __future__ import annotations

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("svg2ooxml.render requires skia-python; install the 'render' extra.") from exc

from svg2ooxml.common.skia_helpers import tile_mode as _skia_tile_mode
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop,
    LinearGradient,
    PatternPaint,
    RadialGradient,
)
from svg2ooxml.core.resvg.painting.paint import Color, FillStyle, StrokeStyle
from svg2ooxml.core.resvg.usvg_tree import PatternNode, Tree


def make_fill_paint(
    fill: FillStyle,
    tree: Tree,
    bounds: tuple[float, float, float, float] | None,
) -> skia.Paint | None:
    paint = skia.Paint(AntiAlias=True)
    paint.setStyle(skia.Paint.kFill_Style)

    if fill.reference is None:
        color = fill.color
        if color is None:
            return None
        paint.setColor4f(color_to_skia(color))
        return paint

    paint_server = tree.resolve_paint(fill.reference)
    if paint_server is None:
        return None

    if isinstance(paint_server, LinearGradient):
        shader = make_linear_gradient_shader(paint_server, bounds, fill.opacity)
    elif isinstance(paint_server, RadialGradient):
        shader = make_radial_gradient_shader(paint_server, bounds, fill.opacity)
    elif isinstance(paint_server, PatternPaint):
        shader = make_pattern_shader(fill, tree)
    else:
        shader = None

    if shader is None:
        return None
    paint.setShader(shader)
    return paint


def make_stroke_paint(
    stroke: StrokeStyle,
    tree: Tree,
    bounds: tuple[float, float, float, float] | None,
) -> skia.Paint | None:
    paint = skia.Paint(AntiAlias=True)
    paint.setStyle(skia.Paint.kStroke_Style)
    paint.setStrokeWidth(stroke.width or 0.0)
    paint.setStrokeCap(skia.Paint.Cap.kButt_Cap)
    paint.setStrokeJoin(skia.Paint.Join.kMiter_Join)

    if stroke.reference is None:
        color = stroke.color
        if color is None:
            return None
        paint.setColor4f(color_to_skia(color))
        return paint

    paint_server = tree.resolve_paint(stroke.reference)
    if paint_server is None:
        return None

    if isinstance(paint_server, LinearGradient):
        shader = make_linear_gradient_shader(paint_server, bounds, stroke.opacity)
    elif isinstance(paint_server, RadialGradient):
        shader = make_radial_gradient_shader(paint_server, bounds, stroke.opacity)
    else:
        shader = None

    if shader is None:
        return None
    paint.setShader(shader)
    return paint


def prepare_gradient_stops(
    stops: tuple[GradientStop, ...],
    opacity: float,
) -> tuple[list[float], list[skia.Color4f]] | None:
    if not stops:
        return None
    positions: list[float] = []
    colors: list[skia.Color4f] = []
    for stop in stops:
        offset = max(0.0, min(1.0, stop.offset))
        color = stop.color
        alpha = color.a * opacity
        positions.append(offset)
        colors.append(skia.Color4f(color.r, color.g, color.b, alpha))
    return positions, colors


def make_linear_gradient_shader(
    gradient: LinearGradient,
    bounds: tuple[float, float, float, float] | None,
    opacity: float,
) -> skia.Shader | None:
    if bounds is None:
        return None
    prepared = prepare_gradient_stops(gradient.stops, opacity)
    if prepared is None:
        return None
    positions, colors = prepared
    x1, y1, x2, y2 = linear_gradient_points(gradient, bounds)
    if x1 == x2 and y1 == y2:
        return None
    tile_mode = resolve_tile_mode(gradient.spread_method)
    matrix = to_skia_matrix(gradient.transform)
    return skia.GradientShader.MakeLinear(
        [skia.Point(x1, y1), skia.Point(x2, y2)],
        colors,
        positions,
        tile_mode,
        0,
        matrix,
    )


def make_radial_gradient_shader(
    gradient: RadialGradient,
    bounds: tuple[float, float, float, float] | None,
    opacity: float,
) -> skia.Shader | None:
    if bounds is None:
        return None
    prepared = prepare_gradient_stops(gradient.stops, opacity)
    if prepared is None:
        return None
    positions, colors = prepared

    cx, cy, radius = radial_gradient_params(gradient, bounds)
    if radius <= 0:
        return None

    tile_mode = resolve_tile_mode(gradient.spread_method)
    matrix = to_skia_matrix(gradient.transform)

    fx, fy = radial_gradient_focus(gradient, bounds)
    if fx != cx or fy != cy:
        return skia.GradientShader.MakeTwoPointConical(
            skia.Point(fx, fy),
            0.0,
            skia.Point(cx, cy),
            radius,
            colors,
            positions,
            tile_mode,
            0,
            matrix,
        )

    return skia.GradientShader.MakeRadial(
        skia.Point(cx, cy),
        radius,
        colors,
        positions,
        tile_mode,
        0,
        matrix,
    )


def make_pattern_shader(fill: FillStyle, tree: Tree) -> skia.Shader | None:
    reference = fill.reference
    reference_id = local_url_id(reference.href if reference is not None else None)
    if reference_id is None:
        return None
    pattern_node = tree.paint_servers.get(reference_id)
    if not isinstance(pattern_node, PatternNode):
        return None
    for child in pattern_node.children:
        child_fill = getattr(child, "fill", None)
        if child_fill and child_fill.color:
            color = child_fill.color
            alpha = color.a * fill.opacity
            return skia.Shaders.Color(skia.Color4f(color.r, color.g, color.b, alpha))
    return None


def resolve_tile_mode(spread_method: str) -> skia.TileMode:
    return _skia_tile_mode(skia, spread_method)


def linear_gradient_points(
    gradient: LinearGradient,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = bounds
    width = max(max_x - min_x, 0.0)
    height = max(max_y - min_y, 0.0)
    if gradient.units == "objectBoundingBox":
        x1 = min_x + gradient.x1 * width
        y1 = min_y + gradient.y1 * height
        x2 = min_x + gradient.x2 * width
        y2 = min_y + gradient.y2 * height
    else:
        x1 = gradient.x1
        y1 = gradient.y1
        x2 = gradient.x2
        y2 = gradient.y2
    return x1, y1, x2, y2


def radial_gradient_params(
    gradient: RadialGradient,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    min_x, min_y, max_x, max_y = bounds
    width = max(max_x - min_x, 0.0)
    height = max(max_y - min_y, 0.0)
    if gradient.units == "objectBoundingBox":
        cx = min_x + gradient.cx * width
        cy = min_y + gradient.cy * height
        radius = gradient.r * (width + height) * 0.5
    else:
        cx = gradient.cx
        cy = gradient.cy
        radius = gradient.r
    return cx, cy, radius


def radial_gradient_focus(
    gradient: RadialGradient,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    width = max(max_x - min_x, 0.0)
    height = max(max_y - min_y, 0.0)
    if gradient.units == "objectBoundingBox":
        fx = min_x + gradient.fx * width
        fy = min_y + gradient.fy * height
    else:
        fx = gradient.fx
        fy = gradient.fy
    return fx, fy


def to_skia_matrix(matrix) -> skia.Matrix:
    return skia.Matrix.MakeAll(
        matrix.a,
        matrix.c,
        matrix.e,
        matrix.b,
        matrix.d,
        matrix.f,
        0.0,
        0.0,
        1.0,
    )


def color_to_skia(color: Color) -> skia.Color4f:
    return skia.Color4f(color.r, color.g, color.b, color.a)


__all__ = [
    "color_to_skia",
    "linear_gradient_points",
    "make_fill_paint",
    "make_linear_gradient_shader",
    "make_pattern_shader",
    "make_radial_gradient_shader",
    "make_stroke_paint",
    "prepare_gradient_stops",
    "radial_gradient_focus",
    "radial_gradient_params",
    "resolve_tile_mode",
    "to_skia_matrix",
]
