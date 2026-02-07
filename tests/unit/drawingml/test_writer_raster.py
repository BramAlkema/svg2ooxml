from __future__ import annotations

import pytest

from svg2ooxml.drawingml.rasterizer import SKIA_AVAILABLE
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.paint import SolidPaint, Stroke
from svg2ooxml.ir.shapes import Rectangle

pytestmark = pytest.mark.skipif(not SKIA_AVAILABLE, reason="skia-python not available")


def test_writer_rasterizes_rectangle(tmp_path):
    writer = DrawingMLWriter()

    rect = Rectangle(
        bounds=Rect(10, 20, 50, 30),
        fill=SolidPaint("336699"),
        stroke=Stroke(paint=SolidPaint("112233"), width=2.0),
        metadata={"policy": {"geometry": {"suggest_fallback": "bitmap"}}},
    )

    result = writer.render_scene([rect])

    media_assets = list(result.assets.iter_media())
    if not media_assets:
        pytest.skip("Rasterizer backend unavailable; no media emitted")
    names = [asset.filename for asset in media_assets]
    assert any(name.endswith(".png") for name in names)
