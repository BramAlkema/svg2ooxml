from __future__ import annotations

from svg2ooxml.drawingml import paint_runtime
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    PatternPaint,
    SolidPaint,
    Stroke,
)


def test_pattern_fill_uses_preset_and_colours() -> None:
    paint = PatternPaint(
        pattern_id="pat",
        preset="pct20",
        foreground="123456",
        background="abcdef",
    )

    xml = paint_runtime.paint_to_fill(paint)

    assert 'prst="pct20"' in xml
    assert 'val="123456"' in xml
    assert 'val="ABCDEF"' in xml


def test_gradient_stroke_generates_gradient_fill() -> None:
    gradient = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    stroke = Stroke(paint=gradient, width=2.0)

    xml = paint_runtime.stroke_to_xml(stroke)

    assert "<a:gradFill" in xml


def test_dashed_stroke_emits_prst_dash() -> None:
    stroke = Stroke(
        paint=SolidPaint("000000"),
        width=1.0,
        dash_array=[4.0, 4.0],
    )

    xml = paint_runtime.stroke_to_xml(stroke)

    assert '<a:prstDash val="dash"/>' in xml
