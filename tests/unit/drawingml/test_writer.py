"""Tests for the DrawingML writer."""

from __future__ import annotations

from lxml import etree as ET

from svg2ooxml.drawingml.writer import DrawingMLWriter, EMU_PER_PX
from svg2ooxml.pipeline.navigation import NavigationKind, NavigationSpec, SlideTarget
from svg2ooxml.ir.geometry import Point, Rect, LineSegment, BezierSegment
from svg2ooxml.ir.paint import SolidPaint, LinearGradientPaint, GradientStop, Stroke
from svg2ooxml.ir.scene import (
    ClipRef,
    ClipStrategy,
    Image,
    MaskDefinition,
    MaskInstance,
    MaskRef,
    Path as IRPath,
)
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.shapes import Rectangle, Line, Polyline, Polygon
from svg2ooxml.ir.text import EmbeddedFontPlan, Run, TextAnchor, TextFrame, WordArtCandidate
from svg2ooxml.map.converter.core import IRScene


def test_render_scene_from_ir_reports_slide_size() -> None:
    writer = DrawingMLWriter()
    scene = IRScene(elements=[], width_px=120, height_px=80)

    result = writer.render_scene_from_ir(scene)

    assert result.slide_size == (int(120 * EMU_PER_PX), int(80 * EMU_PER_PX))
    assert not result.assets.media


def test_render_scene_renders_rectangle() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(bounds=Rect(x=10, y=5, width=20, height=15), fill=SolidPaint("FF0000"))

    result = writer.render_scene([rect])
    xml = result.slide_xml

    assert "Rectangle 2" in xml
    assert f'x="{int(10 * EMU_PER_PX)}"' in xml
    assert "FF0000" in xml


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
    assert '<a:custGeom>' in xml
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
    assert '<a:close/>' in xml
    assert 'val="00FF00"' in xml


def test_render_scene_renders_rounded_rectangle_with_adjustment() -> None:
    writer = DrawingMLWriter()
    rect = Rectangle(bounds=Rect(x=0, y=0, width=100, height=50), fill=SolidPaint("00FF00"), corner_radius=10.0)

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


def test_render_textframe_renders_multiple_runs() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(text="Hello", font_family="Arial", font_size_pt=12, rgb="000000"),
            Run(text="World", font_family="Arial", font_size_pt=12, rgb="FF0000", bold=True),
        ],
        baseline_shift=0.0,
    )

    result = writer.render_scene([frame])
    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    runs = root.findall('.//a:r', ns)
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


def test_render_path_names_include_policy_annotations() -> None:
    writer = DrawingMLWriter()
    segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
    ]
    path = IRPath(segments=segments, fill=SolidPaint("000000"))
    path.metadata.setdefault("policy", {})["geometry"] = {"simplified": True, "render_mode": "native"}

    result = writer.render_scene([path])
    root = ET.fromstring(result.slide_xml.encode("utf-8"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    names = [elem.attrib["name"] for elem in root.findall('.//p:cNvPr', ns)]
    assert any("render_mode=native" in value for value in names)
    assert any("simplified=True" in value for value in names)


def test_render_textframe_notes_policy_metadata(caplog) -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 20),
        runs=[Run(text="Policy!", font_family=TEST_FONT, font_size_pt=12, rgb="FF00FF")],
        baseline_shift=0.0,
        metadata={"policy": {"text": {"rendering_behavior": "outline", "font_fallback": "Arial"}}},
    )

    with caplog.at_level("DEBUG"):
        result = writer.render_scene([frame])

    debug_notes = [rec.getMessage() for rec in caplog.records if rec.levelname == "DEBUG"]
    assert any("rendering_behavior=outline" in message for message in debug_notes)
    assert any("font_fallback=Arial" in message for message in debug_notes)
    assert any("requests outline rendering" in record.getMessage() for record in caplog.records)


def test_render_wordart_frame_uses_warp_template() -> None:
    writer = DrawingMLWriter()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 40),
        runs=[Run(text="WAVE", font_family=TEST_FONT, font_size_pt=28.0, bold=True)],
        wordart_candidate=WordArtCandidate(preset="textWave1", confidence=0.9, fallback_strategy="vector_outline"),
        metadata={"wordart": {"prefer_native": True}},
    )

    xml = writer.render_scene([frame]).slide_xml

    assert "WordArt 2" in xml
    assert 'prstTxWarp="textWave1"' in xml
    assert "WAVE" in xml
    assert "<a:normAutofit/>" in xml


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
    rect.effects.append(CustomEffect(drawingml='<a:effectLst><a:blur rad="1000"/></a:effectLst>'))

    first = writer.render_scene([rect])

    assert any(item.relationship_id == "rIdCustom" for item in first.assets.media)
    second = writer.render_scene([rect])
    assert '<a:effectLst>' in second.slide_xml


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
    assert "pos=\"100000\"" in xml


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


def test_render_path_applies_marker_clip_metadata() -> None:
    writer = DrawingMLWriter()
    segments = [LineSegment(Point(0, 0), Point(10, 0))]
    stroke = Stroke(paint=SolidPaint("000000"), width=1.0)
    metadata = {"marker_clip": {"x": 0.0, "y": 0.0, "width": 2.0, "height": 1.0}, "marker_overflow": "hidden"}
    path = IRPath(
        segments=segments,
        fill=None,
        stroke=stroke,
        metadata=metadata,
    )

    xml = writer.render_scene([path]).slide_xml

    assert "<a:clipPath>" in xml
    assert "<a:path clipFill=\"1\"" in xml


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
    assert asset.relationship_type == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    assert asset.target == "https://example.com"
    assert asset.scope == "shape"


def test_text_run_navigation_creates_relationships() -> None:
    writer = DrawingMLWriter()
    nav_external = NavigationSpec(kind=NavigationKind.EXTERNAL, href="https://example.com")
    nav_slide = NavigationSpec(kind=NavigationKind.SLIDE, slide=SlideTarget(index=3))
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 30),
        runs=[
            Run(text=RUN_TEXT_EXTERNAL, font_family=TEST_FONT, font_size_pt=14.0, navigation=nav_external),
            Run(text=" ", font_family=TEST_FONT, font_size_pt=14.0),
            Run(text=RUN_TEXT_SLIDE, font_family=TEST_FONT, font_size_pt=14.0, navigation=nav_slide),
        ],
    )

    result = writer.render_scene([frame])

    navigation_assets = list(result.assets.navigation)
    assert "a:hlinkClick" in result.slide_xml
    assert len(navigation_assets) == 2
    scopes = {asset.scope for asset in navigation_assets}
    assert scopes == {"text_run"}
    external_asset = next(asset for asset in navigation_assets if asset.target_mode == "External")
    assert external_asset.target == "https://example.com"
    slide_asset = next(asset for asset in navigation_assets if asset.relationship_type == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide")
    assert slide_asset.target.endswith("slide3.xml")


def test_path_clip_path_serialisation() -> None:
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

    xml = writer.render_scene([path]).slide_xml

    assert "<a:clipPath>" in xml
    assert xml.count("<a:moveTo>") >= 1


def test_mask_approximated_to_clip_path() -> None:
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
    mask_ref = MaskRef(mask_id="mask1", definition=mask_def, target_bounds=mask_def.bounding_box)
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

    assert "<a:mask>" in result.slide_xml
    assert "<a:custGeom>" in result.slide_xml


def test_mask_raster_fallback_emits_asset() -> None:
    writer = DrawingMLWriter()
    mask_def = MaskDefinition(
        mask_id="mask-raster",
        bounding_box=Rect(0, 0, 10, 10),
    )
    mask_ref = MaskRef(mask_id="mask-raster", definition=mask_def, target_bounds=mask_def.bounding_box)
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

    assert "<a:mask" in result.slide_xml
    assert '<a:blip' in result.slide_xml
    mask_assets = list(result.assets.iter_masks())
    assert len(mask_assets) == 1
    asset = mask_assets[0]
    assert asset["content_type"] == "image/png"
    assert asset["part_name"].startswith("/ppt/masks/")
    assert any("Raster fallback emitted" in msg for msg in result.assets.diagnostics)


def test_mask_policy_emf_emits_asset() -> None:
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
    mask_ref = MaskRef(mask_id="mask-emf", definition=mask_def, target_bounds=mask_def.bounding_box)
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

    assert "<a:mask" in result.slide_xml
    assert 'r:embed=' in result.slide_xml
    mask_assets = list(result.assets.iter_masks())
    assert len(mask_assets) == 1
    asset = mask_assets[0]
    assert asset["content_type"] == "image/x-emf"
    assert any("EMF fallback emitted" in msg for msg in result.assets.diagnostics)


def test_mask_policy_prefers_mimic_before_emf() -> None:
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
    mask_ref = MaskRef(mask_id="mask-mimic", definition=mask_def, target_bounds=mask_def.bounding_box)
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

    assert "<a:mask" in result.slide_xml
    assert '<a:custGeom>' in result.slide_xml
    assert not list(result.assets.iter_masks())
    assert any("mimic fallback emitted" in msg for msg in result.assets.diagnostics)
TEST_FONT = "TestSans"
RUN_TEXT_EXTERNAL = "label-external"
RUN_TEXT_SLIDE = "label-slide"
