"""Tests for IR scene primitives."""

from svg2ooxml.ir.effects import BlurEffect
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.paint import SolidPaint, Stroke
from svg2ooxml.ir.scene import (
    ClipRef,
    ClipStrategy,
    Group,
    MaskDefinition,
    MaskInstance,
    MaskMode,
    MaskRef,
    Path,
)
from svg2ooxml.ir.shapes import Circle


def _line(x1: float, y1: float, x2: float, y2: float) -> LineSegment:
    return LineSegment(Point(x1, y1), Point(x2, y2))


def test_path_bbox_and_complexity() -> None:
    path = Path(
        segments=[_line(0, 0, 2, 0), _line(2, 0, 2, 3)],
        fill=SolidPaint("FF0000"),
        stroke=Stroke(paint=SolidPaint("000000"), width=1.0),
        clip=ClipRef("clip1", strategy=ClipStrategy.NATIVE),
        effects=[BlurEffect(1.5)],
    )

    bbox = path.bbox

    assert bbox.width == 2
    assert bbox.height == 3
    assert path.complexity_score >= 4


def test_group_bbox_and_children_count() -> None:
    circle = Circle(center=Point(5, 5), radius=2)
    path = Path(segments=[_line(0, 0, 1, 1)], fill=None)
    group = Group(children=[circle, path])

    bbox = group.bbox

    assert bbox.left == 0
    assert bbox.right >= 7
    assert group.total_element_count == 2


def test_mask_definition_reference() -> None:
    mask_def = MaskDefinition(mask_id="mask1")
    mask = MaskRef(mask_id="url(#mask1)", definition=mask_def)

    assert mask.definition is mask_def


def test_mask_instance_exposes_mode_and_bounds() -> None:
    definition = MaskDefinition(mask_id="mask2", mode=MaskMode.ALPHA, bounding_box=Rect(0, 0, 10, 20))
    mask_ref = MaskRef(mask_id="mask2", definition=definition, target_bounds=Rect(0, 0, 10, 20), target_opacity=0.6)
    instance = MaskInstance(mask=mask_ref, bounds=Rect(1, 2, 8, 16), opacity=0.8)

    assert instance.mask_id == "mask2"
    assert instance.definition is definition
    assert instance.mode == MaskMode.ALPHA
    assert instance.bounds == Rect(1, 2, 8, 16)
