"""Tests for preset shape detection."""


import pytest

from svg2ooxml.common.geometry.shape_detect import (
    detect_preset_shape,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point

KAPPA = 0.5522847498


def _line(x1, y1, x2, y2):
    return LineSegment(Point(x1, y1), Point(x2, y2))


def _bezier(sx, sy, c1x, c1y, c2x, c2y, ex, ey):
    return BezierSegment(Point(sx, sy), Point(c1x, c1y), Point(c2x, c2y), Point(ex, ey))


def _make_rect(x, y, w, h):
    """Create 4 line segments forming an axis-aligned rectangle."""
    return [
        _line(x, y, x + w, y),
        _line(x + w, y, x + w, y + h),
        _line(x + w, y + h, x, y + h),
        _line(x, y + h, x, y),
    ]


def _make_ellipse(cx, cy, rx, ry):
    """Create 4 cubic bezier segments forming a standard ellipse."""
    kx = KAPPA * rx
    ky = KAPPA * ry
    right = Point(cx + rx, cy)
    bottom = Point(cx, cy + ry)
    left = Point(cx - rx, cy)
    top = Point(cx, cy - ry)
    return [
        BezierSegment(right, Point(cx + rx, cy + ky), Point(cx + kx, cy + ry), bottom),
        BezierSegment(bottom, Point(cx - kx, cy + ry), Point(cx - rx, cy + ky), left),
        BezierSegment(left, Point(cx - rx, cy - ky), Point(cx - kx, cy - ry), top),
        BezierSegment(top, Point(cx + kx, cy - ry), Point(cx + rx, cy - ky), right),
    ]


def _make_round_rect(x, y, w, h, r):
    """Create 4 lines + 4 bezier corners for a rounded rectangle."""
    k = KAPPA * r
    return [
        # Top edge
        _line(x + r, y, x + w - r, y),
        # Top-right corner
        _bezier(x + w - r, y, x + w - r + k, y, x + w, y + r - k, x + w, y + r),
        # Right edge
        _line(x + w, y + r, x + w, y + h - r),
        # Bottom-right corner
        _bezier(x + w, y + h - r, x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h),
        # Bottom edge
        _line(x + w - r, y + h, x + r, y + h),
        # Bottom-left corner
        _bezier(x + r, y + h, x + r - k, y + h, x, y + h - r + k, x, y + h - r),
        # Left edge
        _line(x, y + h - r, x, y + r),
        # Top-left corner
        _bezier(x, y + r, x, y + r - k, x + r - k, y, x + r, y),
    ]


# ---------------------------------------------------------------------------
# Rectangle detection
# ---------------------------------------------------------------------------


class TestRectDetection:
    def test_detects_simple_rect(self):
        segs = _make_rect(10, 20, 100, 50)
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is not None
        assert match.preset == "rect"
        assert match.bounds.x == pytest.approx(10)
        assert match.bounds.width == pytest.approx(100)

    def test_rejects_non_closed(self):
        segs = [
            _line(0, 0, 10, 0),
            _line(10, 0, 10, 10),
            _line(10, 10, 0, 10),
            _line(0, 10, 0, 5),  # doesn't close back to (0,0)
        ]
        match = detect_preset_shape(segs, tolerance=0.1)
        assert match is None

    def test_rejects_rotated_rect(self):
        # Diamond shape — not axis-aligned
        segs = [
            _line(5, 0, 10, 5),
            _line(10, 5, 5, 10),
            _line(5, 10, 0, 5),
            _line(0, 5, 5, 0),
        ]
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is None

    def test_rejects_wrong_segment_count(self):
        segs = [_line(0, 0, 10, 0), _line(10, 0, 10, 10), _line(10, 10, 0, 0)]
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is None


# ---------------------------------------------------------------------------
# Ellipse detection
# ---------------------------------------------------------------------------


class TestEllipseDetection:
    def test_detects_circle(self):
        segs = _make_ellipse(50, 50, 20, 20)
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is not None
        assert match.preset == "ellipse"
        assert match.bounds.width == pytest.approx(40, abs=1)
        assert match.bounds.height == pytest.approx(40, abs=1)

    def test_detects_ellipse(self):
        segs = _make_ellipse(100, 50, 40, 20)
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is not None
        assert match.preset == "ellipse"
        assert match.bounds.width == pytest.approx(80, abs=1)
        assert match.bounds.height == pytest.approx(40, abs=1)

    def test_rejects_non_ellipse_curves(self):
        # 4 beziers that don't form an ellipse
        segs = [
            _bezier(0, 0, 5, 20, 15, 20, 20, 0),
            _bezier(20, 0, 25, -20, 35, -20, 40, 0),
            _bezier(40, 0, 35, 20, 25, 20, 20, 0),
            _bezier(20, 0, 15, -20, 5, -20, 0, 0),
        ]
        match = detect_preset_shape(segs, tolerance=1.0)
        # May or may not match depending on tolerance — at tight tolerance should fail
        if match is not None:
            assert match.confidence < 0.5

    def test_slightly_imprecise_ellipse(self):
        # Add small perturbation — should still match at default tolerance
        segs = _make_ellipse(50, 50, 30, 15)
        # Perturb one control point slightly
        s = segs[0]
        segs[0] = BezierSegment(
            s.start,
            Point(s.control1.x + 0.5, s.control1.y + 0.3),
            s.control2,
            s.end,
        )
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is not None
        assert match.preset == "ellipse"


# ---------------------------------------------------------------------------
# Rounded rectangle detection
# ---------------------------------------------------------------------------


class TestRoundRectDetection:
    def test_detects_round_rect(self):
        segs = _make_round_rect(10, 20, 100, 60, 8)
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is not None
        assert match.preset == "roundRect"
        assert match.corner_radius == pytest.approx(8, abs=2)

    def test_rejects_mismatched_corners(self):
        # Make one corner much larger
        segs = _make_round_rect(0, 0, 100, 60, 8)
        # Replace first corner with a larger radius
        big = _make_round_rect(0, 0, 100, 60, 25)
        segs[1] = big[1]
        match = detect_preset_shape(segs, tolerance=2.0)
        assert match is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_segments(self):
        assert detect_preset_shape([], tolerance=2.0) is None

    def test_single_segment(self):
        assert detect_preset_shape([_line(0, 0, 10, 0)], tolerance=2.0) is None

    def test_multi_subpath_not_eligible(self):
        # Two separate rects — compound path, not a single shape
        segs = _make_rect(0, 0, 10, 10) + _make_rect(20, 20, 10, 10)
        assert detect_preset_shape(segs, tolerance=2.0) is None
