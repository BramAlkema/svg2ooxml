from __future__ import annotations

from io import BytesIO

import pytest

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.drawingml.rasterizer import SKIA_AVAILABLE, Rasterizer
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import GradientStop, LinearGradientPaint, SolidPaint, Stroke
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.shapes import Rectangle

PILImage = pytest.importorskip("PIL.Image")
pytestmark = pytest.mark.skipif(not SKIA_AVAILABLE, reason="skia-python not available")


def test_rasterizer_applies_shape_opacity_to_fill() -> None:
    rasterizer = Rasterizer()
    rect = Rectangle(
        bounds=Rect(0.0, 0.0, 10.0, 10.0),
        fill=SolidPaint("FF0000"),
        opacity=0.5,
    )

    result = rasterizer.rasterize(rect)

    assert result is not None
    image = PILImage.open(BytesIO(result.data)).convert("RGBA")
    _red, _green, _blue, alpha = image.getpixel((image.width // 2, image.height // 2))
    assert 110 <= alpha <= 145


def test_rasterizer_group_bounds_include_child_stroke_width() -> None:
    rasterizer = Rasterizer()
    rect = Rectangle(
        bounds=Rect(10.0, 10.0, 10.0, 10.0),
        fill=None,
        stroke=Stroke(paint=SolidPaint("000000"), width=8.0),
    )

    result = rasterizer.rasterize(Group(children=[rect]))

    assert result is not None
    assert result.bounds == Rect(6.0, 6.0, 18.0, 18.0)


def test_rasterizer_nested_group_without_drawn_children_returns_none() -> None:
    rasterizer = Rasterizer()
    unsupported_image = Image(
        origin=Point(0.0, 0.0),
        size=Rect(0.0, 0.0, 10.0, 10.0),
        data=b"not decoded here",
        format="png",
    )

    result = rasterizer.rasterize(Group(children=[Group(children=[unsupported_image])]))

    assert result is None


def test_rasterizer_defaults_gradient_units_to_object_bounding_box() -> None:
    rasterizer = Rasterizer()
    paint = LinearGradientPaint(
        stops=[GradientStop(0.0, "000000"), GradientStop(1.0, "FFFFFF")],
        start=(0.0, 0.0),
        end=(1.0, 1.0),
    )

    points = rasterizer._linear_gradient_points(paint, Rect(10.0, 20.0, 30.0, 40.0))

    assert points == (10.0, 20.0, 40.0, 60.0)


def test_rasterizer_accepts_matrix2d_gradient_transform() -> None:
    matrix = Rasterizer._to_skia_matrix(Matrix2D.from_values(2, 0, 0, 3, 4, 5))

    assert matrix is not None
