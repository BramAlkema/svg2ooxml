"""Tests for IO adapters."""

from __future__ import annotations

import zipfile

from svg2ooxml.core.ir import IRScene
from svg2ooxml.io.pptx_writer import write_pptx
from svg2ooxml.io.svg_reader import read_svg_shapes
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.shapes import Rectangle


def test_read_svg_shapes_returns_placeholder_shapes() -> None:
    shapes = tuple(read_svg_shapes("sample.svg"))

    assert shapes == ("rect", "circle", "text")


def test_write_pptx_creates_package(tmp_path) -> None:
    rect = Rectangle(bounds=Rect(0, 0, 32, 16), fill=SolidPaint("00FF00"))
    scene = IRScene(elements=[rect], width_px=100, height_px=50)
    output = tmp_path / "output.pptx"

    result_path = write_pptx(scene, output)

    assert result_path == output
    assert output.exists()

    with zipfile.ZipFile(output) as archive:
        assert "ppt/slides/slide1.xml" in archive.namelist()
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "Rectangle 2" in slide_xml
