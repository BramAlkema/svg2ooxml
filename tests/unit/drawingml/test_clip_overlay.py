"""Tests for clip overlay EMF builder."""

from __future__ import annotations

from svg2ooxml.drawingml.clip_overlay import build_clip_overlay_emf
from svg2ooxml.ir.geometry import LineSegment, Point, Rect


def _square_segments(x: float, y: float, size: float) -> tuple:
    """Create a closed square clip path."""
    return (
        LineSegment(Point(x, y), Point(x + size, y)),
        LineSegment(Point(x + size, y), Point(x + size, y + size)),
        LineSegment(Point(x + size, y + size), Point(x, y + size)),
        LineSegment(Point(x, y + size), Point(x, y)),
    )


def test_build_overlay_returns_emf_bytes() -> None:
    bbox = Rect(0, 0, 100, 100)
    segments = _square_segments(25, 25, 50)

    result = build_clip_overlay_emf(bbox, segments)

    assert result is not None
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_build_overlay_empty_segments_returns_none() -> None:
    bbox = Rect(0, 0, 100, 100)

    result = build_clip_overlay_emf(bbox, [])

    assert result is None


def test_build_overlay_degenerate_bbox_returns_none() -> None:
    segments = _square_segments(0, 0, 10)

    assert build_clip_overlay_emf(Rect(0, 0, 0, 10), segments) is None
    assert build_clip_overlay_emf(Rect(0, 0, 10, 0), segments) is None


def test_build_overlay_too_few_points_returns_none() -> None:
    """A single line segment flattens to < 3 points."""
    segments = (LineSegment(Point(0, 0), Point(10, 0)),)
    bbox = Rect(0, 0, 100, 100)

    result = build_clip_overlay_emf(bbox, segments)

    assert result is None


def test_build_overlay_custom_color() -> None:
    bbox = Rect(0, 0, 100, 100)
    segments = _square_segments(10, 10, 80)

    result = build_clip_overlay_emf(bbox, segments, overlay_color=0x00FF0000)

    assert result is not None
    assert len(result) > 0
