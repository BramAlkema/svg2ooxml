"""Raster tile builder for simple SVG patterns."""

from __future__ import annotations

import math
from collections.abc import Iterator

from lxml import etree as ET

from svg2ooxml.color import parse_color
from svg2ooxml.color.utils import rgb_object_to_hex
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
TileRect = tuple[float, float, float, float, tuple[int, int, int], float]


def build_tile_payload(
    element: ET.Element,
    *,
    analysis: PatternAnalysis,
    phase_x: float = 0.0,
    phase_y: float = 0.0,
) -> tuple[bytes, int, int] | None:
    tile_width = max(analysis.geometry.tile_width, 0.0)
    tile_height = max(analysis.geometry.tile_height, 0.0)
    width_px = max(int(math.ceil(tile_width)), 1)
    height_px = max(int(math.ceil(tile_height)), 1)

    if analysis.pattern_type in {PatternType.GRID, PatternType.CROSS, PatternType.CUSTOM}:
        return _build_rect_tile_payload(
            element,
            tile_width=tile_width,
            tile_height=tile_height,
            width_px=width_px,
            height_px=height_px,
            phase_x=phase_x,
            phase_y=phase_y,
        )

    if analysis.pattern_type != PatternType.DOTS:
        return None
    if analysis.complexity != PatternComplexity.SIMPLE:
        return None
    if analysis.geometry.transform_matrix is None:
        return None
    if not is_translation_only(analysis.geometry.transform_matrix):
        return None

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

    pixels = _phase_shift_pixels(
        pixels,
        width_px=width_px,
        height_px=height_px,
        phase_x=phase_x,
        phase_y=phase_y,
    )
    return encode_rgba_png(pixels, width_px, height_px), width_px, height_px


def _build_rect_tile_payload(
    element: ET.Element,
    *,
    tile_width: float,
    tile_height: float,
    width_px: int,
    height_px: int,
    phase_x: float,
    phase_y: float,
) -> tuple[bytes, int, int] | None:
    rects = list(
        iter_tile_rects(
            element,
            tile_width=tile_width,
            tile_height=tile_height,
        )
    )
    if not rects:
        return None

    pixels = bytearray(width_px * height_px * 4)
    for left, top, right, bottom, color, opacity in rects:
        rasterize_rect(
            pixels,
            width_px=width_px,
            height_px=height_px,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            color=color,
            opacity=opacity,
        )

    pixels = _phase_shift_pixels(
        pixels,
        width_px=width_px,
        height_px=height_px,
        phase_x=phase_x,
        phase_y=phase_y,
    )
    return encode_rgba_png(pixels, width_px, height_px), width_px, height_px


def _phase_shift_pixels(
    pixels: bytearray,
    *,
    width_px: int,
    height_px: int,
    phase_x: float,
    phase_y: float,
) -> bytearray:
    if width_px <= 0 or height_px <= 0:
        return pixels
    shift_x = int(round(phase_x)) % width_px
    shift_y = int(round(phase_y)) % height_px
    if shift_x == 0 and shift_y == 0:
        return pixels

    shifted = bytearray(len(pixels))
    for y in range(height_px):
        src_y = (y + shift_y) % height_px
        for x in range(width_px):
            src_x = (x + shift_x) % width_px
            dst_idx = (y * width_px + x) * 4
            src_idx = (src_y * width_px + src_x) * 4
            shifted[dst_idx : dst_idx + 4] = pixels[src_idx : src_idx + 4]
    return shifted


def iter_tile_rects(
    element: ET.Element,
    *,
    tile_width: float,
    tile_height: float,
) -> Iterator[TileRect]:
    """Yield visible axis-aligned rect geometry for a pattern tile."""

    def _walk(node: ET.Element, transform: Matrix2D) -> Iterator[TileRect]:
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
            if tag != "rect" or _has_visible_stroke(child):
                return
            fill_spec = pattern_fill_spec(child)
            if fill_spec is None:
                continue
            rect = tile_rect_geometry(child, current)
            if rect is None:
                return
            left, top, right, bottom = rect
            if right <= 0.0 or bottom <= 0.0 or left >= tile_width or top >= tile_height:
                continue
            yield left, top, right, bottom, fill_spec[0], fill_spec[1]

    yield from _walk(element, Matrix2D.identity())


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


def _has_visible_stroke(element: ET.Element) -> bool:
    sm = style_map(element)
    stroke = element.get("stroke") or sm.get("stroke")
    if not is_visible_paint_token(stroke):
        return False
    opacity = pattern_opacity(
        sm.get("stroke-opacity") or element.get("stroke-opacity"),
        default=1.0,
    )
    opacity *= pattern_opacity(sm.get("opacity") or element.get("opacity"))
    return opacity > 0.0


def pattern_fill_spec(
    element: ET.Element,
) -> tuple[tuple[int, int, int], float] | None:
    sm = style_map(element)
    fill = element.get("fill") or sm.get("fill")
    if not is_visible_paint_token(fill):
        return None
    color = clean_color(fill)
    color_alpha = 1.0
    if color is None:
        parsed_color = parse_color(fill)
        if parsed_color is None:
            return None
        color = rgb_object_to_hex(parsed_color, default=None)
        if color is None:
            return None
        color_alpha = parsed_color.a
    opacity = pattern_opacity(
        sm.get("fill-opacity") or element.get("fill-opacity"),
        default=1.0,
    )
    opacity *= color_alpha
    opacity *= pattern_opacity(sm.get("opacity") or element.get("opacity"))
    return (
        (
            int(color[0:2], 16),
            int(color[2:4], 16),
            int(color[4:6], 16),
        ),
        max(0.0, min(1.0, opacity)),
    )


def tile_rect_geometry(
    element: ET.Element,
    transform: Matrix2D,
) -> tuple[float, float, float, float] | None:
    if abs(transform.b) > 1e-9 or abs(transform.c) > 1e-9:
        return None
    x = parse_float_attr(element, "x", axis="x", default=0.0)
    y = parse_float_attr(element, "y", axis="y", default=0.0)
    width = parse_float_attr(element, "width", axis="x")
    height = parse_float_attr(element, "height", axis="y")
    if x is None or y is None or width is None or height is None:
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    x1, y1 = transform.transform_xy(x, y)
    x2, y2 = transform.transform_xy(x + width, y + height)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


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


def rasterize_rect(
    pixels: bytearray,
    *,
    width_px: int,
    height_px: int,
    left: float,
    top: float,
    right: float,
    bottom: float,
    color: tuple[int, int, int],
    opacity: float,
) -> None:
    if opacity <= 0.0 or right <= left or bottom <= top:
        return
    min_x = max(int(math.floor(left)), 0)
    max_x = min(int(math.ceil(right)), width_px)
    min_y = max(int(math.floor(top)), 0)
    max_y = min(int(math.ceil(bottom)), height_px)
    if min_x >= max_x or min_y >= max_y:
        return

    sample_offsets = (0.25, 0.75)
    for py in range(min_y, max_y):
        for px in range(min_x, max_x):
            coverage = 0
            for sy in sample_offsets:
                for sx in sample_offsets:
                    sample_x = px + sx
                    sample_y = py + sy
                    if left <= sample_x < right and top <= sample_y < bottom:
                        coverage += 1
            if coverage == 0:
                continue
            composite_rgba_pixel(
                pixels,
                width_px=width_px,
                x=px,
                y=py,
                color=color,
                alpha=opacity * (coverage / 4.0),
            )


__all__ = [
    "build_tile_payload",
    "composite_rgba_pixel",
    "encode_rgba_png",
    "iter_tile_ellipses",
    "iter_tile_rects",
    "path_ellipse_geometry",
    "pattern_fill_spec",
    "rasterize_ellipse",
    "rasterize_rect",
    "tile_ellipse_geometry",
    "tile_rect_geometry",
]
