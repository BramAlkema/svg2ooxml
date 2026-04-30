"""Tests for clip bounds helpers."""

from __future__ import annotations

from svg2ooxml.drawingml.clipmask import clip_bounds_for, clip_xml_for
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import ClipRef, ClipStrategy


def test_clip_bounds_for_returns_custom_geometry_bounds() -> None:
    clip_ref = ClipRef(
        clip_id="clip1",
        bounding_box=Rect(0, 0, 10, 10),
        custom_geometry_bounds=Rect(1, 1, 8, 8),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )

    bounds, diagnostics = clip_bounds_for(clip_ref)

    assert bounds == Rect(1, 1, 8, 8)
    assert any("custom geometry" in msg for msg in diagnostics)


def test_clip_bounds_for_falls_back_to_bounding_box() -> None:
    clip_ref = ClipRef(
        clip_id="clip2",
        bounding_box=Rect(2, 3, 4, 5),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )

    bounds, diagnostics = clip_bounds_for(clip_ref)

    assert bounds == Rect(2, 3, 4, 5)
    assert any("bounding box" in msg for msg in diagnostics)


def test_clip_bounds_for_none_returns_none() -> None:
    bounds, diagnostics = clip_bounds_for(None)

    assert bounds is None
    assert diagnostics == []


def test_clip_bounds_for_empty_clip_returns_none_with_hidden_diagnostic() -> None:
    clip_ref = ClipRef(clip_id="empty", is_empty=True)

    bounds, diagnostics = clip_bounds_for(clip_ref)

    assert bounds is None
    assert any("empty" in msg and "hidden" in msg for msg in diagnostics)


def test_clip_xml_for_returns_empty_string() -> None:
    """Legacy API always returns empty XML string."""
    clip_ref = ClipRef(
        clip_id="clip3",
        bounding_box=Rect(0, 0, 10, 10),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )

    xml, diagnostics = clip_xml_for(clip_ref)

    assert xml == ""
    assert len(diagnostics) > 0
