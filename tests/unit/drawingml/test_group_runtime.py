from __future__ import annotations

from svg2ooxml.drawingml.group_runtime import (
    children_overlap,
    translate_group_child_to_local_coordinates,
)
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.paint import SolidPaint, Stroke
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Line, Rectangle
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame


def test_translate_group_child_moves_auxiliary_coordinate_metadata() -> None:
    mask = MaskRef("mask1", target_bounds=Rect(50, 20, 12, 10))
    path = IRPath(
        segments=[LineSegment(Point(50, 20), Point(70, 20))],
        fill=SolidPaint("000000"),
        clip=ClipRef(
            "clip1",
            bounding_box=Rect(48, 18, 18, 12),
            custom_geometry_bounds=Rect(49, 19, 16, 10),
        ),
        mask=mask,
        mask_instance=MaskInstance(
            mask=mask,
            bounds=Rect(51, 21, 11, 9),
        ),
        metadata={
            "_clip_bounds": Rect(48, 18, 18, 12),
            "mask": {
                "target_bounds": Rect(50, 20, 12, 10),
                "instance_bounds": {"x": 51.0, "y": 21.0, "width": 11.0, "height": 9.0},
            },
            "filter_metadata": {
                "blur": {
                    "bounds": {"x": 45.0, "y": 15.0, "width": 30.0, "height": 20.0}
                },
            },
        },
    )

    moved = translate_group_child_to_local_coordinates(path, 40, 10)

    assert moved.segments[0].start == Point(10, 10)
    assert moved.segments[0].end == Point(30, 10)
    assert moved.clip is not None
    assert moved.clip.bounding_box == Rect(8, 8, 18, 12)
    assert moved.clip.custom_geometry_bounds == Rect(9, 9, 16, 10)
    assert moved.mask is not None
    assert moved.mask.target_bounds == Rect(10, 10, 12, 10)
    assert moved.mask_instance is not None
    assert moved.mask_instance.bounds == Rect(11, 11, 11, 9)
    assert moved.mask_instance.mask.target_bounds == Rect(10, 10, 12, 10)
    assert moved.metadata["_clip_bounds"] == Rect(8, 8, 18, 12)
    assert moved.metadata["mask"]["target_bounds"] == Rect(10, 10, 12, 10)
    assert moved.metadata["mask"]["instance_bounds"] == {
        "x": 11.0,
        "y": 11.0,
        "width": 11.0,
        "height": 9.0,
    }
    assert moved.metadata["filter_metadata"]["blur"]["bounds"] == {
        "x": 5.0,
        "y": 5.0,
        "width": 30.0,
        "height": 20.0,
    }


def test_translate_group_child_moves_text_per_char_absolute_positions() -> None:
    text = TextFrame(
        origin=Point(60, 30),
        anchor=TextAnchor.START,
        bbox=Rect(60, 15, 20, 18),
        runs=[Run("is", "Arial", 15)],
        metadata={
            "per_char": {
                "abs_x": [60.0, 64.0],
                "abs_y": [30.0, 30.0],
                "rotate": [45.0, 90.0],
            }
        },
    )

    moved = translate_group_child_to_local_coordinates(text, 40, 10)

    assert moved.origin == Point(20, 20)
    assert moved.bbox == Rect(20, 5, 20, 18)
    assert moved.metadata["per_char"]["abs_x"] == [20.0, 24.0]
    assert moved.metadata["per_char"]["abs_y"] == [20.0, 20.0]
    assert moved.metadata["per_char"]["rotate"] == [45.0, 90.0]


def test_translate_group_child_preserves_relative_per_char_metadata() -> None:
    text = TextFrame(
        origin=Point(60, 30),
        anchor=TextAnchor.START,
        bbox=Rect(60, 15, 20, 18),
        runs=[Run("is", "Arial", 15)],
        metadata={"per_char": {"dx": [1.0, 2.0], "rotate": [0.0, 0.0]}},
    )

    moved = translate_group_child_to_local_coordinates(text, 40, 10)

    assert moved.metadata["per_char"] == {"dx": [1.0, 2.0], "rotate": [0.0, 0.0]}


def test_children_overlap_includes_stroked_zero_area_lines() -> None:
    stroke = Stroke(SolidPaint("000000"), width=4.0)
    horizontal = Line(Point(0, 10), Point(20, 10), stroke=stroke)
    vertical = Line(Point(10, 0), Point(10, 20), stroke=stroke)

    assert children_overlap([horizontal, vertical]) is True


def test_children_overlap_includes_stroke_width_for_stroke_only_shapes() -> None:
    stroke = Stroke(SolidPaint("000000"), width=4.0)
    left = Rectangle(Rect(0, 0, 10, 10), fill=None, stroke=stroke)
    right = Rectangle(Rect(12, 0, 10, 10), fill=None, stroke=stroke)

    assert children_overlap([left, right]) is True


def test_children_overlap_ignores_invisible_paint() -> None:
    first = Rectangle(Rect(0, 0, 20, 20), fill=None, stroke=None)
    second = Rectangle(Rect(10, 10, 20, 20), fill=None, stroke=None)

    assert children_overlap([first, second]) is False


def test_children_overlap_keeps_disjoint_stroke_bounds_separate() -> None:
    stroke = Stroke(SolidPaint("000000"), width=2.0)
    first = Line(Point(0, 0), Point(20, 0), stroke=stroke)
    second = Line(Point(0, 5), Point(20, 5), stroke=stroke)

    assert children_overlap([first, second]) is False


def test_children_overlap_uses_circle_geometry_for_diagonal_bbox_false_positive() -> (
    None
):
    first = Circle(Point(0, 0), 10, fill=SolidPaint("000000"))
    second = Circle(Point(15, 15), 10, fill=SolidPaint("000000"))

    assert children_overlap([first, second]) is False


def test_children_overlap_reports_actual_circle_intersection() -> None:
    first = Circle(Point(0, 0), 10, fill=SolidPaint("000000"))
    second = Circle(Point(14, 14), 10, fill=SolidPaint("000000"))

    assert children_overlap([first, second]) is True


def test_children_overlap_keeps_stroked_circles_conservative() -> None:
    stroke = Stroke(SolidPaint("000000"), width=4.0)
    first = Circle(Point(0, 0), 10, fill=SolidPaint("000000"), stroke=stroke)
    second = Circle(Point(15, 15), 10, fill=SolidPaint("000000"), stroke=stroke)

    assert children_overlap([first, second]) is True
