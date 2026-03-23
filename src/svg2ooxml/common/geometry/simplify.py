"""Path simplification passes for reducing segment counts.

Operates on IR segment types (LineSegment, BezierSegment) and preserves
subpath boundaries.  Each pass is a pure function: list[SegmentType] → list[SegmentType].

See docs/specs/path-simplification.md for the full specification.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


# ---------------------------------------------------------------------------
# Tolerances (in SVG user-space pixels)
# ---------------------------------------------------------------------------

DEFAULT_EPSILON = 0.01  # degenerate segment threshold
DEFAULT_BEZIER_FLATNESS = 0.5  # control-point deviation for bezier demotion
DEFAULT_COLLINEAR_ANGLE = 0.5  # degrees
DEFAULT_RDP_TOLERANCE = 1.0  # Ramer-Douglas-Peucker tolerance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def simplify_segments(
    segments: Sequence[SegmentType],
    *,
    epsilon: float = DEFAULT_EPSILON,
    bezier_flatness: float = DEFAULT_BEZIER_FLATNESS,
    collinear_angle_deg: float = DEFAULT_COLLINEAR_ANGLE,
    rdp_tolerance: float = DEFAULT_RDP_TOLERANCE,
) -> list[SegmentType]:
    """Run simplification passes on *segments*, preserving subpath boundaries.

    Returns the simplified segment list.
    """
    subpaths = _split_subpaths(list(segments))
    result: list[SegmentType] = []
    for sp in subpaths:
        sp = _remove_degenerates(sp, epsilon)
        sp = _demote_flat_beziers(sp, bezier_flatness)
        sp = _merge_collinear(sp, collinear_angle_deg, epsilon)
        if rdp_tolerance > 0:
            sp = _rdp_simplify(sp, rdp_tolerance, epsilon)
        result.extend(sp)
    return result


# ---------------------------------------------------------------------------
# Pass 1: Degenerate segment removal
# ---------------------------------------------------------------------------


def _remove_degenerates(
    segments: list[SegmentType],
    epsilon: float,
) -> list[SegmentType]:
    """Remove segments whose start ≈ end (within *epsilon*)."""
    kept: list[SegmentType] = []
    for seg in segments:
        if isinstance(seg, LineSegment):
            if _dist(seg.start, seg.end) < epsilon:
                continue
        elif isinstance(seg, BezierSegment):
            if (
                _dist(seg.start, seg.end) < epsilon
                and _dist(seg.start, seg.control1) < epsilon
                and _dist(seg.start, seg.control2) < epsilon
            ):
                continue
        kept.append(seg)
    # Never empty a subpath entirely
    if not kept and segments:
        kept.append(segments[-1])
    return kept


# ---------------------------------------------------------------------------
# Pass 2: Bezier-to-line demotion
# ---------------------------------------------------------------------------


def _demote_flat_beziers(
    segments: list[SegmentType],
    flatness: float,
) -> list[SegmentType]:
    """Replace BezierSegments whose control points lie close to the chord."""
    result: list[SegmentType] = []
    for seg in segments:
        if isinstance(seg, BezierSegment):
            chord_len = _dist(seg.start, seg.end)
            if chord_len < 1e-9:
                # Degenerate chord — check control-point spread instead
                d1 = _dist(seg.start, seg.control1)
                d2 = _dist(seg.start, seg.control2)
                if d1 < flatness and d2 < flatness:
                    result.append(LineSegment(seg.start, seg.end))
                    continue
            else:
                d1 = _point_to_line_dist(seg.control1, seg.start, seg.end)
                d2 = _point_to_line_dist(seg.control2, seg.start, seg.end)
                if d1 < flatness and d2 < flatness:
                    result.append(LineSegment(seg.start, seg.end))
                    continue
        result.append(seg)
    return result


# ---------------------------------------------------------------------------
# Pass 3: Collinear line merge
# ---------------------------------------------------------------------------


def _merge_collinear(
    segments: list[SegmentType],
    angle_deg: float,
    epsilon: float,
) -> list[SegmentType]:
    """Merge consecutive LineSegments with the same direction."""
    if not segments:
        return segments
    angle_rad = math.radians(angle_deg)
    result: list[SegmentType] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if not isinstance(seg, LineSegment):
            result.append(seg)
            i += 1
            continue
        # Accumulate collinear run
        run_start = seg.start
        run_end = seg.end
        j = i + 1
        while j < len(segments):
            nxt = segments[j]
            if not isinstance(nxt, LineSegment):
                break
            # Check continuity
            if _dist(run_end, nxt.start) > epsilon:
                break
            # Check collinearity
            if not _collinear(run_start, run_end, nxt.end, angle_rad):
                break
            run_end = nxt.end
            j += 1
        result.append(LineSegment(run_start, run_end))
        i = j
    return result


# ---------------------------------------------------------------------------
# Pass 4: Ramer-Douglas-Peucker
# ---------------------------------------------------------------------------


def _rdp_simplify(
    segments: list[SegmentType],
    tolerance: float,
    epsilon: float,
) -> list[SegmentType]:
    """Apply RDP to maximal runs of consecutive LineSegments."""
    if len(segments) < 3:
        return segments

    result: list[SegmentType] = []
    run: list[LineSegment] = []

    def _flush_run() -> None:
        if not run:
            return
        if len(run) < 3:
            result.extend(run)
            run.clear()
            return
        # Build point sequence from line run
        points = [run[0].start] + [seg.end for seg in run]
        simplified = _rdp_points(points, tolerance)
        for i in range(len(simplified) - 1):
            result.append(LineSegment(simplified[i], simplified[i + 1]))
        run.clear()

    for seg in segments:
        if isinstance(seg, LineSegment):
            if run and _dist(run[-1].end, seg.start) > epsilon:
                _flush_run()
            run.append(seg)
        else:
            _flush_run()
            result.append(seg)

    _flush_run()
    return result


def _rdp_points(points: list[Point], tolerance: float) -> list[Point]:
    """Ramer-Douglas-Peucker on a point sequence. Returns simplified points."""
    if len(points) <= 2:
        return points

    # Find the point with maximum distance from the line start→end
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(points) - 1):
        d = _point_to_line_dist(points[i], points[0], points[-1])
        if d > max_dist:
            max_dist = d
            max_idx = i

    if max_dist > tolerance:
        left = _rdp_points(points[: max_idx + 1], tolerance)
        right = _rdp_points(points[max_idx:], tolerance)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]


# ---------------------------------------------------------------------------
# Subpath splitting (mirrors drawingml._split_subpaths)
# ---------------------------------------------------------------------------

_SUBPATH_EPSILON = 1e-4


def _split_subpaths(segments: list[SegmentType]) -> list[list[SegmentType]]:
    """Split segment list into subpaths at discontinuities."""
    subpaths: list[list[SegmentType]] = []
    current: list[SegmentType] = []
    prev_end: Point | None = None

    for seg in segments:
        start = seg.start
        if prev_end is not None and _dist(prev_end, start) > _SUBPATH_EPSILON:
            if current:
                subpaths.append(current)
                current = []
        current.append(seg)
        prev_end = seg.end

    if current:
        subpaths.append(current)
    return subpaths


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _dist(a: Point, b: Point) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return math.sqrt(dx * dx + dy * dy)


def _point_to_line_dist(p: Point, a: Point, b: Point) -> float:
    """Perpendicular distance from *p* to line through *a* and *b*."""
    dx = b.x - a.x
    dy = b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-18:
        return _dist(p, a)
    # Project p onto line a→b, compute perpendicular distance
    num = abs(dy * p.x - dx * p.y + b.x * a.y - b.y * a.x)
    return num / math.sqrt(length_sq)


def _collinear(start: Point, mid: Point, end: Point, angle_rad: float) -> bool:
    """True if the direction from start→mid and start→end differ by < angle_rad."""
    dx1 = mid.x - start.x
    dy1 = mid.y - start.y
    dx2 = end.x - start.x
    dy2 = end.y - start.y
    len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
    len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
    if len1 < 1e-9 or len2 < 1e-9:
        return True
    cos_angle = (dx1 * dx2 + dy1 * dy2) / (len1 * len2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.acos(cos_angle) < angle_rad


__all__ = ["simplify_segments"]
