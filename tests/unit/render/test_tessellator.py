from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.render.geometry import Tessellator


def test_tessellator_handles_rectangle():
    from svg2ooxml.ir.shapes import Rectangle

    rect = Rectangle(bounds=Rect(0, 0, 10, 5))
    tess = Tessellator().tessellate_geometry(rect)

    assert len(tess.contours) == 1
    contour = tess.contours[0]
    assert contour.shape == (5, 2)
    assert np.allclose(contour[0], [0, 0])
    assert np.allclose(contour[2], [10, 5])
    assert tess.areas and abs(tess.areas[0] - 50.0) < 1e-3


def test_tessellator_handles_path():
    from svg2ooxml.ir.geometry import LineSegment, Point

    segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
        LineSegment(Point(10, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
    ]
    path = IRPath(segments=segments)

    tess = Tessellator().tessellate_geometry(path)
    assert tess.contours
    contour = tess.contours[0]
    assert contour.shape[0] >= 4
    assert tess.areas and abs(tess.areas[0]) > 0


def test_tessellator_handles_polyline():
    poly = {
        "type": "polyline",
        "points": [(0, 0), (5, 5), (10, 0)],
        "closed": False,
    }
    tess = Tessellator().tessellate_geometry(poly)
    assert len(tess.contours[0]) == 3
    assert tess.areas[0] == 0


def test_tessellator_stroke_outline():
    from svg2ooxml.ir.shapes import Rectangle

    rect = Rectangle(bounds=Rect(0, 0, 20, 10))
    tess = Tessellator().tessellate_stroke(rect, stroke_width=4)
    assert tess.stroke_outline is not None
    assert len(tess.stroke_outline[0]) == len(tess.contours[0])
