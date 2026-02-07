"""Rectangle conversion helpers for IR generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.core.styling.style_runtime import extract_style
from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.ir.scene import Path
from svg2ooxml.ir.shapes import Rectangle

if TYPE_CHECKING:  # pragma: no cover - import guard
    from svg2ooxml.core.ir.converter import IRConverter
    from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace


def convert_rect(
    converter: IRConverter,
    element: etree._Element,
    coord_space: CoordinateSpace,
    *,
    tolerance: float,
):
    """Convert <rect> elements into IR rectangles or paths with rounded corners."""

    width = _parse_float(element.get("width"))
    height = _parse_float(element.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        return None

    x = _parse_float(element.get("x"), default=0.0) or 0.0
    y = _parse_float(element.get("y"), default=0.0) or 0.0
    rx_raw = _parse_float(element.get("rx"))
    ry_raw = _parse_float(element.get("ry"))
    rx = rx_raw if rx_raw is not None else 0.0
    ry = ry_raw if ry_raw is not None else 0.0
    if rx <= 0.0 and ry > 0.0:
        rx = ry
    if ry <= 0.0 and rx > 0.0:
        ry = rx
    rx = max(0.0, rx)
    ry = max(0.0, ry)
    radius_x = min(rx, width / 2.0)
    radius_y = min(ry, height / 2.0)
    has_rounding = radius_x > 0.0 and radius_y > 0.0
    uniform_radius = has_rounding and abs(radius_x - radius_y) < tolerance
    corner_radius = radius_x if uniform_radius else 0.0

    style = extract_style(converter, element)
    metadata = dict(style.metadata)
    converter._attach_policy_metadata(metadata, "geometry")
    clip_ref = converter._resolve_clip_ref(element)
    mask_ref, mask_instance = converter._resolve_mask_ref(element)
    matrix = coord_space.current

    if (
        not clip_ref
        and not mask_ref
        and not style.effects
        and is_axis_aligned(matrix, tolerance)
        and (not has_rounding or uniform_radius)
    ):
        bounds = transform_axis_aligned_rect(matrix, x, y, width, height, tolerance)
        if bounds is not None:
            rect = Rectangle(
                bounds=bounds,
                corner_radius=scaled_corner_radius(corner_radius, matrix, tolerance),
                fill=style.fill,
                stroke=style.stroke,
                opacity=style.opacity,
                effects=list(style.effects),
                metadata=metadata,
                element_id=element.get("id"),
            )
            converter._trace_geometry_decision(element, "native", rect.metadata)
            return rect

    if has_rounding:
        segments = _rounded_rect_segments(x, y, width, height, radius_x, radius_y)
    else:
        segments = _rect_segments(x, y, width, height)

    transformed_segments = coord_space.apply_segments(segments)
    path = Path(
        segments=transformed_segments,
        fill=style.fill,
        stroke=style.stroke,
        clip=clip_ref,
        mask=mask_ref,
        mask_instance=mask_instance,
        opacity=style.opacity,
        effects=style.effects,
        metadata=metadata,
    )
    converter._process_mask_metadata(path)
    converter._trace_geometry_decision(element, "native", path.metadata)
    return path


def _parse_float(value: str | None, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return default


def _rect_segments(x: float, y: float, width: float, height: float) -> list[SegmentType]:
    top_left = Point(x, y)
    top_right = Point(x + width, y)
    bottom_right = Point(x + width, y + height)
    bottom_left = Point(x, y + height)
    return [
        LineSegment(top_left, top_right),
        LineSegment(top_right, bottom_right),
        LineSegment(bottom_right, bottom_left),
        LineSegment(bottom_left, top_left),
    ]


def _rounded_rect_segments(
    x: float,
    y: float,
    width: float,
    height: float,
    radius_x: float,
    radius_y: float,
) -> list[SegmentType]:
    max_rx = width / 2.0
    max_ry = height / 2.0
    rx = max(0.0, min(radius_x, max_rx))
    ry = max(0.0, min(radius_y, max_ry))
    if rx <= 0.0 or ry <= 0.0:
        return _rect_segments(x, y, width, height)

    kappa = 0.5522847498307936
    kx = rx * kappa
    ky = ry * kappa

    top_left = Point(x + rx, y)
    top_right = Point(x + width - rx, y)
    right_top = Point(x + width, y + ry)
    right_bottom = Point(x + width, y + height - ry)
    bottom_right = Point(x + width - rx, y + height)
    bottom_left = Point(x + rx, y + height)
    left_bottom = Point(x, y + height - ry)
    left_top = Point(x, y + ry)

    segments: list[SegmentType] = [
        LineSegment(top_left, top_right),
        BezierSegment(
            start=top_right,
            control1=Point(top_right.x + kx, top_right.y),
            control2=Point(right_top.x, right_top.y - ky),
            end=right_top,
        ),
        LineSegment(right_top, right_bottom),
        BezierSegment(
            start=right_bottom,
            control1=Point(right_bottom.x, right_bottom.y + ky),
            control2=Point(bottom_right.x + kx, bottom_right.y),
            end=bottom_right,
        ),
        LineSegment(bottom_right, bottom_left),
        BezierSegment(
            start=bottom_left,
            control1=Point(bottom_left.x - kx, bottom_left.y),
            control2=Point(left_bottom.x, left_bottom.y + ky),
            end=left_bottom,
        ),
        LineSegment(left_bottom, left_top),
        BezierSegment(
            start=left_top,
            control1=Point(left_top.x, left_top.y - ky),
            control2=Point(top_left.x - kx, top_left.y),
            end=top_left,
        ),
    ]
    return segments


__all__ = ["convert_rect"]
