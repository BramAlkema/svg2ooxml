"""Primitive render pipeline producing a raster surface."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("svg2ooxml.render requires skia-python; install the 'render' extra.") from exc

from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.common.svg_refs import unwrap_url_reference
from svg2ooxml.core.resvg.geometry.primitives import ClosePath, LineTo, MoveTo
from svg2ooxml.core.resvg.geometry.tessellation import TessellationResult, Tessellator
from svg2ooxml.core.resvg.painting.paint import FillStyle, StrokeStyle
from svg2ooxml.core.resvg.usvg_tree import (
    BaseNode,
    ImageNode,
    PathNode,
    Tree,
)
from svg2ooxml.render.filters import (
    UnsupportedPrimitiveError,
    apply_filter,
    plan_filter,
)
from svg2ooxml.render.markers import compute_marker_positions, resolve_marker
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
from svg2ooxml.render.rasterizer import Rasterizer, Viewport
from svg2ooxml.render.shapes import node_geometry
from svg2ooxml.render.skia_paint import (
    make_fill_paint as _make_fill_paint,
)
from svg2ooxml.render.skia_paint import (
    make_stroke_paint as _make_stroke_paint,
)
from svg2ooxml.render.skia_paint import (
    to_skia_matrix as _to_skia_matrix,
)
from svg2ooxml.render.surface import Surface

np = require_numpy("svg2ooxml.render requires NumPy; install the 'render' extra.")

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


def render(tree: Tree, context: RenderContext | None = None) -> Surface:
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

    if isinstance(node, ImageNode):
        _render_image(node, tree, context, surface, viewport)
    else:
        geometry = node_geometry(node)
        if geometry is not None:
            _render_shape_node(node, geometry, tree, context, surface, viewport)

    for child in node.children:
        _render_node(child, tree, context, surface, viewport)


def _render_image(
    node: ImageNode,
    tree: Tree,
    context: RenderContext,
    surface: Surface,
    viewport: Viewport,
) -> None:
    if not node.data:
        return

    try:
        image = skia.Image.MakeFromEncoded(node.data)
        if not image:
            return
    except Exception:
        return

    x = node.x
    y = node.y
    width = node.width or 0.0
    height = node.height or 0.0

    if width <= 0 or height <= 0:
        return

    layer_surface = skia.Surface(viewport.width, viewport.height)
    canvas = layer_surface.getCanvas()
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
    node_matrix = _to_skia_matrix(node.transform)
    total_matrix = skia.Matrix()
    total_matrix.setConcat(device_matrix, node_matrix)
    canvas.concat(total_matrix)

    paint = skia.Paint(AntiAlias=True)
    if node.presentation.opacity is not None:
        paint.setAlphaf(max(0.0, min(1.0, node.presentation.opacity)))

    src_rect = skia.Rect.MakeWH(image.width(), image.height())
    dst_rect = skia.Rect.MakeXYWH(x, y, width, height)
    canvas.drawImageRect(
        image,
        src_rect,
        dst_rect,
        skia.SamplingOptions(),
        paint,
    )

    snapshot = layer_surface.makeImageSnapshot()
    rgba = snapshot.toarray().astype(np.float32) / 255.0
    if snapshot.colorType() == skia.ColorType.kBGRA_8888_ColorType:
        rgba[:, :, [0, 2]] = rgba[:, :, [2, 0]]
    rgba[..., :3] *= rgba[..., 3:4]
    
    layer = Surface(width=viewport.width, height=viewport.height, data=rgba)

    # Apply effects
    mask_ctx = resolve_mask(tree, node.attributes.get("mask"))
    clip_ctx = resolve_clip_path(tree, node.attributes.get("clip-path"))
    filter_href = unwrap_url_reference(node.attributes.get("filter"))
    
    # Calculate bounds for filter
    # We transform (x, y, w, h) by node_matrix to get user-space bounds
    # Note: filter region calculation usually expects bounding box in user space.
    # The 'bounds' argument to apply_filter expects (min_x, min_y, max_x, max_y).
    # Since resvg filter logic handles units, we pass the untransformed bounds? 
    # No, it expects the bounding box of the element in the current user coordinate system.
    # But node.transform is ALREADY applied to the canvas.
    # Wait, `apply_filter` logic uses `bounds` to determine `objectBoundingBox`.
    # For objectBoundingBox, it needs the bounds *before* the filter effect is applied?
    # SVG spec says: "The bounding box is the tightest fitting rectangle aligned with the axes of that element's user coordinate system that entirely encloses it and its descendants."
    # So it's x, y, width, height.
    bounds = _transformed_image_bounds(node, x, y, width, height)

    if filter_href:
        filter_node = tree.resolve_filter(filter_href)
        if filter_node:
            filter_plan = plan_filter(filter_node)
            if filter_plan:
                try:
                    layer = apply_filter(layer, filter_plan, bounds, viewport)
                except UnsupportedPrimitiveError:
                    pass

    if mask_ctx:
        mask_alpha = _resolve_mask_alpha(mask_ctx, context, viewport)
        if mask_alpha is not None:
            layer = apply_mask(layer, mask_alpha)
            
    if clip_ctx:
        clip_mask = _resolve_clip_mask(clip_ctx, context, viewport)
        if clip_mask is not None:
            layer = apply_clip(layer, clip_mask)

    surface.blend(layer)


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
    filter_href = unwrap_url_reference(node.attributes.get("filter"))
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
    mask_alpha: np.ndarray | None,
    clip_mask: np.ndarray | None,
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
    mask_alpha: np.ndarray | None,
    clip_mask: np.ndarray | None,
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


def _build_skia_path(geometry, winding_rule: str) -> skia.Path | None:
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


def _transformed_image_bounds(
    node: ImageNode,
    x: float,
    y: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    matrix = getattr(node, "transform", None)
    if matrix is None:
        return (x, y, x + width, y + height)

    corners = (
        matrix.apply_to_point(x, y),
        matrix.apply_to_point(x + width, y),
        matrix.apply_to_point(x, y + height),
        matrix.apply_to_point(x + width, y + height),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _tessellation_bounds(tessellation: TessellationResult) -> tuple[float, float, float, float] | None:
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


def _resolve_mask_alpha(context: MaskContext | None, render_context: RenderContext, viewport: Viewport) -> np.ndarray | None:
    if context is None:
        return None
    mask_id = context.node.id
    if mask_id and mask_id in render_context.mask_cache:
        return render_context.mask_cache[mask_id]
    alpha = rasterize_mask(context, render_context.tessellator, render_context.rasterizer, viewport)
    if mask_id:
        render_context.mask_cache[mask_id] = alpha
    return alpha


def _resolve_clip_mask(context: ClipPathContext | None, render_context: RenderContext, viewport: Viewport) -> np.ndarray | None:
    if context is None:
        return None
    clip_id = context.node.id
    if clip_id and clip_id in render_context.clip_cache:
        return render_context.clip_cache[clip_id]
    mask = rasterize_clip_path(context, render_context.tessellator, render_context.rasterizer, viewport)
    if clip_id:
        render_context.clip_cache[clip_id] = mask
    return mask

__all__ = ["RenderContext", "render"]
