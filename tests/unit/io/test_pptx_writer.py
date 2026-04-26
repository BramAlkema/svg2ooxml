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
from svg2ooxml.drawingml.assets import (
    AssetRegistrySnapshot,
    FontAsset,
    MediaAsset,
    NavigationAsset,
)
from svg2ooxml.drawingml.navigation import REL_TYPE_HYPERLINK, REL_TYPE_SLIDE
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.io.pptx_assembly import (
    MaskAsset,
    PackagedMedia,
    PackagingContext,
    PPTXPackageBuilder,
    SlideAssembly,
)
from svg2ooxml.io.pptx_writer import PackageWriter, StreamingPackageWriter
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import PatternPaint, SolidPaint
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


def test_pptx_builder_reuses_pattern_tile_relationship_on_slide() -> None:
    builder = PPTXPackageBuilder()
    tile_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    paint = PatternPaint(
        pattern_id="tile_pat_shared",
        tile_image=tile_data,
        tile_width_px=8,
        tile_height_px=8,
    )
    scene = IRScene(
        elements=[
            Rectangle(bounds=Rect(0, 0, 40, 40), fill=paint),
            Rectangle(bounds=Rect(50, 0, 40, 40), fill=paint),
        ],
        width_px=120,
        height_px=60,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "pattern_tile_reuse.pptx"
        builder.build(scene, output)

        with zipfile.ZipFile(output, "r") as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            rels_xml = archive.read("ppt/slides/_rels/slide1.xml.rels")
            rels_root = ET.fromstring(rels_xml)
            rels = rels_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            image_rels = [
                rel
                for rel in rels
                if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
            ]

            assert len(image_rels) == 1
            assert image_rels[0].get("Id") == "rIdMedia1"
            assert image_rels[0].get("Target") == "../media/image1.png"
            assert slide_xml.count('r:embed="rIdMedia1"') == 2


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


def _render_result_with_media_relationship(relationship_id: str) -> DrawingMLRenderResult:
    slide_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:spTree>
      <p:pic>
        <p:blipFill><a:blip r:embed="{relationship_id}"/></p:blipFill>
      </p:pic>
    </p:spTree>
  </p:cSld>
</p:sld>
'''
    return DrawingMLRenderResult(
        slide_xml=slide_xml,
        slide_size=(160, 90),
        assets=AssetRegistrySnapshot(
            media=(
                MediaAsset(
                    relationship_id=relationship_id,
                    filename="image.png",
                    content_type="image/png",
                    data=b"png",
                ),
            )
        ),
    )


def test_packaged_media_sanitizes_filename_and_relationship_target() -> None:
    media = PackagedMedia(
        relationship_id="rIdMedia1",
        filename="../nested/evil file?.txt",
        content_type="image/png",
        data=b"png",
    )

    assert media.filename == "evil_file.png"
    assert media.package_path.as_posix() == "ppt/media/evil_file.png"
    assert media.relationship_target == "../media/evil_file.png"


def test_mask_asset_sanitizes_part_name_to_masks_directory() -> None:
    mask = MaskAsset(
        relationship_id="rIdMask1",
        part_name="/../../mask asset?.bin",
        content_type="image/png",
        data=b"mask",
    )

    assert mask.part_name == "/ppt/masks/mask_asset.png"
    assert mask.package_path.as_posix() == "ppt/masks/mask_asset.png"
    assert mask.relationship_target == "../masks/mask_asset.png"


def test_packaging_context_sanitizes_media_asset_filename() -> None:
    context = PackagingContext()
    filename = context.assign_media_filename(
        MediaAsset(
            relationship_id="rIdMedia1",
            filename="../bad name?.txt",
            content_type="image/png",
            data=b"payload",
        ),
        slide_index=1,
    )

    assert filename == "bad_name.png"


@pytest.mark.parametrize("relationship_id", ["bad id", "rId1"])
def test_build_from_results_rekeys_packaged_media_relationship_ids(
    relationship_id: str,
) -> None:
    builder = PPTXPackageBuilder()
    rendered = _render_result_with_media_relationship(relationship_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "rekey_media.pptx"
        builder.build_from_results([rendered], output)

        with zipfile.ZipFile(output, "r") as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            rels_root = ET.fromstring(
                archive.read("ppt/slides/_rels/slide1.xml.rels")
            )

    rels = rels_root.findall(
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
    )
    image_rels = [
        rel
        for rel in rels
        if rel.get("Type")
        == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    ]

    assert len(image_rels) == 1
    packaged_id = image_rels[0].get("Id")
    assert packaged_id != relationship_id
    assert f'r:embed="{packaged_id}"' in slide_xml
    assert f'r:embed="{relationship_id}"' not in slide_xml


def test_package_writer_never_emits_unsafe_media_or_mask_paths() -> None:
    builder = PPTXPackageBuilder()
    rendered = _render_simple_scene(builder)
    media = PackagedMedia(
        relationship_id="rIdUnsafeMedia",
        filename="../outside?.txt",
        content_type="image/png",
        data=b"png",
    )
    mask = MaskAsset(
        relationship_id="rIdUnsafeMask",
        part_name="../../outside-mask?.bin",
        content_type="image/png",
        data=b"mask",
    )
    slide = SlideAssembly(
        index=1,
        filename="slide1.xml",
        rel_id="rId2",
        slide_id=256,
        slide_xml=rendered.slide_xml,
        slide_size=rendered.slide_size,
        media=[media],
        masks=[mask],
    )
    writer = PackageWriter(
        base_template=builder._base_template,
        content_types_template=builder._content_types_template,
        slide_rels_template=builder._slide_rels_template,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "unsafe_paths.pptx"
        writer.write_package([slide], output)

        with zipfile.ZipFile(output, "r") as archive:
            names = set(archive.namelist())
            assert all(".." not in name.split("/") for name in names)
            assert "ppt/media/outside.png" in names
            assert "ppt/masks/outside-mask.png" in names

            rels_xml = archive.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
            assert 'Target="../media/outside.png"' in rels_xml
            assert 'Target="../masks/outside-mask.png"' in rels_xml

            content_types = archive.read("[Content_Types].xml").decode("utf-8")
            assert 'PartName="/ppt/masks/outside-mask.png"' in content_types
            assert 'ContentType="image/png"' in content_types


def test_package_writer_filters_unsafe_navigation_relationships() -> None:
    builder = PPTXPackageBuilder()
    rendered = _render_simple_scene(builder)
    slide = SlideAssembly(
        index=1,
        filename="slide1.xml",
        rel_id="rId2",
        slide_id=256,
        slide_xml=rendered.slide_xml,
        slide_size=rendered.slide_size,
        media=[],
        navigation=[
            NavigationAsset(
                relationship_id="rIdNavGood",
                relationship_type=REL_TYPE_HYPERLINK,
                target=" https://example.com/docs ",
                target_mode="External",
            ),
            NavigationAsset(
                relationship_id="bad id",
                relationship_type=REL_TYPE_HYPERLINK,
                target="https://example.com/bad-id",
                target_mode="External",
            ),
            NavigationAsset(
                relationship_id="rIdNavScript",
                relationship_type=REL_TYPE_HYPERLINK,
                target="javascript:alert(1)",
                target_mode="External",
            ),
            NavigationAsset(
                relationship_id="rIdNavMode",
                relationship_type=REL_TYPE_HYPERLINK,
                target="https://example.com/mode",
            ),
            NavigationAsset(
                relationship_id="rIdNavType",
                relationship_type="http://example.com/relationships/evil",
                target="https://example.com/evil",
                target_mode="External",
            ),
            NavigationAsset(
                relationship_id="rIdNavSlide0",
                relationship_type=REL_TYPE_SLIDE,
                target="../slides/slide0.xml",
            ),
            NavigationAsset(
                relationship_id="rIdNavSlideMode",
                relationship_type=REL_TYPE_SLIDE,
                target="../slides/slide3.xml",
                target_mode="External",
            ),
            NavigationAsset(
                relationship_id="rIdNavSlide",
                relationship_type=REL_TYPE_SLIDE,
                target="../slides/slide2.xml",
            ),
        ],
    )
    writer = PackageWriter(
        base_template=builder._base_template,
        content_types_template=builder._content_types_template,
        slide_rels_template=builder._slide_rels_template,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "unsafe_navigation.pptx"
        writer.write_package([slide], output)

        with zipfile.ZipFile(output, "r") as archive:
            rels_xml = archive.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")

    assert 'Id="rIdNavGood"' in rels_xml
    assert 'Target="https://example.com/docs"' in rels_xml
    assert 'Id="rIdNavSlide"' in rels_xml
    assert 'Target="../slides/slide2.xml"' in rels_xml
    assert "bad id" not in rels_xml
    assert "javascript:" not in rels_xml
    assert "relationships/evil" not in rels_xml
    assert "slide0.xml" not in rels_xml
    assert "slide3.xml" not in rels_xml


def test_package_writer_sanitizes_direct_slide_package_metadata() -> None:
    builder = PPTXPackageBuilder()
    rendered = _render_simple_scene(builder)
    slide = SlideAssembly(
        index=1,
        filename="../outside.pptx",
        rel_id="bad id",
        slide_id=1,
        slide_xml=rendered.slide_xml,
        slide_size=rendered.slide_size,
        media=[],
    )
    writer = PackageWriter(
        base_template=builder._base_template,
        content_types_template=builder._content_types_template,
        slide_rels_template=builder._slide_rels_template,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "safe_direct_slide.pptx"
        writer.write_package([slide], output)

        with zipfile.ZipFile(output, "r") as archive:
            names = set(archive.namelist())
            assert "ppt/slides/outside.xml" in names
            assert "ppt/slides/_rels/outside.xml.rels" in names
            assert all(".." not in name.split("/") for name in names)

            rels_root = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
            slide_rels = [
                rel
                for rel in rels_root.findall(
                    "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
                )
                if rel.get("Type")
                == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
            ]
            assert len(slide_rels) == 1
            assert slide_rels[0].get("Id") != "bad id"
            assert slide_rels[0].get("Target") == "slides/outside.xml"

            presentation_root = ET.fromstring(archive.read("ppt/presentation.xml"))
            ns = {
                "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            }
            slide_ids = presentation_root.findall("p:sldIdLst/p:sldId", ns)
            assert len(slide_ids) == 1
            assert int(slide_ids[0].get("id")) >= 256
            assert slide_ids[0].get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ) == slide_rels[0].get("Id")

            content_types = archive.read("[Content_Types].xml").decode("utf-8")
            assert 'PartName="/ppt/slides/outside.xml"' in content_types


def test_package_writer_rekeys_font_relationships_away_from_slide_ids() -> None:
    builder = PPTXPackageBuilder()
    rendered = _render_simple_scene(builder)
    slide = SlideAssembly(
        index=1,
        filename="slide1.xml",
        rel_id="rId2",
        slide_id=256,
        slide_xml=rendered.slide_xml,
        slide_size=rendered.slide_size,
        media=[],
        font_assets=[
            FontAsset(
                shape_id=1,
                plan=EmbeddedFontPlan(
                    font_family="InvalidHint",
                    requires_embedding=True,
                    subset_strategy="glyph",
                    glyph_count=1,
                    relationship_hint="bad id",
                    metadata={
                        "font_data": b"font-one",
                        "font_style_kind": "regular",
                    },
                ),
            ),
            FontAsset(
                shape_id=2,
                plan=EmbeddedFontPlan(
                    font_family="ConflictingHint",
                    requires_embedding=True,
                    subset_strategy="glyph",
                    glyph_count=1,
                    relationship_hint="rId2",
                    metadata={
                        "font_data": b"font-two",
                        "font_style_kind": "regular",
                    },
                ),
            ),
        ],
    )
    writer = PackageWriter(
        base_template=builder._base_template,
        content_types_template=builder._content_types_template,
        slide_rels_template=builder._slide_rels_template,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "safe_font_rels.pptx"
        writer.write_package([slide], output)

        with zipfile.ZipFile(output, "r") as archive:
            rels_root = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
            rels = rels_root.findall(
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
            )
            font_rels = [
                rel
                for rel in rels
                if rel.get("Type")
                == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
            ]
            slide_rels = [
                rel
                for rel in rels
                if rel.get("Type")
                == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
            ]
            presentation_root = ET.fromstring(archive.read("ppt/presentation.xml"))

    assert len(font_rels) == 2
    assert len(slide_rels) == 1
    assert slide_rels[0].get("Id") == "rId2"
    font_rel_ids = {rel.get("Id") for rel in font_rels}
    assert "bad id" not in font_rel_ids
    assert "rId2" not in font_rel_ids

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    embedded_ids = {
        elem.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        for elem in presentation_root.findall(".//p:embeddedFont/p:regular", ns)
    }
    assert embedded_ids == font_rel_ids


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
