"""Geometry helpers for marker realization."""

from __future__ import annotations

import math

from lxml import etree

from svg2ooxml.common.geometry.paths import parse_path_data
from svg2ooxml.common.geometry.points import parse_point_pairs
from svg2ooxml.common.geometry.segments import (
    ellipse_segments as _ellipse_segments_common,
)
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


def marker_segments_for_element(element: etree._Element, local_name: str) -> list[SegmentType]:
    if local_name == "path":
        d_attr = element.get("d")
        if not d_attr:
            return []
        return list(parse_path_data(d_attr))

    if local_name == "line":
        x1 = _marker_length(element.get("x1"), axis="x")
        y1 = _marker_length(element.get("y1"), axis="y")
        x2 = _marker_length(element.get("x2"), axis="x")
        y2 = _marker_length(element.get("y2"), axis="y")
        return [LineSegment(Point(x1, y1), Point(x2, y2))]

    if local_name == "polyline" or local_name == "polygon":
        points = [Point(x, y) for x, y in parse_point_pairs(element.get("points"))]
        if local_name == "polygon" and points:
            points.append(points[0])
        segments: list[SegmentType] = []
        for start, end in zip(points[:-1], points[1:], strict=True):
            segments.append(LineSegment(start, end))
        return segments

    if local_name == "circle":
        cx = _marker_length(element.get("cx"), axis="x")
        cy = _marker_length(element.get("cy"), axis="y")
        r = _marker_length(element.get("r"), axis="x")
        if r <= 0:
            return []
        return _circle_segments(cx, cy, r)

    if local_name == "ellipse":
        cx = _marker_length(element.get("cx"), axis="x")
        cy = _marker_length(element.get("cy"), axis="y")
        rx = _marker_length(element.get("rx"), axis="x")
        ry = _marker_length(element.get("ry"), axis="y")
        if rx <= 0 or ry <= 0:
            return []
        return _ellipse_segments(cx, cy, rx, ry)

    if local_name == "rect":
        x = _marker_length(element.get("x"), axis="x")
        y = _marker_length(element.get("y"), axis="y")
        width = _marker_length(element.get("width"), axis="x")
        height = _marker_length(element.get("height"), axis="y")
        if width <= 0 or height <= 0:
            return []
        return [
            LineSegment(Point(x, y), Point(x + width, y)),
            LineSegment(Point(x + width, y), Point(x + width, y + height)),
            LineSegment(Point(x + width, y + height), Point(x, y + height)),
            LineSegment(Point(x, y + height), Point(x, y)),
        ]

    return []


def _marker_length(value: str | None, *, axis: str, default: float = 0.0) -> float:
    return resolve_length_px(value, None, axis=axis, default=default)


def compute_marker_anchor(
    segments: list[SegmentType],
    *,
    position: str,
    tolerance: float,
) -> tuple[Point, float] | None:
    if not segments:
        return None

    if position == "start":
        segment = segments[0]
        angle = _segment_angle(segment, forward=True, tolerance=tolerance)
        return segment.start, angle
    if position == "end":
        segment = segments[-1]
        angle = _segment_angle(segment, forward=False, tolerance=tolerance)
        return segment.end, angle
    return None


def compute_mid_markers(
    segments: list[SegmentType],
    *,
    tolerance: float,
) -> list[tuple[Point, float]]:
    anchors: list[tuple[Point, float]] = []
    if len(segments) < 2:
        return anchors
    for first, second in zip(segments[:-1], segments[1:], strict=True):
        join_point = first.end
        angle_in = _segment_angle(first, forward=False, tolerance=tolerance)
        angle_out = _segment_angle(second, forward=True, tolerance=tolerance)
        angle = (angle_in + angle_out) / 2.0
        anchors.append((join_point, angle))
    return anchors


def expand_marker_use(converter, element: etree._Element) -> list[etree._Element]:
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
    ref_id = local_url_id(href)
    if ref_id is None:
        return []
    referenced = converter._element_index.get(ref_id)
    if referenced is None:
        return []
    return [converter._clone_element(referenced)]


def _circle_segments(cx: float, cy: float, r: float) -> list[SegmentType]:
    return _ellipse_segments_common(cx, cy, r, r)


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    return _ellipse_segments_common(cx, cy, rx, ry)


def _segment_angle(segment: SegmentType, *, forward: bool, tolerance: float) -> float:
    points = _segment_points(segment)
    if len(points) < 2:
        return 0.0
    if forward:
        start, end = points[0], points[-1]
    else:
        start, end = points[-1], points[0]
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) < tolerance and abs(dy) < tolerance:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def _segment_points(segment: SegmentType) -> list[Point]:
    if isinstance(segment, LineSegment):
        return [segment.start, segment.end]
    if isinstance(segment, BezierSegment):
        return [segment.start, segment.control1, segment.control2, segment.end]
    return []
