"""Detect if a path matches a DrawingML preset shape.

Candidates: rect, roundRect, ellipse.
Only single-subpath closed paths are eligible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from svg2ooxml.common.geometry.points import point_distance
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType

DEFAULT_TOLERANCE = 2.0  # px — intentionally loose for shape recognition

_KAPPA = 0.5522847498

PresetName = Literal["rect", "roundRect", "ellipse"]


@dataclass(frozen=True)
class PresetShapeMatch:
    """Result of preset shape detection."""

    preset: PresetName
    bounds: Rect
    corner_radius: float = 0.0
    confidence: float = 1.0


def detect_preset_shape(
    segments: list[SegmentType],
    tolerance: float = DEFAULT_TOLERANCE,
) -> PresetShapeMatch | None:
    """Try to match *segments* against known preset shapes.

    Returns a ``PresetShapeMatch`` or ``None``.
    """
    if not segments:
        return None

    # Must be a closed path (last end ≈ first start)
    first_start = segments[0].start
    last_end = segments[-1].end
    if _dist(first_start, last_end) > tolerance:
        return None

    n = len(segments)

    # Quick reject by segment count
    if n == 4:
        if all(isinstance(s, LineSegment) for s in segments):
            return _detect_rect(segments, tolerance)
        if all(isinstance(s, BezierSegment) for s in segments):
            return _detect_ellipse(segments, tolerance)
    elif n == 8:
        return _detect_round_rect(segments, tolerance)

    return None


# ---------------------------------------------------------------------------
# Rectangle detection
# ---------------------------------------------------------------------------


def _detect_rect(
    segments: list[LineSegment],
    tolerance: float,
) -> PresetShapeMatch | None:
    """4 axis-aligned perpendicular line segments → rect."""
    for seg in segments:
        if not _is_axis_aligned(seg, tolerance):
            return None

    # Check perpendicularity between consecutive segments
    for i in range(4):
        s1 = segments[i]
        s2 = segments[(i + 1) % 4]
        if not _is_perpendicular(s1, s2, tolerance):
            return None

    bounds = _bounds_from_segments(segments)
    return PresetShapeMatch(preset="rect", bounds=bounds, confidence=1.0)


def _is_axis_aligned(seg: LineSegment, tolerance: float) -> bool:
    dx = abs(seg.end.x - seg.start.x)
    dy = abs(seg.end.y - seg.start.y)
    return dx < tolerance or dy < tolerance


def _is_perpendicular(a: LineSegment, b: LineSegment, tolerance: float) -> bool:
    dx1, dy1 = a.end.x - a.start.x, a.end.y - a.start.y
    dx2, dy2 = b.end.x - b.start.x, b.end.y - b.start.y
    dot = dx1 * dx2 + dy1 * dy2
    len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
    len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
    if len1 < 1e-9 or len2 < 1e-9:
        return False
    cos_angle = abs(dot / (len1 * len2))
    return cos_angle < math.sin(math.radians(5))  # within 5° of perpendicular


# ---------------------------------------------------------------------------
# Rounded rectangle detection
# ---------------------------------------------------------------------------


def _detect_round_rect(
    segments: list[SegmentType],
    tolerance: float,
) -> PresetShapeMatch | None:
    """4 lines alternating with 4 beziers → roundRect."""
    # Expect alternating pattern: line, bezier, line, bezier, ...
    # or: bezier, line, bezier, line, ...
    lines: list[LineSegment] = []
    curves: list[BezierSegment] = []

    for seg in segments:
        if isinstance(seg, LineSegment):
            lines.append(seg)
        elif isinstance(seg, BezierSegment):
            curves.append(seg)
        else:
            return None

    if len(lines) != 4 or len(curves) != 4:
        return None

    # All lines must be axis-aligned
    for seg in lines:
        if not _is_axis_aligned(seg, tolerance):
            return None

    # All curves should approximate quarter-circles with similar radii
    radii: list[float] = []
    for curve in curves:
        r = _quarter_circle_radius(curve, tolerance)
        if r is None:
            return None
        radii.append(r)

    # All radii should be approximately equal
    avg_radius = sum(radii) / len(radii)
    for r in radii:
        if abs(r - avg_radius) > tolerance:
            return None

    bounds = _bounds_from_segments(segments)
    return PresetShapeMatch(
        preset="roundRect",
        bounds=bounds,
        corner_radius=avg_radius,
        confidence=min(
            1.0, 1.0 - max(abs(r - avg_radius) for r in radii) / (avg_radius + 1e-9)
        ),
    )


def _quarter_circle_radius(curve: BezierSegment, tolerance: float) -> float | None:
    """Check if a bezier approximates a quarter-circle. Return radius or None."""
    # A quarter-circle bezier has:
    # - chord length = radius * sqrt(2)
    # - control points at kappa * radius from the arc endpoints
    chord = _dist(curve.start, curve.end)
    if chord < 1e-9:
        return None

    # Approximate radius from chord: r = chord / sqrt(2)
    r = chord / math.sqrt(2)

    # Check control point distances from their respective endpoints
    d1 = _dist(curve.start, curve.control1)
    d2 = _dist(curve.end, curve.control2)
    expected = r * _KAPPA

    if abs(d1 - expected) > tolerance or abs(d2 - expected) > tolerance:
        return None

    return r


# ---------------------------------------------------------------------------
# Ellipse detection
# ---------------------------------------------------------------------------


def _detect_ellipse(
    segments: list[BezierSegment],
    tolerance: float,
) -> PresetShapeMatch | None:
    """4 cubic beziers forming a closed loop → ellipse."""
    # Compute bounding box center
    all_points = []
    for seg in segments:
        all_points.extend([seg.start, seg.end, seg.control1, seg.control2])
    min_x = min(p.x for p in all_points)
    max_x = max(p.x for p in all_points)
    min_y = min(p.y for p in all_points)
    max_y = max(p.y for p in all_points)

    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    rx = (max_x - min_x) / 2
    ry = (max_y - min_y) / 2

    if rx < 1e-9 or ry < 1e-9:
        return None

    # Verify each bezier approximates a quarter-ellipse
    # The 4 cardinal points should be at (cx±rx, cy) and (cx, cy±ry)
    cardinal_points = [
        Point(cx + rx, cy),  # right
        Point(cx, cy + ry),  # bottom
        Point(cx - rx, cy),  # left
        Point(cx, cy - ry),  # top
    ]

    # Check that start/end points match cardinal points (in some rotation)
    seg_endpoints = [seg.start for seg in segments]
    matched = _match_cardinal_points(seg_endpoints, cardinal_points, tolerance)
    if not matched:
        return None

    # Verify control points match kappa approximation
    kx = _KAPPA * rx
    ky = _KAPPA * ry

    total_error = 0.0
    for seg in segments:
        # Find which quadrant this segment covers
        err = _ellipse_quadrant_error(seg, cx, cy, rx, ry, kx, ky, tolerance)
        if err is None:
            return None
        total_error += err

    avg_error = total_error / 4
    confidence = max(0.0, 1.0 - avg_error / tolerance)

    bounds = Rect(cx - rx, cy - ry, 2 * rx, 2 * ry)
    return PresetShapeMatch(preset="ellipse", bounds=bounds, confidence=confidence)


def _match_cardinal_points(
    seg_points: list[Point],
    cardinal: list[Point],
    tolerance: float,
) -> bool:
    """Check that segment start points match cardinal points in some rotation."""
    for offset in range(4):
        all_match = True
        for i in range(4):
            ci = (i + offset) % 4
            if _dist(seg_points[i], cardinal[ci]) > tolerance:
                all_match = False
                break
        if all_match:
            return True
    return False


def _ellipse_quadrant_error(
    seg: BezierSegment,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    kx: float,
    ky: float,
    tolerance: float,
) -> float | None:
    """Check how well a bezier matches one quadrant of an ellipse.

    Returns average control point error, or None if way off.
    """
    # Expected control points for each quadrant
    # right→bottom: c1=(rx, ky), c2=(kx, ry)
    # bottom→left:  c1=(-kx, ry), c2=(-rx, ky)
    # left→top:     c1=(-rx, -ky), c2=(-kx, -ry)
    # top→right:    c1=(kx, -ry), c2=(rx, -ky)
    quadrants = [
        ((rx, ky), (kx, ry)),
        ((-kx, ry), (-rx, ky)),
        ((-rx, -ky), (-kx, -ry)),
        ((kx, -ry), (rx, -ky)),
    ]

    best_error = float("inf")
    for (ec1x, ec1y), (ec2x, ec2y) in quadrants:
        c1_err = _dist(seg.control1, Point(cx + ec1x, cy + ec1y))
        c2_err = _dist(seg.control2, Point(cx + ec2x, cy + ec2y))
        err = (c1_err + c2_err) / 2
        if err < best_error:
            best_error = err

    if best_error > tolerance * 2:
        return None
    return best_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dist(a: Point, b: Point) -> float:
    return point_distance(a, b)


def _bounds_from_segments(segments: list[SegmentType]) -> Rect:
    all_x: list[float] = []
    all_y: list[float] = []
    for seg in segments:
        all_x.extend([seg.start.x, seg.end.x])
        all_y.extend([seg.start.y, seg.end.y])
        if isinstance(seg, BezierSegment):
            all_x.extend([seg.control1.x, seg.control2.x])
            all_y.extend([seg.control1.y, seg.control2.y])
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


__all__ = ["PresetShapeMatch", "detect_preset_shape"]
