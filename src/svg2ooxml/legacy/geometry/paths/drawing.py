"""Utilities for tessellating SVG paths into segments."""

from __future__ import annotations

from math import cos, sin
from typing import Iterable, Sequence

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


def approximate_circle(cx: float, cy: float, radius: float) -> list[SegmentType]:
    if radius <= 0:
        return []
    return approximate_ellipse(cx, cy, radius, radius)


def approximate_ellipse(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    if rx <= 0 or ry <= 0:
        return []

    segments: list[SegmentType] = []
    steps = 8
    theta = (2.0 * 3.141592653589793) / steps
    kappa = 0.5522847498307936

    points = [
        Point(cx + rx, cy),
        Point(cx, cy + ry),
        Point(cx - rx, cy),
        Point(cx, cy - ry),
    ]
    controls = [
        (
            Point(cx + rx, cy + ry * kappa),
            Point(cx + rx * kappa, cy + ry),
        ),
        (
            Point(cx - rx * kappa, cy + ry),
            Point(cx - rx, cy + ry * kappa),
        ),
        (
            Point(cx - rx, cy - ry * kappa),
            Point(cx - rx * kappa, cy - ry),
        ),
        (
            Point(cx + rx * kappa, cy - ry),
            Point(cx + rx, cy - ry * kappa),
        ),
    ]

    for i in range(4):
        start = points[i]
        end = points[(i + 1) % 4]
        control1, control2 = controls[i]
        segments.append(BezierSegment(start, control1, control2, end))
    return segments


def to_line_segments(points: Iterable[Point]) -> list[LineSegment]:
    points = list(points)
    segments: list[LineSegment] = []
    for i in range(len(points) - 1):
        segments.append(LineSegment(points[i], points[i + 1]))
    if points:
        segments.append(LineSegment(points[-1], points[0]))
    return segments


__all__ = ["approximate_circle", "approximate_ellipse", "to_line_segments"]
