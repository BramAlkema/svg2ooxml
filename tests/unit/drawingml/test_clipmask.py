"""Tests for clip and mask XML helpers."""

from __future__ import annotations

from svg2ooxml.drawingml.clipmask import mask_xml_for
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import MaskDefinition, MaskRef


def test_mask_xml_for_emits_clip_path_geometry() -> None:
    mask_def = MaskDefinition(
        mask_id="mask1",
        bounding_box=Rect(0, 0, 4, 4),
        segments=(
            LineSegment(Point(0, 0), Point(4, 0)),
            LineSegment(Point(4, 0), Point(4, 4)),
            LineSegment(Point(4, 4), Point(0, 4)),
            LineSegment(Point(0, 4), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(mask_id="mask1", definition=mask_def)

    xml, diagnostics = mask_xml_for(mask_ref)

    assert "<a:clipPath>" in xml
    assert any("clip path geometry" in message for message in diagnostics)


def test_mask_xml_falls_back_to_bounding_box() -> None:
    mask_def = MaskDefinition(
        mask_id="mask2",
        bounding_box=Rect(1, 2, 3, 4),
        segments=(),
    )
    mask_ref = MaskRef(mask_id="mask2", definition=mask_def)

    xml, diagnostics = mask_xml_for(mask_ref)

    assert "<a:clipPath>" in xml
    assert any("bounding box" in message for message in diagnostics)
