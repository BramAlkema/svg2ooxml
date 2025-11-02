"""Primitive render pipeline producing a raster surface."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("svg2ooxml.render requires skia-python; install the 'render' extra.") from exc

from svg2ooxml.core.resvg.geometry.primitives import ClosePath, LineTo, MoveTo
from svg2ooxml.core.resvg.geometry.tessellation import TessellationResult, Tessellator
from svg2ooxml.core.resvg.painting.gradients import GradientStop, LinearGradient, PatternPaint, RadialGradient
from svg2ooxml.core.resvg.painting.paint import Color, FillStyle, StrokeStyle
from svg2ooxml.core.resvg.usvg_tree import BaseNode, PathNode, PatternNode, Tree
from svg2ooxml.render.filters import UnsupportedPrimitiveError, apply_filter, plan_filter
from svg2ooxml.render.mask_clip import (
    ClipPathContext,
    MaskContext,
    apply_clip,
    apply_mask,
    rasterize_clip_path,
    rasterize_mask,
    resolve_clip_path,
    resolve_mask,
)
from svg2ooxml.render.markers import compute_marker_positions, resolve_marker
from svg2ooxml.render.rasterizer import Rasterizer, Viewport
from svg2ooxml.render.shapes import node_geometry
from svg2ooxml.render.surface import Surface

_DEFINITION_TAGS = {
    "defs",
    "mask",
    "clipPath",
    "linearGradient",
    "radialGradient",
    "pattern",
    "marker",
    "filter",
}


@dataclass(slots=True)
class RenderContext:
    tessellator: Tessellator
    rasterizer: Rasterizer
    mask_cache: dict[str, np.ndarray] = field(default_factory=dict)
    clip_cache: dict[str, np.ndarray] = field(default_factory=dict)


def render(tree: Tree, context: Optional[RenderContext] = None) -> Surface:
    viewport = Viewport.from_tree(tree)
    surface = Surface.make(viewport.width, viewport.height)
    context = context or RenderContext(
        tessellator=Tessellator(),
        rasterizer=Rasterizer(),
    )
    _render_node(tree.root, tree, context, surface, viewport)
    return surface


def _render_node(
    node: BaseNode,
    tree: Tree,
    context: RenderContext,
    surface: Surface,
    viewport: Viewport,
) -> None:
    if node.tag in _DEFINITION_TAGS:
        return

    geometry = node_geometry(node)
    if geometry is not None:
        _render_shape_node(node, geometry, tree, context, surface, viewport)

    for child in node.children:
        _render_node(child, tree, context, surface, viewport)


def _render_shape_node(
    node: BaseNode,
    geometry,
    tree: Tree,
    context: RenderContext,
    surface: Surface,
    viewport: Viewport,
) -> None:
    if isinstance(node, PathNode) and node.geometry is not None:
        marker_href = node.attributes.get("marker-start")
        marker = resolve_marker(tree, marker_href)
        if marker:
            compute_marker_positions(list(node.geometry.to_primitives()))

    mask_ctx = resolve_mask(tree, node.attributes.get("mask"))
    clip_ctx = resolve_clip_path(tree, node.attributes.get("clip-path"))
    filter_href = _clean_href(node.attributes.get("filter"))
    filter_plan = None
    if filter_href:
        filter_node = tree.resolve_filter(filter_href)
        if filter_node:
            filter_plan = plan_filter(filter_node)

    mask_alpha = _resolve_mask_alpha(mask_ctx, context, viewport) if mask_ctx else None
    clip_mask = _resolve_clip_mask(clip_ctx, context, viewport) if clip_ctx else None

    if node.fill:
        _render_fill(
            node,
            geometry,
            node.fill,
            tree,
            context,
            surface,
            viewport,
            mask_alpha,
            clip_mask,
            filter_plan,
        )
    if node.stroke:
        _render_stroke(
            node,
            geometry,
            node.stroke,
            tree,
            context,
            surface,
            viewport,
            mask_alpha,
            clip_mask,
            filter_plan,
        )


def _render_fill(
    node: BaseNode,
    geometry,
    fill: FillStyle,
    tree: Tree,
    context: RenderContext,
    surface: Surface,
    viewport: Viewport,
    mask_alpha: Optional[np.ndarray],
    clip_mask: Optional[np.ndarray],
    filter_plan,
) -> None:
    tessellation = context.tessellator.tessellate_fill(geometry)
    if not tessellation.contours:
        return

    sk_path = _build_skia_path(geometry, tessellation.winding_rule)
    if sk_path is None:
        return

    bounds = _tessellation_bounds(tessellation)
    paint = _make_fill_paint(fill, tree, bounds)
    if paint is None:
        return

    layer = _draw_path_with_skia(sk_path, paint, viewport)

    if filter_plan is not None and bounds is not None:
        try:
            layer = apply_filter(layer, filter_plan, bounds, viewport)
        except UnsupportedPrimitiveError:
            pass

    if mask_alpha is not None:
        layer = apply_mask(layer, mask_alpha)
    if clip_mask is not None:
        layer = apply_clip(layer, clip_mask)
    surface.blend(layer)


def _render_stroke(
    node: BaseNode,
    geometry,
    stroke: StrokeStyle,
    tree: Tree,
    context: RenderContext,
    surface: Surface,
    viewport: Viewport,
    mask_alpha: Optional[np.ndarray],
    clip_mask: Optional[np.ndarray],
    filter_plan,
) -> None:
    if stroke.width is None or stroke.width <= 0:
        return

    tessellation = context.tessellator.tessellate_fill(geometry)
    if not tessellation.contours:
        return

    sk_path = _build_skia_path(geometry, tessellation.winding_rule)
    if sk_path is None:
        return

    bounds = _tessellation_bounds(tessellation)
    paint = _make_stroke_paint(stroke, tree, bounds)
    if paint is None:
        return

    layer = _draw_path_with_skia(sk_path, paint, viewport)

    if filter_plan is not None and bounds is not None:
        try:
            layer = apply_filter(layer, filter_plan, bounds, viewport)
        except UnsupportedPrimitiveError:
            pass

    if mask_alpha is not None:
        layer = apply_mask(layer, mask_alpha)
    if clip_mask is not None:
        layer = apply_clip(layer, clip_mask)
    surface.blend(layer)


def _build_skia_path(geometry, winding_rule: str) -> Optional[skia.Path]:
    path = skia.Path()
    if winding_rule == "evenodd":
        path.setFillType(skia.PathFillType.kEvenOdd)
    else:
        path.setFillType(skia.PathFillType.kWinding)

    for primitive in geometry.to_primitives():
        if isinstance(primitive, MoveTo):
            path.moveTo(primitive.x, primitive.y)
        elif isinstance(primitive, LineTo):
            path.lineTo(primitive.x, primitive.y)
        elif isinstance(primitive, ClosePath):
            path.close()

    if path.isEmpty():
        return None
    return path


def _draw_path_with_skia(path: skia.Path, paint: skia.Paint, viewport: Viewport) -> Surface:
    surface = skia.Surface(viewport.width, viewport.height)
    canvas = surface.getCanvas()
    canvas.clear(skia.Color4f(0.0, 0.0, 0.0, 0.0))

    device_matrix = skia.Matrix.MakeAll(
        viewport.scale_x,
        0.0,
        -viewport.min_x * viewport.scale_x,
        0.0,
        viewport.scale_y,
        -viewport.min_y * viewport.scale_y,
        0.0,
        0.0,
        1.0,
    )
    canvas.concat(device_matrix)
    canvas.drawPath(path, paint)

    image = surface.makeImageSnapshot()
    rgba = image.toarray().astype(np.float32) / 255.0

    # Handle platform-specific color channel ordering
    # Some Skia builds use BGRA instead of RGBA
    if image.colorType() == skia.ColorType.kBGRA_8888_ColorType:
        # Swap R and B channels: BGRA -> RGBA
        rgba[:, :, [0, 2]] = rgba[:, :, [2, 0]]

    rgba[..., :3] *= rgba[..., 3:4]
    return Surface(width=viewport.width, height=viewport.height, data=rgba)


def _make_fill_paint(fill: FillStyle, tree: Tree, bounds: Optional[tuple[float, float, float, float]]) -> Optional[skia.Paint]:
    paint = skia.Paint(AntiAlias=True)
    paint.setStyle(skia.Paint.kFill_Style)

    if fill.reference is None:
        color = fill.color
        if color is None:
            return None
        paint.setColor4f(_color_to_skia(color))
        return paint

    paint_server = tree.resolve_paint(fill.reference)
    if paint_server is None:
        return None

    if isinstance(paint_server, LinearGradient):
        shader = _make_linear_gradient_shader(paint_server, bounds, fill.opacity)
    elif isinstance(paint_server, RadialGradient):
        shader = _make_radial_gradient_shader(paint_server, bounds, fill.opacity)
    elif isinstance(paint_server, PatternPaint):
        shader = _make_pattern_shader(fill, tree)
    else:
        shader = None

    if shader is None:
        return None
    paint.setShader(shader)
    return paint


def _make_stroke_paint(stroke: StrokeStyle, tree: Tree, bounds: Optional[tuple[float, float, float, float]]) -> Optional[skia.Paint]:
    paint = skia.Paint(AntiAlias=True)
    paint.setStyle(skia.Paint.kStroke_Style)
    paint.setStrokeWidth(stroke.width or 0.0)
    paint.setStrokeCap(skia.Paint.Cap.kButt_Cap)
    paint.setStrokeJoin(skia.Paint.Join.kMiter_Join)

    if stroke.reference is None:
        color = stroke.color
        if color is None:
            return None
        paint.setColor4f(_color_to_skia(color))
        return paint

    paint_server = tree.resolve_paint(stroke.reference)
    if paint_server is None:
        return None

    if isinstance(paint_server, LinearGradient):
        shader = _make_linear_gradient_shader(paint_server, bounds, stroke.opacity)
    elif isinstance(paint_server, RadialGradient):
        shader = _make_radial_gradient_shader(paint_server, bounds, stroke.opacity)
    else:
        shader = None

    if shader is None:
        return None
    paint.setShader(shader)
    return paint


def _prepare_gradient_stops(
    stops: tuple[GradientStop, ...],
    opacity: float,
) -> Optional[tuple[list[float], list[skia.Color4f]]]:
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


def _make_linear_gradient_shader(
    gradient: LinearGradient,
    bounds: Optional[tuple[float, float, float, float]],
    opacity: float,
) -> Optional[skia.Shader]:
    if bounds is None:
        return None
    prepared = _prepare_gradient_stops(gradient.stops, opacity)
    if prepared is None:
        return None
    positions, colors = prepared
    x1, y1, x2, y2 = _linear_gradient_points(gradient, bounds)
    if x1 == x2 and y1 == y2:
        return None
    tile_mode = _resolve_tile_mode(gradient.spread_method)
    matrix = _to_skia_matrix(gradient.transform)
    return skia.GradientShader.MakeLinear(
        [skia.Point(x1, y1), skia.Point(x2, y2)],
        colors,
        positions,
        tile_mode,
        0,
        matrix,
    )


def _make_radial_gradient_shader(
    gradient: RadialGradient,
    bounds: Optional[tuple[float, float, float, float]],
    opacity: float,
) -> Optional[skia.Shader]:
    if bounds is None:
        return None
    prepared = _prepare_gradient_stops(gradient.stops, opacity)
    if prepared is None:
        return None
    positions, colors = prepared

    cx, cy, radius = _radial_gradient_params(gradient, bounds)
    if radius <= 0:
        return None

    tile_mode = _resolve_tile_mode(gradient.spread_method)
    matrix = _to_skia_matrix(gradient.transform)

    fx, fy = _radial_gradient_focus(gradient, bounds)
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


def _make_pattern_shader(fill: FillStyle, tree: Tree) -> Optional[skia.Shader]:
    reference = fill.reference
    if reference is None or not reference.href.startswith("#"):
        return None
    pattern_node = tree.paint_servers.get(reference.href[1:])
    if not isinstance(pattern_node, PatternNode):
        return None
    for child in pattern_node.children:
        child_fill = getattr(child, "fill", None)
        if child_fill and child_fill.color:
            color = child_fill.color
            alpha = color.a * fill.opacity
            return skia.Shaders.Color(skia.Color4f(color.r, color.g, color.b, alpha))
    return None


def _resolve_tile_mode(spread_method: str) -> skia.TileMode:
    if spread_method == "repeat":
        return skia.TileMode.kRepeat
    if spread_method == "reflect":
        return skia.TileMode.kMirror
    return skia.TileMode.kClamp


def _linear_gradient_points(
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


def _radial_gradient_params(
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


def _radial_gradient_focus(
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


def _to_skia_matrix(matrix) -> skia.Matrix:
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


def _tessellation_bounds(tessellation: TessellationResult) -> Optional[tuple[float, float, float, float]]:
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for contour in tessellation.contours:
        if not contour:
            continue
        xs = [point[0] for point in contour]
        ys = [point[1] for point in contour]
        min_x = min(min_x, min(xs))
        min_y = min(min_y, min(ys))
        max_x = max(max_x, max(xs))
        max_y = max(max_y, max(ys))
    if min_x is math.inf or min_y is math.inf:
        return None
    return min_x, min_y, max_x, max_y


def _resolve_mask_alpha(context: Optional[MaskContext], render_context: RenderContext, viewport: Viewport) -> Optional[np.ndarray]:
    if context is None:
        return None
    mask_id = context.node.id
    if mask_id and mask_id in render_context.mask_cache:
        return render_context.mask_cache[mask_id]
    alpha = rasterize_mask(context, render_context.tessellator, render_context.rasterizer, viewport)
    if mask_id:
        render_context.mask_cache[mask_id] = alpha
    return alpha


def _resolve_clip_mask(context: Optional[ClipPathContext], render_context: RenderContext, viewport: Viewport) -> Optional[np.ndarray]:
    if context is None:
        return None
    clip_id = context.node.id
    if clip_id and clip_id in render_context.clip_cache:
        return render_context.clip_cache[clip_id]
    mask = rasterize_clip_path(context, render_context.tessellator, render_context.rasterizer, viewport)
    if clip_id:
        render_context.clip_cache[clip_id] = mask
    return mask


def _color_to_skia(color: Color) -> skia.Color4f:
    return skia.Color4f(color.r, color.g, color.b, color.a)


def _clean_href(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.startswith("url(") and value.endswith(")"):
        value = value[4:-1].strip()
    return value


__all__ = ["RenderContext", "render"]
