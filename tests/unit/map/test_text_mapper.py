"""Tests for TextMapper."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.map.mapper import TextMapper, OutputFormat


def _text_frame() -> TextFrame:
    return TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 40),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=12.0)],
        metadata={},
    )


def test_text_mapper_emits_text_body() -> None:
    mapper = TextMapper()
    frame = _text_frame()

    result = mapper.map(frame)
    assert result.output_format == OutputFormat.NATIVE_DML
    assert "<p:txBody>" in result.xml_content
