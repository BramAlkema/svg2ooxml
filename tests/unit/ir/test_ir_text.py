"""Tests for IR text primitives."""

from svg2ooxml.ir.font_metadata import FontMetadata
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import EnhancedRun, Run, TextAnchor, TextFrame


def test_run_weight_and_decoration() -> None:
    run = Run(
        text="Hello",
        font_family="Arial",
        font_size_pt=12.0,
        bold=True,
        underline=True,
    )

    assert run.weight_class == 700
    assert run.has_decoration is True


def test_enhanced_run_effective_values() -> None:
    metadata = FontMetadata(family="Calibri", weight=500, size_pt=11.0)
    run = EnhancedRun(
        text="Hi",
        font_family="Arial",
        font_size_pt=12.0,
        font_metadata=metadata,
    )

    assert run.effective_font_family == "Calibri"
    assert run.effective_font_size == 11.0
    assert run.weight_class == 500


def test_text_frame_defaults() -> None:
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 10, 10),
    )

    assert frame.is_textless is True
    assert frame.text_content == ""
