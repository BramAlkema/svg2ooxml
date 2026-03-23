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
DEFAULT_CURVE_FIT_TOLERANCE = 1.5  # curve fitting max error
DEFAULT_CURVE_FIT_MIN_POINTS = 8  # min run length to attempt fitting


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
    curve_fit_tolerance: float = DEFAULT_CURVE_FIT_TOLERANCE,
    curve_fit_min_points: int = DEFAULT_CURVE_FIT_MIN_POINTS,
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
        if curve_fit_tolerance > 0 and curve_fit_min_points > 0:
            sp = _curve_fit(sp, curve_fit_tolerance, curve_fit_min_points, epsilon)
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
# Pass 5: Curve fitting (Schneider algorithm)
# ---------------------------------------------------------------------------


def _curve_fit(
    segments: list[SegmentType],
    tolerance: float,
    min_points: int,
    epsilon: float,
) -> list[SegmentType]:
    """Re-fit long runs of LineSegments into fewer BezierSegments."""
    result: list[SegmentType] = []
    run: list[LineSegment] = []

    def _flush_run() -> None:
        if not run:
            return
        points = [run[0].start] + [seg.end for seg in run]
        if len(points) < min_points:
            result.extend(run)
            run.clear()
            return
        fitted = _fit_cubic_beziers(points, tolerance)
        # Quality gate: each bezier costs ~3 XML nodes vs 1 for a line,
        # so only use fitted result if it reduces total XML weight.
        fitted_weight = sum(3 if isinstance(s, BezierSegment) else 1 for s in fitted)
        original_weight = len(run)  # all lines, 1 node each
        if fitted_weight < original_weight:
            result.extend(fitted)
        else:
            result.extend(run)
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


def _fit_cubic_beziers(
    points: list[Point],
    tolerance: float,
) -> list[BezierSegment]:
    """Fit cubic bezier curves to a point sequence (Schneider algorithm).

    Returns a list of BezierSegments that approximate the point sequence
    within *tolerance*.
    """
    if len(points) < 2:
        return []
    if len(points) == 2:
        return []  # single line — not worth fitting

    # Compute left/right tangent at endpoints
    left_tan = _normalize(_sub(points[1], points[0]))
    right_tan = _normalize(_sub(points[-2], points[-1]))

    return _fit_cubic_recursive(points, left_tan, right_tan, tolerance)


def _fit_cubic_recursive(
    points: list[Point],
    left_tan: tuple[float, float],
    right_tan: tuple[float, float],
    tolerance: float,
) -> list[BezierSegment]:
    """Recursively fit cubic beziers, splitting at max-error point."""
    if len(points) == 2:
        # Degenerate — return line as-is (caller handles)
        return []

    # Try fitting a single cubic
    bezier = _fit_single_cubic(points, left_tan, right_tan)
    max_err, split_idx = _compute_max_error(points, bezier)

    if max_err <= tolerance:
        return [bezier]

    # Split at point of maximum error and recurse
    if split_idx <= 0:
        split_idx = 1
    if split_idx >= len(points) - 1:
        split_idx = len(points) - 2

    center_tan = _normalize(_sub(points[split_idx + 1], points[split_idx - 1]))
    neg_center_tan = (-center_tan[0], -center_tan[1])

    left_segs = _fit_cubic_recursive(
        points[: split_idx + 1], left_tan, neg_center_tan, tolerance,
    )
    right_segs = _fit_cubic_recursive(
        points[split_idx:], center_tan, right_tan, tolerance,
    )
    return left_segs + right_segs


def _fit_single_cubic(
    points: list[Point],
    left_tan: tuple[float, float],
    right_tan: tuple[float, float],
) -> BezierSegment:
    """Fit a single cubic bezier to a point sequence using least-squares.

    Uses chord-length parameterization and the Schneider method for
    computing control points from endpoint tangents.
    """
    n = len(points)
    first = points[0]
    last = points[-1]

    # Chord-length parameterization
    u = _chord_length_parameterize(points)

    # Compute A matrix entries and right-hand side
    # For each point, compute contribution to control point distances
    a00 = a01 = a11 = 0.0
    x0 = x1 = 0.0

    for i in range(n):
        t = u[i]
        b1 = 3.0 * t * (1.0 - t) ** 2  # Bernstein basis B1
        b2 = 3.0 * t ** 2 * (1.0 - t)   # Bernstein basis B2

        a1 = (left_tan[0] * b1, left_tan[1] * b1)
        a2 = (right_tan[0] * b2, right_tan[1] * b2)

        a00 += _dot(a1, a1)
        a01 += _dot(a1, a2)
        a11 += _dot(a2, a2)

        # tmp = point - bezier(t) using only endpoints
        b0 = (1.0 - t) ** 3
        b3 = t ** 3
        tmp = (
            points[i].x - (first.x * b0 + first.x * b1 + last.x * b2 + last.x * b3),
            points[i].y - (first.y * b0 + first.y * b1 + last.y * b2 + last.y * b3),
        )
        x0 += _dot(a1, tmp)
        x1 += _dot(a2, tmp)

    # Solve 2x2 system
    det = a00 * a11 - a01 * a01
    if abs(det) < 1e-12:
        # Fallback: use 1/3 rule
        dist = _dist(first, last) / 3.0
        return BezierSegment(
            start=first,
            control1=Point(first.x + left_tan[0] * dist, first.y + left_tan[1] * dist),
            control2=Point(last.x + right_tan[0] * dist, last.y + right_tan[1] * dist),
            end=last,
        )

    alpha_l = (a11 * x0 - a01 * x1) / det
    alpha_r = (a00 * x1 - a01 * x0) / det

    # If alpha is negative or too small, use heuristic
    seg_length = _dist(first, last)
    eps = 1e-6 * seg_length
    if alpha_l < eps or alpha_r < eps:
        dist = seg_length / 3.0
        alpha_l = dist
        alpha_r = dist

    return BezierSegment(
        start=first,
        control1=Point(first.x + left_tan[0] * alpha_l, first.y + left_tan[1] * alpha_l),
        control2=Point(last.x + right_tan[0] * alpha_r, last.y + right_tan[1] * alpha_r),
        end=last,
    )


def _compute_max_error(
    points: list[Point],
    bezier: BezierSegment,
) -> tuple[float, int]:
    """Compute maximum distance from points to the fitted bezier."""
    u = _chord_length_parameterize(points)
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(points) - 1):
        p = _eval_bezier(bezier, u[i])
        d = _dist(points[i], p)
        if d > max_dist:
            max_dist = d
            max_idx = i
    return max_dist, max_idx


def _eval_bezier(b: BezierSegment, t: float) -> Point:
    """Evaluate cubic bezier at parameter t."""
    mt = 1.0 - t
    mt2 = mt * mt
    t2 = t * t
    x = mt2 * mt * b.start.x + 3 * mt2 * t * b.control1.x + 3 * mt * t2 * b.control2.x + t2 * t * b.end.x
    y = mt2 * mt * b.start.y + 3 * mt2 * t * b.control1.y + 3 * mt * t2 * b.control2.y + t2 * t * b.end.y
    return Point(x, y)


def _chord_length_parameterize(points: list[Point]) -> list[float]:
    """Assign parameter values using cumulative chord length."""
    u = [0.0]
    for i in range(1, len(points)):
        u.append(u[-1] + _dist(points[i - 1], points[i]))
    total = u[-1]
    if total > 1e-12:
        u = [v / total for v in u]
    else:
        # Degenerate: evenly space
        n = len(points) - 1
        u = [i / n if n > 0 else 0.0 for i in range(len(points))]
    return u


# ---------------------------------------------------------------------------
# Vector math helpers
# ---------------------------------------------------------------------------


def _sub(a: Point, b: Point) -> tuple[float, float]:
    return (a.x - b.x, a.y - b.y)


def _normalize(v: tuple[float, float]) -> tuple[float, float]:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1])
    if length < 1e-12:
        return (1.0, 0.0)
    return (v[0] / length, v[1] / length)


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


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
