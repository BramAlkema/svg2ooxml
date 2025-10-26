"""Integration tests for the resvg-to-IR geometry adapters."""

from __future__ import annotations

import pytest

from svg2ooxml.geometry.paths import normalize_path_to_segments, tessellate_path
from svg2ooxml.geometry.transforms.matrix import Matrix2D


def test_normalize_path_to_segments_applies_transform() -> None:
    square_path = "M0 0 L10 0 L10 10 L0 10 Z"
    translation = Matrix2D.translation(5.0, -2.0)

    result = normalize_path_to_segments(square_path, transform=translation)

    assert len(result.segments) == 4
    first = result.segments[0]
    assert first.start.x == pytest.approx(5.0)
    assert first.start.y == pytest.approx(-2.0)
    assert first.end.x == pytest.approx(15.0)
    assert first.end.y == pytest.approx(-2.0)
    last = result.segments[-1]
    assert last.end.x == pytest.approx(5.0)
    assert last.end.y == pytest.approx(-2.0)
    assert result.tolerance == pytest.approx(0.25)


def test_tessellate_path_returns_fill_and_stroke_data() -> None:
    square_path = "M0 0 L10 0 L10 10 L0 10 Z"
    normalized = normalize_path_to_segments(square_path, stroke_width=2.0)

    tessellation = tessellate_path(
        normalized.normalized_path,
        include_stroke=True,
    )

    assert len(tessellation.fill.contours) == 1
    contour = tessellation.fill.contours[0]
    assert contour[0].x == pytest.approx(0.0)
    assert contour[0].y == pytest.approx(0.0)
    assert contour[-1].x == pytest.approx(0.0)
    assert contour[-1].y == pytest.approx(0.0)
    assert tessellation.fill.winding_rule == "nonzero"

    assert tessellation.stroke is not None
    assert tessellation.stroke.stroke_width == pytest.approx(2.0)
    assert tessellation.stroke.stroke_outline is not None
    assert len(tessellation.stroke.stroke_outline) == 1
    outline = tessellation.stroke.stroke_outline[0]
    assert len(outline) == len(contour)
    assert all(isinstance(point.x, float) and isinstance(point.y, float) for point in outline)
