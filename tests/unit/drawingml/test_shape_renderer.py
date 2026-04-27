"""Shape renderer guardrail tests."""

from __future__ import annotations

from svg2ooxml.drawingml.shape_renderer_utils import is_invalid_custom_effect_xml
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.paint import GradientStop, RadialGradientPaint, SolidPaint
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Rectangle


def test_fill_overlay_effect_is_not_rejected_for_nested_solid_fill() -> None:
    xml = (
        "<a:effectLst>"
        '<a:fillOverlay blend="screen">'
        "<a:solidFill><a:srgbClr val=\"EFF9FF\"><a:alpha val=\"48800\"/></a:srgbClr></a:solidFill>"
        "</a:fillOverlay>"
        "<a:glow rad=\"26669\"><a:srgbClr val=\"EFF9FF\"><a:alpha val=\"16592\"/></a:srgbClr></a:glow>"
        "</a:effectLst>"
    )

    assert (
        is_invalid_custom_effect_xml(
            xml,
            invalid_substrings=(
                "svg2ooxml:sourcegraphic",
                "svg2ooxml:sourcealpha",
                "svg2ooxml:emf",
                "svg2ooxml:raster",
            ),
        )
        is False
    )


def test_bare_solid_fill_fragment_is_rejected() -> None:
    xml = "<a:solidFill><a:srgbClr val=\"FF0000\"/></a:solidFill>"

    assert (
        is_invalid_custom_effect_xml(
            xml,
            invalid_substrings=(
                "svg2ooxml:sourcegraphic",
                "svg2ooxml:sourcealpha",
                "svg2ooxml:emf",
                "svg2ooxml:raster",
            ),
        )
        is True
    )


def test_shape_renderer_ignores_invalid_policy_metadata() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(0.0, 0.0, 10.0, 10.0),
        fill=SolidPaint("336699"),
        metadata={"policy": "not-a-policy"},
    )

    result = writer.render_scene([rect])

    assert "<p:sp" in result.slide_xml


def test_shape_renderer_skips_malformed_filter_hex_fallback() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(0.0, 0.0, 10.0, 10.0),
        fill=SolidPaint("336699"),
        metadata={
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [{"type": "raster", "data_hex": "not-hex"}]
                    }
                }
            },
        },
    )

    result = writer.render_scene([rect])

    assert "<p:sp" in result.slide_xml


def test_shape_renderer_applies_gradient_fallback_to_frozen_paths_without_rasterizer() -> None:
    writer = DrawingMLWriter()
    writer._rasterizer = None
    gradient = RadialGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "0000FF"),
        ],
        center=(0.5, 0.5),
        radius=0.5,
        policy_decision="rasterize_nonuniform",
    )
    path = IRPath(
        segments=[
            LineSegment(Point(0.0, 0.0), Point(10.0, 0.0)),
            LineSegment(Point(10.0, 0.0), Point(10.0, 10.0)),
            LineSegment(Point(10.0, 10.0), Point(0.0, 0.0)),
        ],
        fill=gradient,
    )

    result = writer.render_scene([path])

    assert 'val="800080"' in result.slide_xml
