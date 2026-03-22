"""Tests for PPTX package builder media integration."""

from __future__ import annotations

import hashlib
import struct
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest
from lxml import etree as ET

from svg2ooxml.core.ir import IRScene
from svg2ooxml.core.pipeline.navigation import (
    NavigationKind,
    NavigationSpec,
    SlideTarget,
)
from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder
from svg2ooxml.io.pptx_writer import StreamingPackageWriter
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.shapes import Rectangle
from svg2ooxml.ir.text import EmbeddedFontPlan, Run, TextAnchor, TextFrame
from svg2ooxml.services.fonts.eot import build_eot


def _build_scene_with_filter_assets() -> IRScene:
    rect = Rectangle(bounds=Rect(0, 0, 40, 40), fill=SolidPaint("FFFFFF"))
    rect.effects.append(
        CustomEffect(
            drawingml=(
                '<a:effectLst><a:blipFill rotWithShape="0">'
                '<a:blip r:embed="rIdCustom"/></a:blipFill></a:effectLst>'
            )
        )
    )
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
    return IRScene(elements=[rect], width_px=40, height_px=40)


def test_pptx_builder_embeds_filter_assets() -> None:
    scene = _build_scene_with_filter_assets()
    builder = PPTXPackageBuilder()
    expected_media = hashlib.md5(bytes.fromhex("DEADBEEF"), usedforsecurity=False).hexdigest()[:8]
    expected_path = f"emf_{expected_media}.emf"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "scene.pptx"
        builder.build(scene, output)

        with zipfile.ZipFile(output, "r") as archive:
            names = set(archive.namelist())
            assert f"ppt/media/{expected_path}" in names

            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            assert 'r:embed="rIdCustom"' in slide_xml

            rels_xml = archive.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
            assert 'Id="rIdCustom"' in rels_xml
            assert f'../media/{expected_path}' in rels_xml

            content_xml = archive.read("[Content_Types].xml").decode("utf-8")
            assert 'Extension="emf"' in content_xml


def test_pptx_builder_embeds_fonts() -> None:
    pytest.importorskip("fontforge")
    font_path = Path("tests/resources/ScheherazadeRegOT.ttf")
    font_bytes = font_path.read_bytes()
    test_guid = uuid.UUID("12345678-90ab-cdef-1234-567890abcdef")
    eot = build_eot(
        font_bytes,
        resolved_family="Scheherazade",
        resolved_style="Regular",
        guid=test_guid,
    )

    plan = EmbeddedFontPlan(
        font_family="Scheherazade",
        requires_embedding=True,
        subset_strategy="glyph",
        glyph_count=len("Hello"),
        relationship_hint="rIdFontCustom",
        metadata={
            "font_data": eot.data,
            "eot_bytes": eot.data,
            "font_family": "Scheherazade",
            "font_path": str(font_path),
            "font_style_kind": "regular",
            "font_style_flags": {"bold": False, "italic": False, "style_kind": "regular"},
            "font_guid": str(test_guid),
            "font_root_string": eot.root_string,
            "font_pitch_family": 0x32,
            "font_charset": 1,
        },
    )
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 40),
        runs=[Run(text="Hello", font_family="Scheherazade", font_size_pt=24.0)],
        embedding_plan=plan,
    )
    scene = IRScene(elements=[frame], width_px=120, height_px=40)

    builder = PPTXPackageBuilder()

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "fonts_scene.pptx"
        builder.build(scene, output)

        with zipfile.ZipFile(output, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            assert font_files, "Expected embedded font file in PPTX package"
            font_name = font_files[0]
            embedded = archive.read(font_name)
            assert font_name.endswith(".fntdata")
            assert struct.unpack_from("<H", embedded, 34)[0] == 0x504C  # EOT magic

            rels_xml = archive.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
            assert "relationships/font" in rels_xml
            assert "rIdFontCustom" in rels_xml
            assert font_name.split("ppt/")[1] in rels_xml

            presentation_xml = archive.read("ppt/presentation.xml").decode("utf-8")
            assert "embeddedFontLst" in presentation_xml
            assert "Scheherazade" in presentation_xml
            assert "rIdFontCustom" in presentation_xml
            assert "pitchFamily" in presentation_xml
            assert "charset" in presentation_xml

            content_xml = archive.read("[Content_Types].xml").decode("utf-8")
            assert 'Extension="fntdata"' in content_xml
            assert "application/x-fontdata" in content_xml


def test_pptx_builder_embeds_navigation_relationships() -> None:
    rect = Rectangle(bounds=Rect(0, 0, 40, 30), fill=SolidPaint("00AAFF"))
    rect.metadata["navigation"] = NavigationSpec(
        kind=NavigationKind.EXTERNAL,
        href="https://example.com",
    ).as_dict()

    nav_text = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 120, 20),
        runs=[
            Run(text="Visit", font_family="Arial", font_size_pt=14.0, navigation=NavigationSpec(kind=NavigationKind.EXTERNAL, href="https://example.com/docs")),
            Run(text=" ", font_family="Arial", font_size_pt=14.0),
            Run(text="Next", font_family="Arial", font_size_pt=14.0, navigation=NavigationSpec(kind=NavigationKind.SLIDE, slide=SlideTarget(index=2))),
        ],
    )

    scene = IRScene(elements=[rect, nav_text], width_px=160, height_px=90)

    builder = PPTXPackageBuilder()

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "nav_scene.pptx"
        builder.build(scene, output)

        with zipfile.ZipFile(output, "r") as archive:
            rels_xml = archive.read("ppt/slides/_rels/slide1.xml.rels")
            rels_root = ET.fromstring(rels_xml)
            rels = rels_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            hyperlink_targets = [rel.get("Target") for rel in rels if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"]
            assert "https://example.com" in hyperlink_targets
            assert "https://example.com/docs" in hyperlink_targets
            slide_targets = [rel.get("Target") for rel in rels if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"]
            assert "../slides/slide2.xml" in slide_targets

            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            assert slide_xml.count("a:hlinkClick") >= 3


def test_pptx_builder_supports_multiple_slides() -> None:
    builder = PPTXPackageBuilder()

    first_scene = IRScene(
        elements=[Rectangle(bounds=Rect(0, 0, 40, 20), fill=SolidPaint("FF0000"))],
        width_px=160,
        height_px=90,
    )
    second_scene = IRScene(
        elements=[Rectangle(bounds=Rect(10, 10, 30, 15), fill=SolidPaint("00FF00"))],
        width_px=200,
        height_px=120,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "multi_slide.pptx"
        builder.build_scenes([first_scene, second_scene], output)

        with zipfile.ZipFile(output, "r") as archive:
            names = set(archive.namelist())
            assert "ppt/slides/slide1.xml" in names
            assert "ppt/slides/slide2.xml" in names

            presentation_xml = ET.fromstring(archive.read("ppt/presentation.xml"))
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            slide_ids = presentation_xml.findall("p:sldIdLst/p:sldId", ns)
            assert len(slide_ids) == 2

            rels_xml = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
            rels = rels_xml.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
            slide_targets = {
                rel.get("Target")
                for rel in rels
                if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
            }
            assert {"slides/slide1.xml", "slides/slide2.xml"}.issubset(slide_targets)

            content_types = archive.read("[Content_Types].xml").decode("utf-8")
            assert 'PartName="/ppt/slides/slide2.xml"' in content_types


# ------------------------------------------------------------------
# Streaming API tests
# ------------------------------------------------------------------


def _render_simple_scene(builder: PPTXPackageBuilder, width: int = 160, height: int = 90):
    """Render a minimal scene and return the DrawingMLRenderResult."""
    scene = IRScene(
        elements=[Rectangle(bounds=Rect(0, 0, 40, 20), fill=SolidPaint("FF0000"))],
        width_px=width,
        height_px=height,
    )
    return builder._writer.render_scene_from_ir(scene)


def test_streaming_single_slide() -> None:
    builder = PPTXPackageBuilder()
    result = _render_simple_scene(builder)

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_single.pptx"
        with builder.begin_streaming() as stream:
            stream.add_slide(result)
            path = stream.finalize(output)

        assert path.exists()
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            assert "ppt/slides/slide1.xml" in names
            assert "ppt/presentation.xml" in names
            assert "[Content_Types].xml" in names


def test_streaming_multiple_slides() -> None:
    builder = PPTXPackageBuilder()

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_multi.pptx"
        with builder.begin_streaming() as stream:
            for _ in range(3):
                stream.add_slide(_render_simple_scene(builder))
            path = stream.finalize(output)

        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            assert "ppt/slides/slide1.xml" in names
            assert "ppt/slides/slide2.xml" in names
            assert "ppt/slides/slide3.xml" in names

            presentation_xml = ET.fromstring(archive.read("ppt/presentation.xml"))
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            slide_ids = presentation_xml.findall("p:sldIdLst/p:sldId", ns)
            assert len(slide_ids) == 3


def test_streaming_media_dedup() -> None:
    """Same image across 2 slides should produce only one copy in ppt/media/."""
    builder = PPTXPackageBuilder()

    # Create two scenes that reference the same media (same content = same MD5)
    scene1 = _build_scene_with_filter_assets()
    scene2 = _build_scene_with_filter_assets()
    result1 = builder._writer.render_scene_from_ir(scene1)
    result2 = builder._writer.render_scene_from_ir(scene2)

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_dedup.pptx"
        with builder.begin_streaming() as stream:
            stream.add_slide(result1)
            stream.add_slide(result2)
            path = stream.finalize(output)

        with zipfile.ZipFile(path, "r") as archive:
            media_files = [n for n in archive.namelist() if n.startswith("ppt/media/")]
            # Same content should be deduped to one file
            emf_files = [n for n in media_files if n.endswith(".emf")]
            assert len(emf_files) == 1


def test_streaming_slide_size_multipage() -> None:
    """3 different sizes → max dimensions in multipage mode."""
    builder = PPTXPackageBuilder(slide_size_mode="multipage")

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_sizes.pptx"
        with builder.begin_streaming() as stream:
            stream.add_slide(_render_simple_scene(builder, width=100, height=80))
            stream.add_slide(_render_simple_scene(builder, width=200, height=120))
            stream.add_slide(_render_simple_scene(builder, width=150, height=100))
            path = stream.finalize(output)

        with zipfile.ZipFile(path, "r") as archive:
            presentation_xml = ET.fromstring(archive.read("ppt/presentation.xml"))
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            slide_sz = presentation_xml.find("p:sldSz", ns)
            cx = int(slide_sz.get("cx"))
            cy = int(slide_sz.get("cy"))
            # Should be at least as large as the biggest slide
            assert cx >= 200 * 914400 // 96
            assert cy >= 120 * 914400 // 96


def test_streaming_slide_size_same() -> None:
    """mode='same' → first slide dimensions."""
    builder = PPTXPackageBuilder(slide_size_mode="same")

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_same.pptx"
        with builder.begin_streaming() as stream:
            stream.add_slide(_render_simple_scene(builder, width=100, height=80))
            stream.add_slide(_render_simple_scene(builder, width=200, height=120))
            path = stream.finalize(output)

        with zipfile.ZipFile(path, "r") as archive:
            presentation_xml = ET.fromstring(archive.read("ppt/presentation.xml"))
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            slide_sz = presentation_xml.find("p:sldSz", ns)
            cx = int(slide_sz.get("cx"))
            cy = int(slide_sz.get("cy"))

            # In same mode, first slide dimensions are used (clamped to OOXML minimum 914400)
            first_result = _render_simple_scene(builder, width=100, height=80)
            expected_cx = max(first_result.slide_size[0], 914400)
            expected_cy = max(first_result.slide_size[1], 914400)
            assert (cx, cy) == (expected_cx, expected_cy)


def test_streaming_begin_required() -> None:
    """add_slide() without begin() → RuntimeError."""
    builder = PPTXPackageBuilder()
    writer = StreamingPackageWriter(
        base_template=builder._base_template,
        content_types_template=builder._content_types_template,
        slide_rels_template=builder._slide_rels_template,
    )

    with pytest.raises(RuntimeError, match="begin"):
        writer.add_slide(_render_simple_scene(builder))


def test_streaming_double_finalize() -> None:
    """finalize() twice → RuntimeError."""
    builder = PPTXPackageBuilder()

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "streaming_double.pptx"
        with builder.begin_streaming() as stream:
            stream.add_slide(_render_simple_scene(builder))
            stream.finalize(output)

            with pytest.raises(RuntimeError, match="finalize"):
                stream.finalize(output)


def test_streaming_context_manager_cleanup() -> None:
    """Exception inside context manager → temp dir cleaned up."""
    builder = PPTXPackageBuilder()
    temp_path_ref = None

    try:
        with builder.begin_streaming() as stream:
            stream.add_slide(_render_simple_scene(builder))
            temp_path_ref = stream._temp_path
            assert temp_path_ref is not None
            assert temp_path_ref.exists()
            raise ValueError("Simulated error")
    except ValueError:
        pass

    # After __exit__, temp dir should be cleaned up
    assert stream._temp_path is None
