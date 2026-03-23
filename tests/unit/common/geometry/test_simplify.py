"""Tests for path simplification passes."""

import math

import pytest

from svg2ooxml.common.geometry.simplify import (
    _demote_flat_beziers,
    _merge_collinear,
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
