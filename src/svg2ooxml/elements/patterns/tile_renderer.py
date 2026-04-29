"""Raster tile builder for simple SVG dot patterns."""

from __future__ import annotations

import math
from collections.abc import Iterator

from lxml import etree as ET

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.core.styling.style_helpers import clean_color
from svg2ooxml.elements.patterns._helpers import (
    is_dot_like_path,
    is_visible_paint_token,
    local_name,
    parse_float_attr,
    pattern_opacity,
    style_map,
)
from svg2ooxml.elements.patterns.geometry import is_translation_only
from svg2ooxml.elements.patterns.types import (
    PatternAnalysis,
    PatternComplexity,
    PatternType,
)
from svg2ooxml.render.rgba import (
    encode_rgba8_png as encode_rgba_png,
)
from svg2ooxml.render.rgba import (
    source_over_straight_rgba8_pixel as composite_rgba_pixel,
)

TileEllipse = tuple[float, float, float, float, tuple[int, int, int], float]


def build_tile_payload(
    element: ET.Element,
    *,
    analysis: PatternAnalysis,
) -> tuple[bytes, int, int] | None:
    """Build a reusable tile image for simple translated dot patterns."""
    if analysis.pattern_type != PatternType.DOTS:
        return None
    if analysis.complexity != PatternComplexity.SIMPLE:
        return None
    if analysis.geometry.transform_matrix is None:
        return None
    if not is_translation_only(analysis.geometry.transform_matrix):
        return None

    tile_width = max(analysis.geometry.tile_width, 0.0)
    tile_height = max(analysis.geometry.tile_height, 0.0)
    width_px = max(int(math.ceil(tile_width)), 1)
    height_px = max(int(math.ceil(tile_height)), 1)

    ellipses = list(
        iter_tile_ellipses(
            element,
            tile_width=tile_width,
            tile_height=tile_height,
        )
    )
    if not ellipses:
        return None

    pixels = bytearray(width_px * height_px * 4)
    for center_x, center_y, radius_x, radius_y, color, opacity in ellipses:
        rasterize_ellipse(
            pixels,
            width_px=width_px,
            height_px=height_px,
            center_x=center_x,
            center_y=center_y,
            radius_x=radius_x,
            radius_y=radius_y,
            color=color,
            opacity=opacity,
        )

    return encode_rgba_png(pixels, width_px, height_px), width_px, height_px


def iter_tile_ellipses(
    element: ET.Element,
    *,
    tile_width: float,
    tile_height: float,
) -> Iterator[TileEllipse]:
    """Yield visible ellipse-like dot geometry for a pattern tile."""

    def _walk(node: ET.Element, transform: Matrix2D) -> Iterator[TileEllipse]:
        current = transform
        transform_attr = node.get("transform")
        if transform_attr:
            try:
                current = current.multiply(parse_transform_list(transform_attr))
            except Exception:
                current = transform

        for child in node:
            if not isinstance(child.tag, str):
                continue
            tag = local_name(child.tag)
            if tag in {"g", "a", "switch"}:
                yield from _walk(child, current)
                continue
            fill_spec = pattern_fill_spec(child)
            if fill_spec is None:
                continue
            ellipse = tile_ellipse_geometry(child, current)
            if ellipse is None:
                continue
            center_x, center_y, radius_x, radius_y = ellipse
            if (
                center_x + radius_x < 0.0
                or center_y + radius_y < 0.0
                or center_x - radius_x > tile_width
                or center_y - radius_y > tile_height
            ):
                continue
            yield (
                center_x,
                center_y,
                radius_x,
                radius_y,
                fill_spec[0],
                fill_spec[1],
            )

    yield from _walk(element, Matrix2D.identity())


def pattern_fill_spec(
    element: ET.Element,
) -> tuple[tuple[int, int, int], float] | None:
    sm = style_map(element)
    fill = element.get("fill") or sm.get("fill")
    if not is_visible_paint_token(fill):
        return None
    color = clean_color(fill)
    if color is None:
        return None
    opacity = pattern_opacity(
        sm.get("fill-opacity") or element.get("fill-opacity"),
        default=1.0,
    )
    opacity *= pattern_opacity(sm.get("opacity") or element.get("opacity"))
    return (
        (
            int(color[0:2], 16),
            int(color[2:4], 16),
            int(color[4:6], 16),
        ),
        max(0.0, min(1.0, opacity)),
    )


def tile_ellipse_geometry(
    element: ET.Element,
    transform: Matrix2D,
) -> tuple[float, float, float, float] | None:
    if abs(transform.b) > 1e-9 or abs(transform.c) > 1e-9:
        return None

    tag = local_name(element.tag)
    geometry: tuple[float, float, float, float] | None = None
    if tag == "circle":
        cx = parse_float_attr(element, "cx", axis="x")
        cy = parse_float_attr(element, "cy", axis="y")
        radius = parse_float_attr(element, "r", axis="x")
        if cx is not None and cy is not None and radius is not None:
            geometry = (cx, cy, radius, radius)
    elif tag == "ellipse":
        cx = parse_float_attr(element, "cx", axis="x")
        cy = parse_float_attr(element, "cy", axis="y")
        rx = parse_float_attr(element, "rx", axis="x")
        ry = parse_float_attr(element, "ry", axis="y")
        if cx is not None and cy is not None and rx is not None and ry is not None:
            geometry = (cx, cy, rx, ry)
    elif tag == "path":
        geometry = path_ellipse_geometry(element)

    if geometry is None:
        return None

    cx, cy, rx, ry = geometry
    center_x, center_y = transform.transform_xy(cx, cy)
    edge_x, _edge_y = transform.transform_xy(cx + rx, cy)
    _up_x, up_y = transform.transform_xy(cx, cy + ry)
    radius_x = abs(edge_x - center_x)
    radius_y = abs(up_y - center_y)
    if radius_x <= 0.0 or radius_y <= 0.0:
        return None
    return center_x, center_y, radius_x, radius_y


def path_ellipse_geometry(
    element: ET.Element,
) -> tuple[float, float, float, float] | None:
    sodipodi_ns = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
    cx = parse_float_attr(element, f"{{{sodipodi_ns}}}cx", axis="x")
    cy = parse_float_attr(element, f"{{{sodipodi_ns}}}cy", axis="y")
    rx = parse_float_attr(element, f"{{{sodipodi_ns}}}rx", axis="x")
    ry = parse_float_attr(element, f"{{{sodipodi_ns}}}ry", axis="y")
    if cx is not None and cy is not None and rx is not None and ry is not None:
        return (cx, cy, rx, ry)

    if not is_dot_like_path(element):
        return None

    path_data = element.get("d") or ""
    path_data_upper = path_data.upper()
    if "M" not in path_data_upper or "A" not in path_data_upper:
        return None

    values = parse_numeric_list(path_data)
    if len(values) < 4:
        return None
    start_x, start_y, radius_x, radius_y = values[:4]
    return (start_x - radius_x, start_y, radius_x, radius_y)


def rasterize_ellipse(
    pixels: bytearray,
    *,
    width_px: int,
    height_px: int,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
    color: tuple[int, int, int],
    opacity: float,
) -> None:
    if opacity <= 0.0:
        return
    min_x = max(int(math.floor(center_x - radius_x - 1.0)), 0)
    max_x = min(int(math.ceil(center_x + radius_x + 1.0)), width_px)
    min_y = max(int(math.floor(center_y - radius_y - 1.0)), 0)
    max_y = min(int(math.ceil(center_y + radius_y + 1.0)), height_px)
    if min_x >= max_x or min_y >= max_y:
        return

    sample_offsets = (0.25, 0.75)
    inv_rx = 1.0 / radius_x
    inv_ry = 1.0 / radius_y

    for py in range(min_y, max_y):
        for px in range(min_x, max_x):
            coverage = 0
            for sy in sample_offsets:
                for sx in sample_offsets:
                    dx = ((px + sx) - center_x) * inv_rx
                    dy = ((py + sy) - center_y) * inv_ry
                    if dx * dx + dy * dy <= 1.0:
                        coverage += 1
            if coverage == 0:
                continue
            alpha = opacity * (coverage / 4.0)
            composite_rgba_pixel(
                pixels,
                width_px=width_px,
                x=px,
                y=py,
                color=color,
                alpha=alpha,
            )


__all__ = [
    "build_tile_payload",
    "composite_rgba_pixel",
    "encode_rgba_png",
    "iter_tile_ellipses",
    "path_ellipse_geometry",
    "pattern_fill_spec",
    "rasterize_ellipse",
    "tile_ellipse_geometry",
]
