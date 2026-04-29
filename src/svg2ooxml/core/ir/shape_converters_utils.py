"""Shared shape converter utilities."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.points import parse_point_pairs
from svg2ooxml.common.geometry.segments import (
    ellipse_segments,
    line_segments_from_points,
)
from svg2ooxml.common.math_utils import clamp01
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name as _local_name
from svg2ooxml.common.svg_refs import namespace_uri
from svg2ooxml.common.units.lengths import resolve_length_px_required
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType


def _clamp01(value: float) -> float:
    return clamp01(value)


def _resolve_svg_length(
    unit_converter,
    value: str | None,
    context,
    *,
    axis: str,
    default: float | None = None,
) -> float | None:
    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        return float(
            resolve_length_px_required(
                token,
                context,
                axis=axis,
                unit_converter=unit_converter,
            )
        )
    except Exception:
        return default


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    return ellipse_segments(cx, cy, rx, ry)


def _points_to_segments(points: Sequence[Point], *, closed: bool) -> list[SegmentType]:
    segments: list[SegmentType] = list(line_segments_from_points(points))
    if closed and points:
        segments.append(LineSegment(points[-1], points[0]))
    return segments


def _segments_to_points(segments: Sequence[SegmentType], *, closed: bool) -> list[Point]:
    if not segments:
        return []
    points: list[Point] = []
    first = getattr(segments[0], "start", None)
    if isinstance(first, Point):
        points.append(first)
    for segment in segments:
        end = getattr(segment, "end", None)
        if isinstance(end, Point):
            points.append(end)
    if closed and len(points) > 1:
        if _points_close(points[0], points[-1]):
            points.pop()
    return points


def _parse_points(value: str | None) -> list[Point]:
    return [Point(x, y) for x, y in parse_point_pairs(value)]


def _has_markers(element: etree._Element) -> bool:
    for attr in ("marker-start", "marker-mid", "marker-end"):
        if element.get(attr):
            return True
    style_attr = element.get("style")
    if not style_attr:
        return False
    for name, value in parse_style_declarations(style_attr)[0].items():
        if name in {"marker-start", "marker-mid", "marker-end"} and value:
            return True
    return False


def _points_close(a: Point, b: Point, tolerance: float = DEFAULT_TOLERANCE) -> bool:
    return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance


def _compute_bbox(points: Iterable[tuple[float, float]]) -> Rect:
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _guess_image_format(href: str | None, data: bytes | None, mime: str | None) -> str:
    if mime:
        if "png" in mime:
            return "png"
        if "jpeg" in mime or "jpg" in mime:
            return "jpg"
        if "gif" in mime:
            return "gif"
        if "svg" in mime:
            return "svg"
    if href:
        lower = href.lower()
        for suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            if lower.endswith(suffix):
                return suffix.strip(".")
    return "png"


def _foreign_object_clip_id(element: etree._Element, bbox: Rect) -> str:
    element_id = element.get("id")
    if element_id:
        return f"foreignObject:{element_id}"
    return f"foreignObject:{bbox.x:.4f},{bbox.y:.4f},{bbox.width:.4f},{bbox.height:.4f}"


def _first_foreign_child(element: etree._Element) -> etree._Element | None:
    for child in element:
        if isinstance(child.tag, str):
            return child
    return None


def _classify_foreign_payload(payload: etree._Element | None) -> str:
    if payload is None:
        return "empty"
    tag = _local_name(payload.tag).lower()
    namespace = namespace_uri(payload.tag) or ""

    if tag == "svg":
        return "nested_svg"

    if tag in {"img", "image", "object", "picture"}:
        if _extract_image_href(payload):
            return "image"

    xhtml_tags = {
        "p",
        "div",
        "span",
        "table",
        "tbody",
        "tr",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "a",
        "em",
        "strong",
        "b",
        "i",
        "u",
        "br",
        "hr",
        "pre",
        "code",
        "blockquote",
    }
    if tag in xhtml_tags or "xhtml" in namespace.lower() or "html" in namespace.lower():
        return "xhtml"

    return "unknown"


def _extract_image_href(element: etree._Element) -> str | None:
    return (
        element.get("src")
        or element.get("href")
        or element.get("xlink:href")
        or element.get("{http://www.w3.org/1999/xlink}href")
    )


def _collect_foreign_text(element: etree._Element) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        child_text = _collect_foreign_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(part for part in parts if part)


def _rect_segments_from_bbox(bbox: Rect) -> list[SegmentType]:
    points = [
        Point(bbox.x, bbox.y),
        Point(bbox.x + bbox.width, bbox.y),
        Point(bbox.x + bbox.width, bbox.y + bbox.height),
        Point(bbox.x, bbox.y + bbox.height),
    ]
    return _points_to_segments(points, closed=True)


def _uniform_scale(matrix: Matrix2D, tolerance: float) -> float | None:
    scale_x = (matrix.a**2 + matrix.b**2) ** 0.5
    scale_y = (matrix.c**2 + matrix.d**2) ** 0.5
    if scale_x <= tolerance or scale_y <= tolerance:
        return None
    if abs(scale_x - scale_y) > tolerance:
        return None
    if abs(matrix.a * matrix.c + matrix.b * matrix.d) > tolerance:
        return None
    return scale_x


def _bezier_point(segment: BezierSegment, t: float) -> Point:
    inv_t = 1 - t
    x = (
        inv_t ** 3 * segment.start.x
        + 3 * inv_t ** 2 * t * segment.control1.x
        + 3 * inv_t * t ** 2 * segment.control2.x
        + t ** 3 * segment.end.x
    )
    y = (
        inv_t ** 3 * segment.start.y
        + 3 * inv_t ** 2 * t * segment.control1.y
        + 3 * inv_t * t ** 2 * segment.control2.y
        + t ** 3 * segment.end.y
    )
    return x, y
