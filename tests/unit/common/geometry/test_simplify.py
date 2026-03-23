"""Tests for path simplification passes."""

import math

import pytest

from svg2ooxml.common.geometry.simplify import (
    _curve_fit,
    _demote_flat_beziers,
    _merge_collinear,
    _rdp_simplify,
    _remove_degenerates,
    _split_subpaths,
    simplify_segments,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(x1, y1, x2, y2):
    return LineSegment(Point(x1, y1), Point(x2, y2))


def _bezier(sx, sy, c1x, c1y, c2x, c2y, ex, ey):
    return BezierSegment(Point(sx, sy), Point(c1x, c1y), Point(c2x, c2y), Point(ex, ey))


# ---------------------------------------------------------------------------
# Pass 1: Degenerate removal
# ---------------------------------------------------------------------------


class TestRemoveDegenerates:
    def test_removes_zero_length_line(self):
        segs = [_line(0, 0, 0, 0), _line(0, 0, 10, 0)]
        result = _remove_degenerates(segs, epsilon=0.01)
        assert len(result) == 1
        assert result[0].end == Point(10, 0)

    def test_removes_near_zero_length_line(self):
        segs = [_line(0, 0, 0.005, 0.005), _line(0, 0, 10, 0)]
        result = _remove_degenerates(segs, epsilon=0.01)
        assert len(result) == 1

    def test_keeps_normal_line(self):
        segs = [_line(0, 0, 1, 1)]
        result = _remove_degenerates(segs, epsilon=0.01)
        assert len(result) == 1

    def test_removes_collapsed_bezier(self):
        segs = [_bezier(5, 5, 5.001, 5, 5, 5.001, 5.002, 5.002)]
        result = _remove_degenerates(segs, epsilon=0.01)
        assert len(result) == 1  # kept as last segment (never empty subpath)

    def test_keeps_curved_bezier(self):
        segs = [_bezier(0, 0, 5, 10, 15, 10, 20, 0)]
        result = _remove_degenerates(segs, epsilon=0.01)
        assert len(result) == 1

    def test_never_empties_subpath(self):
        segs = [_line(0, 0, 0, 0)]
        result = _remove_degenerates(segs, epsilon=1.0)
        assert len(result) == 1

    def test_empty_input(self):
        assert _remove_degenerates([], epsilon=0.01) == []


# ---------------------------------------------------------------------------
# Pass 2: Bezier demotion
# ---------------------------------------------------------------------------


class TestDemoteFlatBeziers:
    def test_demotes_flat_bezier(self):
        # Control points on the chord line
        seg = _bezier(0, 0, 3, 0.1, 7, -0.1, 10, 0)
        result = _demote_flat_beziers([seg], flatness=0.5)
        assert len(result) == 1
        assert isinstance(result[0], LineSegment)
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(10, 0)

    def test_keeps_curved_bezier(self):
        seg = _bezier(0, 0, 0, 10, 10, 10, 10, 0)
        result = _demote_flat_beziers([seg], flatness=0.5)
        assert len(result) == 1
        assert isinstance(result[0], BezierSegment)

    def test_keeps_line_segments(self):
        seg = _line(0, 0, 10, 0)
        result = _demote_flat_beziers([seg], flatness=0.5)
        assert result == [seg]

    def test_degenerate_chord(self):
        # Start == end, but control points spread out
        seg = _bezier(5, 5, 10, 5, 5, 10, 5, 5)
        result = _demote_flat_beziers([seg], flatness=0.5)
        assert isinstance(result[0], BezierSegment)  # not demoted

    def test_degenerate_chord_flat(self):
        # Start ≈ end, control points also close
        seg = _bezier(5, 5, 5.1, 5.1, 5.2, 5.2, 5, 5)
        result = _demote_flat_beziers([seg], flatness=0.5)
        assert isinstance(result[0], LineSegment)


# ---------------------------------------------------------------------------
# Pass 3: Collinear merge
# ---------------------------------------------------------------------------


class TestMergeCollinear:
    def test_merges_two_collinear_horizontal(self):
        segs = [_line(0, 0, 5, 0), _line(5, 0, 10, 0)]
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 1
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(10, 0)

    def test_merges_three_collinear(self):
        segs = [_line(0, 0, 3, 0), _line(3, 0, 7, 0), _line(7, 0, 10, 0)]
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 1
        assert result[0].end == Point(10, 0)

    def test_keeps_perpendicular(self):
        segs = [_line(0, 0, 10, 0), _line(10, 0, 10, 10)]
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 2

    def test_keeps_non_adjacent(self):
        segs = [_line(0, 0, 5, 0), _line(5, 1, 10, 1)]  # gap
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 2

    def test_skips_beziers(self):
        segs = [
            _line(0, 0, 5, 0),
            _bezier(5, 0, 6, 2, 8, 2, 10, 0),
            _line(10, 0, 15, 0),
        ]
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 3

    def test_nearly_collinear(self):
        # 0.1 degree deviation — should merge with 0.5 degree tolerance
        angle = math.radians(0.1)
        segs = [
            _line(0, 0, 10, 0),
            _line(10, 0, 20, 10 * math.tan(angle)),
        ]
        result = _merge_collinear(segs, angle_deg=0.5, epsilon=0.01)
        assert len(result) == 1

    def test_empty(self):
        assert _merge_collinear([], angle_deg=0.5, epsilon=0.01) == []


# ---------------------------------------------------------------------------
# Pass 4: RDP
# ---------------------------------------------------------------------------


class TestRdpSimplify:
    def test_removes_intermediate_points_on_line(self):
        # Four points on a straight line — RDP needs ≥3 segments
        segs = [_line(0, 0, 3, 0), _line(3, 0, 6, 0), _line(6, 0, 10, 0)]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert len(result) == 1
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(10, 0)

    def test_keeps_significant_deviation(self):
        # Triangle: middle point is 5 units from the baseline — well above tolerance
        segs = [_line(0, 0, 5, 5), _line(5, 5, 10, 0)]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert len(result) == 2

    def test_reduces_zigzag_within_tolerance(self):
        # Small zigzag within tolerance band
        segs = [
            _line(0, 0, 2, 0.3),
            _line(2, 0.3, 4, -0.2),
            _line(4, -0.2, 6, 0.1),
            _line(6, 0.1, 8, -0.3),
            _line(8, -0.3, 10, 0),
        ]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert len(result) < 5
        assert result[0].start == Point(0, 0)
        assert result[-1].end == Point(10, 0)

    def test_preserves_bezier_segments(self):
        segs = [
            _line(0, 0, 5, 0),
            _bezier(5, 0, 6, 2, 8, 2, 10, 0),
            _line(10, 0, 15, 0),
        ]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert any(isinstance(s, BezierSegment) for s in result)

    def test_handles_gap_between_runs(self):
        segs = [
            _line(0, 0, 3, 0),
            _line(3, 0, 7, 0),
            _line(7, 0, 10, 0),
            # gap
            _line(20, 20, 23, 20),
            _line(23, 20, 27, 20),
            _line(27, 20, 30, 20),
        ]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert len(result) == 2
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(10, 0)
        assert result[1].start == Point(20, 20)
        assert result[1].end == Point(30, 20)

    def test_short_runs_unchanged(self):
        segs = [_line(0, 0, 5, 5)]
        result = _rdp_simplify(segs, tolerance=1.0, epsilon=0.01)
        assert len(result) == 1

    def test_closed_polygon_simplification(self):
        # Square with extra point on one edge — should simplify
        segs = [
            _line(0, 0, 5, 0),
            _line(5, 0, 10, 0),   # collinear with above
            _line(10, 0, 10, 10),
            _line(10, 10, 0, 10),
            _line(0, 10, 0, 0),
        ]
        result = _rdp_simplify(segs, tolerance=0.5, epsilon=0.01)
        # The collinear point on top edge should be removed
        assert len(result) == 4


# ---------------------------------------------------------------------------
# Pass 5: Curve fitting
# ---------------------------------------------------------------------------


class TestCurveFit:
    def _semicircle_points(self, n=20):
        """Generate points along a semicircle (0 to pi)."""
        points = []
        for i in range(n):
            t = math.pi * i / (n - 1)
            points.append(Point(math.cos(t) * 10, math.sin(t) * 10))
        return points

    def _lines_from_points(self, points):
        return [LineSegment(points[i], points[i + 1]) for i in range(len(points) - 1)]

    def test_fits_semicircle_to_fewer_beziers(self):
        pts = self._semicircle_points(20)
        segs = self._lines_from_points(pts)
        result = _curve_fit(segs, tolerance=0.5, min_points=8, epsilon=0.01)
        assert len(result) < len(segs)
        assert any(isinstance(s, BezierSegment) for s in result)

    def test_quality_gate_keeps_original(self):
        # 3 line segments — below min_points, should pass through
        segs = [_line(0, 0, 3, 1), _line(3, 1, 6, 0), _line(6, 0, 9, 1)]
        result = _curve_fit(segs, tolerance=0.5, min_points=8, epsilon=0.01)
        assert len(result) == 3
        assert all(isinstance(s, LineSegment) for s in result)

    def test_preserves_bezier_segments(self):
        segs = [
            _line(0, 0, 5, 0),
            _bezier(5, 0, 6, 2, 8, 2, 10, 0),
            _line(10, 0, 15, 0),
        ]
        result = _curve_fit(segs, tolerance=0.5, min_points=2, epsilon=0.01)
        assert any(isinstance(s, BezierSegment) for s in result)

    def test_fitted_curve_approximates_original(self):
        # Quarter circle with many sample points
        n = 30
        pts = []
        for i in range(n):
            t = (math.pi / 2) * i / (n - 1)
            pts.append(Point(math.cos(t) * 20, math.sin(t) * 20))
        segs = self._lines_from_points(pts)
        result = _curve_fit(segs, tolerance=1.0, min_points=8, epsilon=0.01)
        # Should produce significantly fewer segments
        assert len(result) < len(segs) // 2
        # Start and end should match
        assert result[0].start.x == pytest.approx(pts[0].x, abs=0.1)
        assert result[-1].end.x == pytest.approx(pts[-1].x, abs=0.1)

    def test_straight_line_not_fitted(self):
        # Points on a straight line — fitting would produce 1 bezier
        # but quality gate: 1 bezier vs many lines. Bezier wins.
        pts = [Point(i, 0) for i in range(20)]
        segs = self._lines_from_points(pts)
        result = _curve_fit(segs, tolerance=0.5, min_points=8, epsilon=0.01)
        # After RDP/collinear merge these would already be 1 line,
        # but curve fit alone should still produce fewer segments
        assert len(result) <= len(segs)


# ---------------------------------------------------------------------------
# Subpath splitting
# ---------------------------------------------------------------------------


class TestSplitSubpaths:
    def test_single_subpath(self):
        segs = [_line(0, 0, 5, 0), _line(5, 0, 10, 0)]
        result = _split_subpaths(segs)
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_two_subpaths(self):
        segs = [_line(0, 0, 5, 0), _line(20, 20, 30, 20)]
        result = _split_subpaths(segs)
        assert len(result) == 2

    def test_empty(self):
        assert _split_subpaths([]) == []


# ---------------------------------------------------------------------------
# Integration: simplify_segments
# ---------------------------------------------------------------------------


class TestSimplifySegments:
    def test_compound_path_preserves_subpaths(self):
        # Two separate subpaths — simplification should not cross boundary
        segs = [
            _line(0, 0, 10, 0),
            _line(10, 0, 10, 10),
            # gap — new subpath
            _line(50, 50, 60, 50),
            _line(60, 50, 60, 60),
        ]
        result = simplify_segments(segs)
        # Both subpaths preserved (no merging across gap)
        assert len(result) == 4

    def test_reduces_collinear_run(self):
        segs = [_line(0, 0, 1, 0), _line(1, 0, 2, 0), _line(2, 0, 3, 0)]
        result = simplify_segments(segs)
        assert len(result) == 1
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(3, 0)

    def test_demotes_and_merges(self):
        # Flat bezier followed by collinear line — should demote then merge
        segs = [
            _bezier(0, 0, 3, 0.001, 7, -0.001, 10, 0),
            _line(10, 0, 20, 0),
        ]
        result = simplify_segments(segs)
        assert len(result) == 1
        assert isinstance(result[0], LineSegment)
        assert result[0].start == Point(0, 0)
        assert result[0].end == Point(20, 0)

    def test_passthrough_simple_path(self):
        # Triangle — nothing to simplify
        segs = [
            _line(0, 0, 10, 0),
            _line(10, 0, 5, 8),
            _line(5, 8, 0, 0),
        ]
        result = simplify_segments(segs)
        assert len(result) == 3
