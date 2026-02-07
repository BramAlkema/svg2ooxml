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
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder
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
