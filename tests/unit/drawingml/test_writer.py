"""Tests for the DrawingML writer."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from lxml import etree as ET
from PIL import Image as PILImage

from svg2ooxml.core.ir import IRScene
from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.core.pipeline.navigation import (
    NavigationKind,
    NavigationSpec,
    SlideTarget,
)
from svg2ooxml.drawingml.writer import EMU_PER_PX, DrawingMLWriter, px_to_emu
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    TransformType,
)
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    PatternPaint,
    SolidPaint,
    Stroke,
)
from svg2ooxml.ir.scene import (
    ClipRef,
    ClipStrategy,
    Group,
    Image,
    MaskDefinition,
    MaskInstance,
    MaskRef,
)
from svg2ooxml.ir.scene import (
    Path as IRPath,
)
from svg2ooxml.ir.shapes import Line, Polygon, Polyline, Rectangle
from svg2ooxml.ir.text import (
    EmbeddedFontPlan,
    Run,
    TextAnchor,
    TextFrame,
    WordArtCandidate,
)


def test_render_scene_from_ir_reports_slide_size() -> None:
    writer = DrawingMLWriter()
    scene = IRScene(elements=[], width_px=120, height_px=80)

    result = writer.render_scene_from_ir(scene)

    assert result.slide_size == (int(120 * EMU_PER_PX), int(80 * EMU_PER_PX))
    assert not result.assets.media


def test_render_scene_renders_rectangle() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(x=10, y=5, width=20, height=15), fill=SolidPaint("FF0000")
    )

    result = writer.render_scene([rect])
    xml = result.slide_xml

    assert "Rectangle 2" in xml
    assert f'x="{int(10 * EMU_PER_PX)}"' in xml
    assert "FF0000" in xml


def test_render_rectangle_with_pattern_tile_registers_media() -> None:
    """Rectangle with PatternPaint tile_image gets blipFill with registered media."""
    writer = DrawingMLWriter()
    tile_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # fake PNG header + padding
    paint = PatternPaint(
        pattern_id="tile_pat",
        tile_image=tile_data,
        tile_width_px=8,
        tile_height_px=8,
    )
    rect = Rectangle(bounds=Rect(x=0, y=0, width=50, height=50), fill=paint)

    result = writer.render_scene([rect])
    xml = result.slide_xml

    # blipFill should be present with r:embed referencing registered media
    assert "<a:blipFill" in xml
    assert "<a:tile" in xml
    # media should be registered
    assert len(result.assets.media) == 1


def test_render_path_with_pattern_tile_registers_media() -> None:
    writer = DrawingMLWriter()
    tile_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    paint = PatternPaint(
        pattern_id="tile_pat_path",
        tile_image=tile_data,
        tile_width_px=8,
        tile_height_px=8,
    )
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(50, 0)),
            LineSegment(Point(50, 0), Point(50, 50)),
            LineSegment(Point(50, 50), Point(0, 50)),
            LineSegment(Point(0, 50), Point(0, 0)),
        ],
        fill=paint,
    )

    result = writer.render_scene([path])
    xml = result.slide_xml

    assert "<a:blipFill" in xml
    assert "<a:tile" in xml
    assert len(result.assets.media) == 1


def test_render_scene_from_ir_preserves_filter_png_alpha_by_default() -> None:
    writer = DrawingMLWriter()
    image = PILImage.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    rect = Rectangle(
        bounds=Rect(x=0, y=0, width=10, height=10),
        fill=SolidPaint("FF0000"),
        metadata={
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [
                            {
                                "type": "raster",
                                "data": png_bytes,
                                "relationship_id": "rIdRasterTest",
                            }
                        ]
                    }
                }
            },
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "filter_metadata": {
                "blur": {"bounds": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}}
            },
        },
    )
    scene = IRScene(elements=[rect], width_px=20, height_px=20, background_color="FFFFFF")

    result = writer.render_scene_from_ir(scene)

    filter_media = next(
        asset for asset in result.assets.media if asset.relationship_id == "rIdRasterTest"
    )
    preserved = PILImage.open(BytesIO(filter_media.data)).convert("RGBA")
    assert preserved.getpixel((0, 0)) == (255, 0, 0, 255)
    assert preserved.getpixel((1, 0)) == (0, 0, 0, 0)


def test_render_scene_from_ir_flattens_filter_png_assets_when_requested() -> None:
    writer = DrawingMLWriter()
    image = PILImage.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    rect = Rectangle(
        bounds=Rect(x=0, y=0, width=10, height=10),
        fill=SolidPaint("FF0000"),
        metadata={
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [
                            {
                                "type": "raster",
                                "data": png_bytes,
                                "relationship_id": "rIdRasterTest",
                                "flatten_for_powerpoint": True,
                            }
                        ]
                    }
                }
            },
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "filter_metadata": {
                "blur": {"bounds": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}}
            },
        },
    )
    scene = IRScene(elements=[rect], width_px=20, height_px=20, background_color="FFFFFF")

    result = writer.render_scene_from_ir(scene)

    filter_media = next(
        asset for asset in result.assets.media if asset.relationship_id == "rIdRasterTest"
    )
    flattened = PILImage.open(BytesIO(filter_media.data)).convert("RGBA")
    assert flattened.getpixel((0, 0)) == (255, 0, 0, 255)
    assert flattened.getpixel((1, 0)) == (255, 255, 255, 255)


def test_render_scene_from_ir_flattens_filter_png_assets_against_scene_background() -> None:
    writer = DrawingMLWriter()
    image = PILImage.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    rect = Rectangle(
        bounds=Rect(x=0, y=0, width=10, height=10),
        fill=SolidPaint("FF0000"),
        metadata={
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [
                            {
                                "type": "raster",
                                "data": buffer.getvalue(),
                                "relationship_id": "rIdRasterTest",
                                "flatten_for_powerpoint": True,
                            }
                        ]
                    }
                }
            },
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "filter_metadata": {
                "blur": {"bounds": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}}
            },
        },
    )
    scene = IRScene(elements=[rect], width_px=20, height_px=20, background_color="00FF00")

    result = writer.render_scene_from_ir(scene)

    filter_media = next(
        asset for asset in result.assets.media if asset.relationship_id == "rIdRasterTest"
    )
    flattened = PILImage.open(BytesIO(filter_media.data)).convert("RGBA")
    assert flattened.getpixel((1, 0)) == (0, 255, 0, 255)


def test_render_reuses_identical_pattern_tile_media_on_slide() -> None:
    writer = DrawingMLWriter()
    tile_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    paint = PatternPaint(
        pattern_id="tile_pat_shared",
        tile_image=tile_data,
        tile_width_px=8,
        tile_height_px=8,
    )
    scene = [
        Rectangle(bounds=Rect(x=0, y=0, width=40, height=40), fill=paint),
        Rectangle(bounds=Rect(x=50, y=0, width=40, height=40), fill=paint),
    ]

    result = writer.render_scene(scene)
    media = list(result.assets.media)

    assert len(media) == 1
    assert result.slide_xml.count(f'r:embed="{media[0].relationship_id}"') == 2


def test_render_rectangle_with_pattern_preset_no_media() -> None:
    """Rectangle with PatternPaint preset (no tile) uses pattFill, no media."""
    writer = DrawingMLWriter()
    paint = PatternPaint(
        pattern_id="preset_pat",
        preset="horz",
        foreground="FF0000",
        background="FFFFFF",
    )
    rect = Rectangle(bounds=Rect(x=0, y=0, width=50, height=50), fill=paint)

    result = writer.render_scene([rect])
    xml = result.slide_xml

    assert "<a:pattFill" in xml
    assert 'prst="horz"' in xml
    assert "blipFill" not in xml
    assert not result.assets.media


def test_render_scene_renders_line() -> None:
    writer = DrawingMLWriter()
    line = Line(
        start=Point(10, 12),
        end=Point(40, 24),
        stroke=Stroke(paint=SolidPaint("336699"), width=2.5),
    )

    result = writer.render_scene([line])
    xml = result.slide_xml

    assert "<p:cxnSp>" in xml
    assert "Line 2" in xml
    assert 'prst="line"' in xml
    assert 'val="336699"' in xml


def test_render_scene_renders_polyline() -> None:
    writer = DrawingMLWriter()
    polyline = Polyline(
        points=[Point(0, 0), Point(20, 10), Point(40, 0)],
        stroke=Stroke(paint=SolidPaint("FF00FF"), width=1.5),
    )

    result = writer.render_scene([polyline])
    xml = result.slide_xml

    assert "Polyline 2" in xml
    assert xml.count("<a:lnTo>") >= 2
    assert 'val="FF00FF"' in xml


def test_render_scene_renders_polygon() -> None:
    writer = DrawingMLWriter()
    polygon = Polygon(
        points=[Point(10, 10), Point(30, 10), Point(20, 30)],
        fill=SolidPaint("00FF00"),
        stroke=Stroke(paint=SolidPaint("000000"), width=1.0),
    )

    result = writer.render_scene([polygon])
    xml = result.slide_xml

    assert "Polygon 2" in xml
    assert "<a:close/>" in xml
    assert 'val="00FF00"' in xml


def test_render_scene_renders_rounded_rectangle_with_adjustment() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(x=0, y=0, width=100, height=50),
        fill=SolidPaint("00FF00"),
        corner_radius=10.0,
    )

    result = writer.render_scene([rect])
    xml = result.slide_xml

    assert 'prst="roundRect"' in xml
    assert '<a:gd name="adj" fmla="val 20000"/>' in xml


def test_render_scene_renders_textframe() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=12, rgb="00AAFF")],
        baseline_shift=0.0,
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert "Text 2" in xml
    assert "Hello" in xml
    assert "00AAFF" in xml
    assert not result.assets.fonts


def test_render_textframe_rtl_explicit_direction() -> None:
    """TextFrame with direction='rtl' emits rtl='1' on pPr."""
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="مرحبا", font_family="Arial", font_size_pt=12, rgb="000000")],
        direction="rtl",
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert 'rtl="1"' in xml
    # START anchor in RTL should become right-aligned
    assert 'algn="r"' in xml


def test_render_textframe_ltr_no_rtl_attr() -> None:
    """TextFrame with direction='ltr' does not emit rtl attribute."""
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=12, rgb="000000")],
        direction="ltr",
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert 'rtl="1"' not in xml
    assert 'algn="l"' in xml


def test_render_textframe_arabic_auto_detects_rtl() -> None:
    """TextFrame with Arabic text auto-detects RTL when no direction set."""
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[
            Run(
                text="مرحبا بالعالم", font_family="Arial", font_size_pt=12, rgb="000000"
            )
        ],
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert 'rtl="1"' in xml
    assert 'algn="r"' in xml


def test_render_textframe_rtl_end_anchor_becomes_left_align() -> None:
    """In RTL, END anchor maps to left alignment."""
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.END,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="مرحبا", font_family="Arial", font_size_pt=12, rgb="000000")],
        direction="rtl",
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert 'rtl="1"' in xml
    assert 'algn="l"' in xml


def test_render_textframe_renders_multiple_runs() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(text="Hello", font_family="Arial", font_size_pt=12, rgb="000000"),
            Run(
                text="World",
                font_family="Arial",
                font_size_pt=12,
                rgb="FF0000",
                bold=True,
            ),
        ],
        baseline_shift=0.0,
    )

    result = writer.render_scene([frame])
    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    runs = root.findall(".//a:r", ns)
    assert len(runs) == 2
    second = ET.tostring(runs[1], encoding="unicode")
    assert 'val="FF0000"' in second
    assert 'b="1"' in second


def test_text_runs_emit_font_slots_and_kerning() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(
                text="Hi",
                font_family="Inter",
                font_size_pt=18.0,
                kerning=0.12,
                letter_spacing=0.05,
                language="en-US",
                east_asian_font="MS Gothic",
                complex_script_font="Nirmala UI",
            )
        ],
        baseline_shift=0.0,
    )

    result = writer.render_scene([frame])
    xml = result.slide_xml

    assert 'kern="120"' in xml
    assert 'spc="50"' in xml
    assert 'lang="en-US"' in xml
    assert '<a:ea typeface="MS Gothic"/>' in xml
    assert '<a:cs typeface="Nirmala UI"/>' in xml


def test_text_run_font_slots_are_escaped_once() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(
                text="Hi",
                font_family="Rock & Roll",
                font_size_pt=18.0,
                language="en&GB",
                east_asian_font="East & Asian",
                complex_script_font="Script & Serif",
            )
        ],
    )

    xml = writer.render_scene([frame]).slide_xml

    assert 'typeface="Rock &amp; Roll"' in xml
    assert 'typeface="Rock &amp;amp; Roll"' not in xml
    assert 'lang="en&amp;GB"' in xml
    assert 'lang="en&amp;amp;GB"' not in xml


def test_invalid_text_rotation_metadata_is_ignored() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[Run(text="Hi", font_family="Arial", font_size_pt=18.0)],
        metadata={"text_rotation_deg": "bad"},
    )

    xml = writer.render_scene([frame]).slide_xml

    assert "<a:t>Hi</a:t>" in xml
    assert ' rot="' not in xml


def test_render_scene_renders_path_custom_geometry() -> None:
    writer = DrawingMLWriter()
    segments = [
        LineSegment(Point(0, 0), Point(50, 0)),
        BezierSegment(
            start=Point(50, 0),
            control1=Point(60, 10),
            control2=Point(40, 20),
            end=Point(30, 10),
        ),
    ]
    path = IRPath(segments=segments, fill=SolidPaint("0000FF"))

    xml = writer.render_scene([path]).slide_xml

    assert "<a:custGeom>" in xml
    assert "<a:moveTo>" in xml
    assert "<a:lnTo>" in xml
    assert "<a:cubicBezTo>" in xml


def test_render_path_names_exclude_policy_annotations() -> None:
    """Shape names must not contain debug metadata — PowerPoint displays them."""
    writer = DrawingMLWriter()
    segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
    ]
    path = IRPath(segments=segments, fill=SolidPaint("000000"))
    path.metadata.setdefault("policy", {})["geometry"] = {
        "simplified": True,
        "render_mode": "native",
    }

    result = writer.render_scene([path])
    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    names = [elem.attrib["name"] for elem in root.findall(".//p:cNvPr", ns)]
    assert all("render_mode" not in v for v in names)
    assert all("simplified" not in v for v in names)


def test_render_textframe_notes_policy_metadata(caplog) -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[
            Run(text="Policy!", font_family=TEST_FONT, font_size_pt=12, rgb="FF00FF")
        ],
        baseline_shift=0.0,
        metadata={
            "policy": {
                "text": {"rendering_behavior": "outline", "font_fallback": "Arial"}
            }
        },
    )

    with caplog.at_level("DEBUG"):
        _result = writer.render_scene([frame])

    debug_notes = [
        rec.getMessage() for rec in caplog.records if rec.levelname == "DEBUG"
    ]
    assert any("rendering_behavior=outline" in message for message in debug_notes)
    assert any("font_fallback=Arial" in message for message in debug_notes)


def test_render_wordart_frame_uses_warp_template() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 40),
        runs=[Run(text="WAVE", font_family=TEST_FONT, font_size_pt=28.0, bold=True)],
        wordart_candidate=WordArtCandidate(
            preset="textWave1", confidence=0.9, fallback_strategy="vector_outline"
        ),
        metadata={"wordart": {"prefer_native": True}},
    )

    xml = writer.render_scene([frame]).slide_xml

    assert "WordArt 2" in xml
    assert 'prst="textWave1"' in xml
    assert "WAVE" in xml
    assert "<a:normAutofit/>" not in xml


def test_render_wordart_frame_uses_tighter_height_for_flat_presets() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(10, 20, 120, 56),
        runs=[Run(text="WAVE", font_family=TEST_FONT, font_size_pt=28.0, bold=True)],
        wordart_candidate=WordArtCandidate(
            preset="textWave1", confidence=0.9, fallback_strategy="vector_outline"
        ),
        metadata={"wordart": {"prefer_native": True}},
    )

    xml = writer.render_scene([frame]).slide_xml
    root = ET.fromstring(xml.encode("utf-8"))
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    ext = root.find(".//p:sp/p:spPr/a:xfrm/a:ext", ns)
    off = root.find(".//p:sp/p:spPr/a:xfrm/a:off", ns)

    assert ext is not None
    assert off is not None
    expected_height = round(28.0 * (96.0 / 72.0) * 1.1 * EMU_PER_PX)
    expected_y = round(
        (20.0 + ((56.0 - (28.0 * (96.0 / 72.0) * 1.1)) / 2.0)) * EMU_PER_PX
    )
    assert int(ext.attrib["cy"]) == expected_height
    assert int(off.attrib["y"]) == expected_y


def test_render_wordart_frame_preserves_height_for_circle_presets() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(10, 20, 120, 56),
        runs=[Run(text="ROUND", font_family=TEST_FONT, font_size_pt=28.0, bold=True)],
        wordart_candidate=WordArtCandidate(
            preset="textCircle", confidence=0.9, fallback_strategy="vector_outline"
        ),
        metadata={"wordart": {"prefer_native": True}},
    )

    xml = writer.render_scene([frame]).slide_xml
    root = ET.fromstring(xml.encode("utf-8"))
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    ext = root.find(".//p:sp/p:spPr/a:xfrm/a:ext", ns)

    assert ext is not None
    assert int(ext.attrib["cy"]) == int(56.0 * EMU_PER_PX)


def test_render_scene_from_ir_uses_wordart_for_text_path_fixture() -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "corpus"
        / "kelvin_lawrence"
        / "text-path.svg"
    )
    parser = SVGParser(ParserConfig())
    parse_result = parser.parse(fixture.read_text(), source_path=str(fixture))
    scene = convert_parser_output(parse_result)

    writer = DrawingMLWriter()
    result = writer.render_scene_from_ir(scene)

    assert "Some text drawn on a curved path!" in result.slide_xml
    assert "prstTxWarp" in result.slide_xml


def test_render_scene_from_ir_suppresses_w3c_test_frame() -> None:
    writer = DrawingMLWriter()
    scene = IRScene(
        elements=[
            Rectangle(
                bounds=Rect(1, 1, 478, 358),
                fill=None,
                stroke=Stroke(paint=SolidPaint("000000"), width=1.0),
                metadata={"element_ids": ["test-frame"]},
                element_id="test-frame",
            ),
            Rectangle(bounds=Rect(20, 20, 40, 30), fill=SolidPaint("FF0000")),
        ],
        width_px=480,
        height_px=360,
        metadata={"source_path": "/tmp/project/tests/svg/animate-elem-02-t.svg"},
    )

    result = writer.render_scene_from_ir(scene)

    assert len(result.shape_xml) == 1
    assert "FF0000" in result.slide_xml
    assert "000000" not in result.slide_xml


def test_render_scene_from_ir_preserves_test_frame_outside_w3c_corpus() -> None:
    writer = DrawingMLWriter()
    scene = IRScene(
        elements=[
            Rectangle(
                bounds=Rect(1, 1, 478, 358),
                fill=None,
                stroke=Stroke(paint=SolidPaint("000000"), width=1.0),
                metadata={"element_ids": ["test-frame"]},
                element_id="test-frame",
            )
        ],
        width_px=480,
        height_px=360,
        metadata={"source_path": "/tmp/project/tests/visual/fixtures/example.svg"},
    )

    result = writer.render_scene_from_ir(scene)

    assert len(result.shape_xml) == 1
    assert "000000" in result.slide_xml


def test_writer_collects_font_embedding_plans() -> None:
    writer = DrawingMLWriter()
    plan = EmbeddedFontPlan(
        font_family="Inter",
        requires_embedding=True,
        subset_strategy="glyph",
        glyph_count=4,
        metadata={"font_path": "/fonts/Inter.ttf"},
    )
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="Test", font_family="Inter", font_size_pt=14.0)],
        embedding_plan=plan,
    )

    result = writer.render_scene([frame])

    fonts = list(result.assets.fonts)
    assert fonts
    entry = fonts[0]
    assert entry.shape_id == 2
    assert entry.plan == plan


def test_render_image_registers_media() -> None:
    writer = DrawingMLWriter()
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 20, 20),
        data=b"EMF",
        format="emf",
        metadata={"policy": {"geometry": {"render_mode": "emf"}}},
    )

    result = writer.render_scene([image])

    assert "<p:pic>" in result.slide_xml
    media = list(result.assets.media)
    assert media
    assert media[0].content_type == "image/x-emf"


def test_render_image_png_content_type() -> None:
    writer = DrawingMLWriter()
    image = Image(
        origin=Point(5, 5),
        size=Rect(0, 0, 10, 10),
        data=b"PNG",
        format="png",
    )

    result = writer.render_scene([image])

    media = list(result.assets.media)
    assert media[0].content_type == "image/png"


def test_writer_registers_filter_assets() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(bounds=Rect(0, 0, 20, 20), fill=SolidPaint("FFFFFF"))
    rect.metadata = {
        "policy": {
            "media": {
                "filter_assets": {
                    "glow": [
                        {
                            "type": "emf",
                            "data_hex": "DEADBEEF",
                            "relationship_id": "rIdCustom",
                        }
                    ]
                }
            }
        }
    }
    rect.effects.append(
        CustomEffect(drawingml='<a:effectLst><a:blur rad="1000"/></a:effectLst>')
    )

    first = writer.render_scene([rect])

    assert any(item.relationship_id == "rIdCustom" for item in first.assets.media)
    second = writer.render_scene([rect])
    assert "<a:effectLst>" in second.slide_xml


def test_leaf_group_with_filter_fallback_renders_single_picture() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Rectangle(bounds=Rect(0, 0, 20, 20), fill=SolidPaint("4472C4")),
            Rectangle(bounds=Rect(10, 10, 20, 20), fill=SolidPaint("ED7D31")),
        ],
        metadata={
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "filter_metadata": {
                "blur": {"bounds": {"x": 0.0, "y": 0.0, "width": 30.0, "height": 30.0}}
            },
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [
                            {
                                "type": "raster",
                                "data": b"\x89PNG\r\n\x1a\n",
                                "relationship_id": "rIdFilterBlur",
                            }
                        ]
                    }
                }
            },
        },
    )

    result = writer.render_scene([group])

    assert len(result.shape_xml) == 1
    assert result.shape_xml[0].startswith("<p:pic>")
    assert 'r:embed="rIdFilterBlur"' in result.slide_xml


def test_shape_filter_fallback_uses_filter_expanded_bounds() -> None:
    writer = DrawingMLWriter()
    buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, format="PNG")
    rect = Rectangle(
        bounds=Rect(10, 20, 30, 40),
        fill=SolidPaint("4472C4"),
        metadata={
            "filters": [{"id": "blur", "fallback": "bitmap"}],
            "filter_metadata": {
                "blur": {"bounds": {"x": 5.0, "y": 15.0, "width": 50.0, "height": 60.0}}
            },
            "policy": {
                "media": {
                    "filter_assets": {
                        "blur": [
                            {
                                "type": "raster",
                                "data": buffer.getvalue(),
                                "relationship_id": "rIdFilterBlur",
                            }
                        ]
                    }
                }
            },
        },
    )

    result = writer.render_scene([rect])

    assert len(result.shape_xml) == 1
    assert result.shape_xml[0].startswith("<p:pic>")

    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    off = root.find(".//p:pic/p:spPr/a:xfrm/a:off", ns)
    ext = root.find(".//p:pic/p:spPr/a:xfrm/a:ext", ns)

    assert off is not None
    assert ext is not None
    assert off.attrib == {"x": str(px_to_emu(5.0)), "y": str(px_to_emu(15.0))}
    assert ext.attrib == {"cx": str(px_to_emu(50.0)), "cy": str(px_to_emu(60.0))}


def test_writer_preserves_effect_dag_custom_effect() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(bounds=Rect(0, 0, 20, 20), fill=SolidPaint("FFFFFF"))
    rect.effects.append(
        CustomEffect(
            drawingml=(
                "<a:effectDag><a:cont/><a:alphaModFix><a:cont/>"
                '<a:effectLst><a:blur rad="1000"/></a:effectLst>'
                "</a:alphaModFix></a:effectDag>"
            )
        )
    )

    result = writer.render_scene([rect])

    assert "<a:effectDag>" in result.slide_xml
    assert "<a:alphaModFix>" in result.slide_xml


def test_render_linear_gradient_fill() -> None:
    writer = DrawingMLWriter()
    gradient = LinearGradientPaint(
        stops=[
            GradientStop(offset=0.0, rgb="000000", opacity=1.0),
            GradientStop(offset=1.0, rgb="FFFFFF", opacity=0.5),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    rect = Rectangle(bounds=Rect(0, 0, 20, 10), fill=gradient)

    xml = writer.render_scene([rect]).slide_xml

    assert "<a:gradFill" in xml
    assert "<a:lin" in xml
    assert 'pos="100000"' in xml


def test_render_path_with_arrow_markers() -> None:
    writer = DrawingMLWriter()
    segments = [LineSegment(Point(0, 0), Point(50, 0))]
    stroke = Stroke(paint=SolidPaint("000000"), width=2.0)
    path = IRPath(
        segments=segments,
        fill=None,
        stroke=stroke,
        metadata={"markers": {"start": "arrow", "end": "arrow"}},
    )

    xml = writer.render_scene([path]).slide_xml

    assert "<a:headEnd" in xml
    assert "<a:tailEnd" in xml
    assert 'type="arrow"' in xml


def test_render_path_with_geometry_marker_profiles() -> None:
    writer = DrawingMLWriter()
    segments = [LineSegment(Point(0, 0), Point(50, 0))]
    stroke = Stroke(paint=SolidPaint("000000"), width=2.0)
    path = IRPath(
        segments=segments,
        fill=None,
        stroke=stroke,
        metadata={
            "markers": {"start": "m1", "end": "m2"},
            "marker_profiles": {
                "start": {"type": "oval", "size": "lg", "source": "geometry"},
                "end": {"type": "diamond", "size": "sm", "source": "geometry"},
            },
        },
    )

    xml = writer.render_scene([path]).slide_xml

    assert '<a:headEnd type="diamond" w="sm" len="sm"/>' in xml
    assert '<a:tailEnd type="oval" w="lg" len="lg"/>' in xml


def test_render_path_applies_marker_clip_metadata() -> None:
    """Non-standard <a:clipPath> is no longer emitted (ECMA-376 compliance)."""
    writer = DrawingMLWriter()
    segments = [LineSegment(Point(0, 0), Point(10, 0))]
    stroke = Stroke(paint=SolidPaint("000000"), width=1.0)
    metadata = {
        "marker_clip": {"x": 0.0, "y": 0.0, "width": 2.0, "height": 1.0},
        "marker_overflow": "hidden",
    }
    path = IRPath(
        segments=segments,
        fill=None,
        stroke=stroke,
        metadata=metadata,
    )

    xml = writer.render_scene([path]).slide_xml

    # Non-standard element must not appear in output.
    assert "<a:clipPath>" not in xml
    # Shape should still render.
    assert "<p:sp>" in xml


def test_shape_navigation_embeds_hyperlink_metadata() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(bounds=Rect(0, 0, 20, 10), fill=SolidPaint("123456"))
    rect.metadata["navigation"] = NavigationSpec(
        kind=NavigationKind.EXTERNAL,
        href="https://example.com",
        tooltip="Example",
    ).as_dict()

    result = writer.render_scene([rect])

    assert "a:hlinkClick" in result.slide_xml
    navigation_assets = list(result.assets.navigation)
    assert navigation_assets
    asset = navigation_assets[0]
    assert (
        asset.relationship_type
        == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    )
    assert asset.target == "https://example.com"
    assert asset.scope == "shape"


def test_text_run_navigation_creates_relationships() -> None:
    writer = DrawingMLWriter()
    nav_external = NavigationSpec(
        kind=NavigationKind.EXTERNAL, href="https://example.com"
    )
    nav_slide = NavigationSpec(kind=NavigationKind.SLIDE, slide=SlideTarget(index=3))
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(
                text=RUN_TEXT_EXTERNAL,
                font_family=TEST_FONT,
                font_size_pt=14.0,
                navigation=nav_external,
            ),
            Run(text=" ", font_family=TEST_FONT, font_size_pt=14.0),
            Run(
                text=RUN_TEXT_SLIDE,
                font_family=TEST_FONT,
                font_size_pt=14.0,
                navigation=nav_slide,
            ),
        ],
    )

    result = writer.render_scene([frame])

    navigation_assets = list(result.assets.navigation)
    assert "a:hlinkClick" in result.slide_xml
    assert len(navigation_assets) == 2
    scopes = {asset.scope for asset in navigation_assets}
    assert scopes == {"text_run"}
    external_asset = next(
        asset for asset in navigation_assets if asset.target_mode == "External"
    )
    assert external_asset.target == "https://example.com"
    slide_asset = next(
        asset
        for asset in navigation_assets
        if asset.relationship_type
        == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
    )
    assert slide_asset.target.endswith("slide3.xml")


def test_path_clip_path_serialisation() -> None:
    """Non-standard <a:clipPath> is no longer emitted; clip bounds used for diagnostics."""
    writer = DrawingMLWriter()
    clip_segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
        LineSegment(Point(10, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
    ]
    clip_ref = ClipRef(
        clip_id="clip1",
        path_segments=tuple(clip_segments),
        bounding_box=Rect(0, 0, 10, 10),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(20, 0)),
            LineSegment(Point(20, 0), Point(20, 10)),
            LineSegment(Point(20, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("00FF00"),
        clip=clip_ref,
    )

    result = writer.render_scene([path])

    # Non-standard element must not appear in output.
    assert "<a:clipPath>" not in result.slide_xml
    # Shape still renders.
    assert "<p:sp>" in result.slide_xml
    # Clip diagnostic is recorded.
    assert any(
        "clip1" in msg.lower() or "clip" in msg.lower()
        for msg in result.assets.diagnostics
    )


def test_mask_approximated_to_clip_path() -> None:
    """Non-standard <a:mask> no longer emitted; native geometry recorded in diagnostics."""
    writer = DrawingMLWriter()
    mask_def = MaskDefinition(
        mask_id="mask1",
        bounding_box=Rect(2, 2, 6, 6),
        segments=(
            LineSegment(Point(2, 2), Point(8, 2)),
            LineSegment(Point(8, 2), Point(8, 8)),
            LineSegment(Point(8, 8), Point(2, 8)),
            LineSegment(Point(2, 8), Point(2, 2)),
        ),
    )
    mask_ref = MaskRef(
        mask_id="mask1", definition=mask_def, target_bounds=mask_def.bounding_box
    )
    mask_instance = MaskInstance(mask=mask_ref, bounds=mask_def.bounding_box)
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("FF0000"),
        mask=mask_ref,
        mask_instance=mask_instance,
    )

    result = writer.render_scene([path])

    # Non-standard elements must not appear.
    assert "<a:mask>" not in result.slide_xml
    # Shape still renders.
    assert "<p:sp>" in result.slide_xml
    # Mask diagnostic records the fallback.
    assert any(
        "mask1" in msg.lower() or "native geometry" in msg.lower()
        for msg in result.assets.diagnostics
    )


def test_mask_raster_fallback_emits_asset() -> None:
    """Raster mask asset is registered but non-standard <a:mask> is not emitted."""
    writer = DrawingMLWriter()
    mask_def = MaskDefinition(
        mask_id="mask-raster",
        bounding_box=Rect(0, 0, 10, 10),
    )
    mask_ref = MaskRef(
        mask_id="mask-raster", definition=mask_def, target_bounds=mask_def.bounding_box
    )
    mask_instance = MaskInstance(mask=mask_ref, bounds=mask_def.bounding_box)
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("FF0000"),
        mask=mask_ref,
        mask_instance=mask_instance,
        metadata={
            "mask": {
                "strategy": "raster",
                "classification": "raster",
                "requires_raster": True,
                "bounds_px": (0.0, 0.0, 10.0, 10.0),
                "element_bbox": Rect(0, 0, 10, 10),
                "fallback_order": ("raster",),
            }
        },
    )

    result = writer.render_scene([path])

    # Non-standard element must not appear.
    assert "<a:mask" not in result.slide_xml
    # Asset is still registered for potential future use.
    mask_assets = list(result.assets.iter_masks())
    assert len(mask_assets) == 1
    asset = mask_assets[0]
    assert asset["content_type"] == "image/png"
    assert asset["part_name"].startswith("/ppt/masks/")
    assert any("Raster fallback emitted" in msg for msg in result.assets.diagnostics)


def test_mask_policy_emf_emits_asset() -> None:
    """EMF mask asset is registered but non-standard <a:mask> is not emitted."""
    writer = DrawingMLWriter()
    mask_def = MaskDefinition(
        mask_id="mask-emf",
        bounding_box=Rect(0, 0, 8, 8),
        segments=(
            LineSegment(Point(0, 0), Point(8, 0)),
            LineSegment(Point(8, 0), Point(8, 8)),
            LineSegment(Point(8, 8), Point(0, 8)),
            LineSegment(Point(0, 8), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(
        mask_id="mask-emf", definition=mask_def, target_bounds=mask_def.bounding_box
    )
    mask_instance = MaskInstance(mask=mask_ref, bounds=mask_def.bounding_box)
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(8, 0)),
            LineSegment(Point(8, 0), Point(8, 8)),
            LineSegment(Point(8, 8), Point(0, 8)),
            LineSegment(Point(0, 8), Point(0, 0)),
        ],
        fill=SolidPaint("FF0000"),
        mask=mask_ref,
        mask_instance=mask_instance,
        metadata={
            "mask": {
                "strategy": "policy_emf",
                "classification": "vector",
                "fallback_order": ("emf", "raster"),
                "requires_emf": True,
                "bounds_px": (0.0, 0.0, 8.0, 8.0),
                "element_bbox": Rect(0, 0, 8, 8),
            }
        },
    )

    result = writer.render_scene([path])

    # Non-standard element must not appear.
    assert "<a:mask" not in result.slide_xml
    # Asset is still registered for potential future use.
    mask_assets = list(result.assets.iter_masks())
    assert len(mask_assets) == 1
    asset = mask_assets[0]
    assert asset["content_type"] == "image/x-emf"
    assert any("EMF fallback emitted" in msg for msg in result.assets.diagnostics)


def test_mask_policy_prefers_mimic_before_emf() -> None:
    """Mimic strategy wins over EMF; no non-standard XML emitted, no assets registered."""
    writer = DrawingMLWriter()
    mask_def = MaskDefinition(
        mask_id="mask-mimic",
        bounding_box=Rect(0, 0, 6, 6),
        segments=(
            LineSegment(Point(0, 0), Point(6, 0)),
            LineSegment(Point(6, 0), Point(6, 6)),
            LineSegment(Point(6, 6), Point(0, 6)),
            LineSegment(Point(0, 6), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(
        mask_id="mask-mimic", definition=mask_def, target_bounds=mask_def.bounding_box
    )
    mask_instance = MaskInstance(mask=mask_ref, bounds=mask_def.bounding_box)
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(6, 0)),
            LineSegment(Point(6, 0), Point(6, 6)),
            LineSegment(Point(6, 6), Point(0, 6)),
            LineSegment(Point(0, 6), Point(0, 0)),
        ],
        fill=SolidPaint("FF0000"),
        mask=mask_ref,
        mask_instance=mask_instance,
        metadata={
            "mask": {
                "classification": "vector",
                "fallback_order": ("mimic", "emf"),
            }
        },
    )

    result = writer.render_scene([path])

    # Non-standard element must not appear.
    assert "<a:mask" not in result.slide_xml
    # Mimic doesn't register mask assets.
    assert not list(result.assets.iter_masks())
    assert any("mimic fallback emitted" in msg for msg in result.assets.diagnostics)


def test_apply_mask_alpha_scales_solid_fill_opacity() -> None:
    """_apply_mask_alpha multiplies alpha into SolidPaint opacity."""
    from svg2ooxml.drawingml.writer import _apply_mask_alpha

    path = IRPath(
        segments=[LineSegment(Point(0, 0), Point(10, 10))],
        fill=SolidPaint(rgb="FF0000", opacity=0.8),
        stroke=Stroke(paint=SolidPaint(rgb="00FF00", opacity=1.0), width=2.0),
    )

    result = _apply_mask_alpha(path, 0.5)

    # Fill opacity: 0.8 * 0.5 = 0.4
    assert abs(result.fill.opacity - 0.4) < 0.001
    # Stroke paint opacity: 1.0 * 0.5 = 0.5
    assert abs(result.stroke.paint.opacity - 0.5) < 0.001


def test_apply_mask_alpha_scales_gradient_stop_opacities() -> None:
    """_apply_mask_alpha multiplies alpha into each gradient stop's opacity."""
    from svg2ooxml.drawingml.writer import _apply_mask_alpha

    gradient = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000", opacity=1.0),
            GradientStop(1.0, "00FF00", opacity=0.6),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    path = IRPath(
        segments=[LineSegment(Point(0, 0), Point(10, 10))],
        fill=gradient,
    )

    result = _apply_mask_alpha(path, 0.5)

    assert abs(result.fill.stops[0].opacity - 0.5) < 0.001  # 1.0 * 0.5
    assert abs(result.fill.stops[1].opacity - 0.3) < 0.001  # 0.6 * 0.5


def test_apply_mask_alpha_removes_mask_ref() -> None:
    """_apply_mask_alpha clears mask and mask_instance after applying alpha."""
    from svg2ooxml.drawingml.writer import _apply_mask_alpha

    mask_ref = MaskRef(mask_id="m1")
    path = IRPath(
        segments=[LineSegment(Point(0, 0), Point(10, 10))],
        fill=SolidPaint(rgb="FF0000", opacity=1.0),
        mask=mask_ref,
    )

    result = _apply_mask_alpha(path, 0.5)

    assert result.mask is None
    assert result.mask_instance is None
    assert abs(result.fill.opacity - 0.5) < 0.001


def test_render_scene_does_not_consume_mask_alpha_metadata() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(0, 0, 20, 10),
        fill=SolidPaint("4472C4"),
        metadata={"_mask_alpha": 0.5},
    )

    first = writer.render_scene([rect]).slide_xml
    second = writer.render_scene([rect]).slide_xml

    assert '<a:alpha val="50000"/>' in first
    assert first == second


def test_render_scene_applies_alpha_mask_with_copied_metadata() -> None:
    writer = DrawingMLWriter()
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(20, 0)),
            LineSegment(Point(20, 0), Point(20, 10)),
            LineSegment(Point(20, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("4472C4"),
        mask=MaskRef(mask_id="m1"),
        metadata={"mask": {"strategy": "alpha", "alpha_value": 0.5}},
    )

    xml = writer.render_scene([path]).slide_xml

    assert '<a:alpha val="50000"/>' in xml
    assert "_mask_alpha" not in path.metadata


def test_image_clip_produces_src_rect() -> None:
    """Image (0,0,100,100) with clip (25,25,50,50) emits srcRect."""
    writer = DrawingMLWriter()
    clip_ref = ClipRef(
        clip_id="clip-crop",
        bounding_box=Rect(25, 25, 50, 50),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 100, 100),
        data=b"PNG",
        format="png",
        clip=clip_ref,
    )

    result = writer.render_scene([image])

    assert '<a:srcRect l="25000" t="25000" r="25000" b="25000"/>' in result.slide_xml


def test_image_clip_applies_ellipse_geometry() -> None:
    """ClipRef with custom ellipse geometry replaces default rect geometry."""
    writer = DrawingMLWriter()
    clip_ref = ClipRef(
        clip_id="clip-ellipse",
        bounding_box=Rect(0, 0, 50, 50),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
        custom_geometry_xml='<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>',
    )
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 50, 50),
        data=b"PNG",
        format="png",
        clip=clip_ref,
    )

    result = writer.render_scene([image])

    assert 'prst="ellipse"' in result.slide_xml


def test_image_no_clip_defaults_to_rect() -> None:
    """Image without clip gets default rectangle geometry."""
    writer = DrawingMLWriter()
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 50, 50),
        data=b"PNG",
        format="png",
    )

    result = writer.render_scene([image])

    assert 'prst="rect"' in result.slide_xml
    assert "<a:srcRect" not in result.slide_xml


def test_clipped_path_gets_overlay_pic() -> None:
    """Path with clip path_segments produces shape + EMF overlay picture."""
    writer = DrawingMLWriter()
    clip_segments = (
        LineSegment(Point(2, 2), Point(8, 2)),
        LineSegment(Point(8, 2), Point(8, 8)),
        LineSegment(Point(8, 8), Point(2, 8)),
        LineSegment(Point(2, 8), Point(2, 2)),
    )
    clip_ref = ClipRef(
        clip_id="clip-overlay",
        path_segments=clip_segments,
        bounding_box=Rect(2, 2, 6, 6),
        clip_rule="nonzero",
        strategy=ClipStrategy.NATIVE,
    )
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("00FF00"),
        clip=clip_ref,
    )

    result = writer.render_scene([path])

    # Path shape renders.
    assert "<p:sp>" in result.slide_xml
    # Overlay picture renders.
    assert "<p:pic>" in result.slide_xml
    # Overlay is an EMF media asset.
    media = list(result.assets.media)
    assert any(m.content_type == "image/x-emf" for m in media)


def test_unclipped_path_no_overlay() -> None:
    """Path without clip does not generate an overlay picture."""
    writer = DrawingMLWriter()
    path = IRPath(
        segments=[
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ],
        fill=SolidPaint("FF0000"),
    )

    result = writer.render_scene([path])

    assert "<p:sp>" in result.slide_xml
    assert "<p:pic>" not in result.slide_xml


def test_render_scene_exposes_shape_fragments() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Rectangle(bounds=Rect(0, 0, 20, 10), fill=SolidPaint("4472C4")),
            Rectangle(bounds=Rect(25, 0, 20, 10), fill=SolidPaint("ED7D31")),
        ]
    )

    result = writer.render_scene([group])

    # Leaf groups (no nested groups) are flattened
    assert len(result.shape_xml) == 2
    assert all(fragment.startswith("<p:sp>") for fragment in result.shape_xml)


def test_render_scene_preserves_leaf_group_when_group_is_animation_target() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Rectangle(bounds=Rect(0, 0, 20, 10), fill=SolidPaint("4472C4")),
        ],
        metadata={"element_ids": ["bee_group"]},
    )
    animation = AnimationDefinition(
        element_id="bee_group",
        animation_type=AnimationType.ANIMATE_TRANSFORM,
        target_attribute="transform",
        values=["0,0", "10,0"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
        transform_type=TransformType.TRANSLATE,
    )

    result = writer.render_scene(
        [group],
        animation_payload={"definitions": [animation]},
    )

    assert len(result.shape_xml) == 1
    assert result.shape_xml[0].startswith("<p:grpSp>")

    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    group_ids = {
        elem.get("id")
        for elem in root.xpath(".//p:spTree/p:grpSp/p:nvGrpSpPr/p:cNvPr", namespaces=ns)
        if elem.get("id")
    }
    timing_shape_ids = {
        elem.get("spid")
        for elem in root.xpath(".//p:timing//p:spTgt", namespaces=ns)
        if elem.get("spid")
    }

    assert group_ids
    assert timing_shape_ids & group_ids


def test_preserved_group_children_use_group_local_coordinates() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Rectangle(bounds=Rect(10, 15, 20, 10), fill=SolidPaint("4472C4")),
            Rectangle(bounds=Rect(35, 20, 10, 8), fill=SolidPaint("ED7D31")),
        ],
        metadata={"element_ids": ["bee_group"]},
    )
    animation = AnimationDefinition(
        element_id="bee_group",
        animation_type=AnimationType.ANIMATE_TRANSFORM,
        target_attribute="transform",
        values=["0,0", "10,0"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
        transform_type=TransformType.TRANSLATE,
    )

    result = writer.render_scene(
        [group],
        animation_payload={"definitions": [animation]},
    )

    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    group_xfrm = root.find(".//p:grpSp/p:grpSpPr/a:xfrm", ns)
    assert group_xfrm is not None

    child_offsets = root.xpath(
        ".//p:grpSp/p:sp/p:spPr/a:xfrm/a:off",
        namespaces=ns,
    )
    assert [off.attrib for off in child_offsets] == [
        {"x": "0", "y": "0"},
        {"x": str(px_to_emu(25)), "y": str(px_to_emu(5))},
    ]


def test_nested_group_uses_real_group_bounds() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Group(
                children=[
                    Rectangle(bounds=Rect(10, 15, 20, 12), fill=SolidPaint("4472C4"))
                ]
            )
        ]
    )

    result = writer.render_scene([group])
    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    xfrm = root.find(".//p:grpSp/p:grpSpPr/a:xfrm", ns)

    assert xfrm is not None
    off = xfrm.find("a:off", ns)
    ext = xfrm.find("a:ext", ns)
    ch_off = xfrm.find("a:chOff", ns)
    ch_ext = xfrm.find("a:chExt", ns)
    assert off is not None
    assert ext is not None
    assert ch_off is not None
    assert ch_ext is not None
    assert off.attrib == {"x": str(px_to_emu(10)), "y": str(px_to_emu(15))}
    assert ext.attrib == {"cx": str(px_to_emu(20)), "cy": str(px_to_emu(12))}
    assert ch_off.attrib == {"x": "0", "y": "0"}
    assert ch_ext.attrib == {"cx": str(px_to_emu(20)), "cy": str(px_to_emu(12))}


def test_render_shapes_returns_flattened_group_fragments() -> None:
    writer = DrawingMLWriter()
    group = Group(
        children=[
            Rectangle(bounds=Rect(0, 0, 20, 10), fill=SolidPaint("4472C4")),
            Line(
                start=Point(0, 20),
                end=Point(20, 20),
                stroke=Stroke(paint=SolidPaint("ED7D31"), width=1.5),
            ),
        ]
    )

    fragments = writer.render_shapes([group])

    assert len(fragments) == 2  # leaf group flattened
    assert "Rectangle" in fragments[0]
    assert "Line" in fragments[1]


def test_render_shapes_from_ir_returns_shape_fragments() -> None:
    writer = DrawingMLWriter()
    scene = IRScene(
        elements=[Rectangle(bounds=Rect(0, 0, 20, 10), fill=SolidPaint("4472C4"))],
        width_px=20,
        height_px=10,
    )

    fragments = writer.render_shapes_from_ir(scene)

    assert len(fragments) == 1
    assert "Rectangle 2" in fragments[0]


def test_render_shapes_from_ir_uses_scene_metadata_for_w3c_test_frame_suppression() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(0, 0, 20, 10),
        fill=SolidPaint("4472C4"),
        metadata={"element_ids": ["test-frame"]},
    )
    scene = IRScene(
        elements=[rect],
        width_px=20,
        height_px=10,
        metadata={"source_path": "tests/svg/example.svg"},
    )

    fragments = writer.render_shapes_from_ir(scene)

    assert fragments == ()


def test_render_scene_uses_scheme_color_for_theme_mapped_shapes() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(
        bounds=Rect(0, 0, 20, 10),
        fill=SolidPaint("4472C4", theme_color="accent1"),
        stroke=Stroke(paint=SolidPaint("ED7D31", theme_color="accent2"), width=1.5),
    )

    xml = writer.render_scene([rect]).slide_xml

    assert '<a:schemeClr val="accent1"/>' in xml
    assert '<a:schemeClr val="accent2"/>' in xml
    assert 'val="4472C4"' not in xml
    assert 'val="ED7D31"' not in xml


def test_render_textframe_uses_scheme_color_for_theme_mapped_runs() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[
            Run(
                text="Theme",
                font_family="Arial",
                font_size_pt=12,
                rgb="4472C4",
                theme_color="accent1",
                stroke_rgb="ED7D31",
                stroke_theme_color="accent2",
                stroke_width_px=1.0,
                stroke_opacity=1.0,
            )
        ],
    )

    xml = writer.render_scene([frame]).slide_xml

    assert '<a:schemeClr val="accent1"/>' in xml
    assert '<a:schemeClr val="accent2"/>' in xml
    assert 'val="4472C4"' not in xml
    assert 'val="ED7D31"' not in xml


TEST_FONT = "TestSans"
RUN_TEXT_EXTERNAL = "label-external"
RUN_TEXT_SLIDE = "label-slide"
