"""Path utilities for EMF emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


@dataclass(slots=True, frozen=True)
class DashPattern:
    """Normalised dash pattern expressed in EMUs."""

    pattern: Tuple[float, ...]
    offset: float = 0.0

    def is_solid(self) -> bool:
        return not self.pattern or all(value <= 0 for value in self.pattern)


def flatten_segments(
    segments: Sequence[SegmentType],
    *,
    tolerance: float = 0.5,
) -> List[Tuple[float, float]]:
    """Return a polyline approximation of the supplied segments."""

    if not segments:
        return []
    points: List[Tuple[float, float]] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            if not points:
                points.append((segment.start.x, segment.start.y))
            points.append((segment.end.x, segment.end.y))
        elif isinstance(segment, BezierSegment):
            if not points:
                points.append((segment.start.x, segment.start.y))
            _flatten_bezier(segment, tolerance, points)
        else:  # pragma: no cover - defensive fall-back
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            if start is not None:
                if not points:
                    points.append((start.x, start.y))
            if end is not None:
                points.append((end.x, end.y))
    return points


def apply_dash_pattern(
    points: Sequence[Tuple[float, float]],
    pattern: DashPattern | None,
) -> List[List[Tuple[float, float]]]:
    """Break a polyline into dash segments."""

    if not points or len(points) < 2:
        return []
    if pattern is None or pattern.is_solid():
        return [list(points)]

    segments: List[List[Tuple[float, float]]] = []
    pattern_values = [abs(value) for value in pattern.pattern if value > 0]
    if not pattern_values:
        return [list(points)]

    pattern_length = sum(pattern_values)
    dash_index = 0
    dash_remaining = pattern_values[dash_index]
    offset = pattern.offset % pattern_length
    while offset > 0:
        if offset < dash_remaining:
            dash_remaining -= offset
            offset = 0
        else:
            offset -= dash_remaining
            dash_index = (dash_index + 1) % len(pattern_values)
            dash_remaining = pattern_values[dash_index]

    drawing = bool(dash_index % 2 == 0)
    current_segment: List[Tuple[float, float]] = []

    for start, end in zip(points[:-1], points[1:]):
        sx, sy = start
        ex, ey = end
        dx = ex - sx
        dy = ey - sy
        segment_length = (dx * dx + dy * dy) ** 0.5
        if segment_length == 0:
            continue

        consumed = 0.0
        while consumed < segment_length:
            step = min(dash_remaining, segment_length - consumed)
            t = step / segment_length
            ix = sx + dx * ((consumed + step) / segment_length)
            iy = sy + dy * ((consumed + step) / segment_length)

            if drawing:
                if not current_segment:
                    current_segment.append((sx + dx * (consumed / segment_length), sy + dy * (consumed / segment_length)))
                current_segment.append((ix, iy))

            consumed += step
            dash_remaining -= step

            if dash_remaining <= 1e-6:
                if drawing and current_segment:
                    segments.append(current_segment)
                    current_segment = []

                dash_index = (dash_index + 1) % len(pattern_values)
                dash_remaining = pattern_values[dash_index]
                drawing = dash_index % 2 == 0

        sx, sy = ex, ey

    if drawing and current_segment:
        segments.append(current_segment)

    return [segment for segment in segments if len(segment) > 1]


def _flatten_bezier(segment: BezierSegment, tolerance: float, points: List[Tuple[float, float]]) -> None:
    stack: List[Tuple[BezierSegment, int]] = [(segment, 0)]
    while stack:
        current, depth = stack.pop()
        if _bezier_is_flat(current, tolerance) or depth > 12:
            points.append((current.end.x, current.end.y))
            continue
        left, right = _split_bezier(current)
        stack.append((right, depth + 1))
        stack.append((left, depth + 1))


def _bezier_is_flat(segment: BezierSegment, tolerance: float) -> bool:
    def distance(point: Point, line_start: Point, line_end: Point) -> float:
        num = abs(
            (line_end.x - line_start.x) * (line_start.y - point.y)
            - (line_start.x - point.x) * (line_end.y - line_start.y)
        )
        den = ((line_end.x - line_start.x) ** 2 + (line_end.y - line_start.y) ** 2) ** 0.5
        return num / den if den else 0.0

    d1 = distance(segment.control1, segment.start, segment.end)
    d2 = distance(segment.control2, segment.start, segment.end)
    return max(d1, d2) <= tolerance


def _split_bezier(segment: BezierSegment) -> Tuple[BezierSegment, BezierSegment]:
    p0 = segment.start
    p1 = segment.control1
    p2 = segment.control2
    p3 = segment.end

    m1 = Point((p0.x + p1.x) * 0.5, (p0.y + p1.y) * 0.5)
    m2 = Point((p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5)
    m3 = Point((p2.x + p3.x) * 0.5, (p2.y + p3.y) * 0.5)
    m4 = Point((m1.x + m2.x) * 0.5, (m1.y + m2.y) * 0.5)
    m5 = Point((m2.x + m3.x) * 0.5, (m2.y + m3.y) * 0.5)
    center = Point((m4.x + m5.x) * 0.5, (m4.y + m5.y) * 0.5)

    left = BezierSegment(start=p0, control1=m1, control2=m4, end=center)
    right = BezierSegment(start=center, control1=m5, control2=m3, end=p3)
    return left, right
