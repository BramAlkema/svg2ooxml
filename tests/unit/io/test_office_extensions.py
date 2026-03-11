"""Office extension contract tests (svgBlip and p14 image settings)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree as ET
import pytest

from svg2office.core.ir import IRScene
from svg2office.io.pptx_assembly import PPTXPackageBuilder
from svg2office.ir.geometry import Point, Rect
from svg2office.ir.scene import Image
from svg2office.ir.shapes import Rectangle

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
}


def _svg_scene() -> IRScene:
    return IRScene(
        elements=[
            Image(
                origin=Point(0, 0),
                size=Rect(0, 0, 24, 24),
                data=b"<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'><rect width='24' height='24' fill='blue'/></svg>",
                format="svg",
            )
        ],
        width_px=24,
        height_px=24,
    )


def _build(builder: PPTXPackageBuilder, output: Path, scene: IRScene) -> None:
    builder.build(scene, output)
    assert output.exists()


def test_office_compat_svg_blip_package_shape(tmp_path: Path) -> None:
    output = tmp_path / "office-compat-svg.pptx"
    _build(PPTXPackageBuilder(office_profile="office_compat"), output, _svg_scene())

    with zipfile.ZipFile(output, "r") as archive:
        media_parts = [name for name in archive.namelist() if name.startswith("ppt/media/")]
        assert any(name.endswith(".png") for name in media_parts)
        assert any(name.endswith(".svg") for name in media_parts)

        slide_root = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
        ignorable = slide_root.get(f"{{{_NS['mc']}}}Ignorable")
        assert ignorable is not None
        assert set(ignorable.split()) == {"a14", "asvg"}

        blip = slide_root.find(".//a:blip", _NS)
        assert blip is not None
        fallback_rid = blip.get(f"{{{_NS['r']}}}embed")
        assert fallback_rid

        svg_blip = slide_root.find(".//asvg:svgBlip", _NS)
        assert svg_blip is not None
        svg_rid = svg_blip.get(f"{{{_NS['r']}}}embed")
        assert svg_rid
        assert svg_rid != fallback_rid

        use_local_dpi = slide_root.find(".//a14:useLocalDpi", _NS)
        assert use_local_dpi is not None
        assert use_local_dpi.get("val") == "0"

        rels_root = ET.fromstring(archive.read("ppt/slides/_rels/slide1.xml.rels"))
        rels = {
            rel.get("Id"): rel.get("Target")
            for rel in rels_root.findall("rel:Relationship", _NS)
        }
        assert rels[fallback_rid].endswith(".png")
        assert rels[svg_rid].endswith(".svg")


def test_ecma_strict_svg_blip_package_shape(tmp_path: Path) -> None:
    output = tmp_path / "ecma-strict-svg.pptx"
    _build(PPTXPackageBuilder(office_profile="ecma_strict"), output, _svg_scene())

    with zipfile.ZipFile(output, "r") as archive:
        media_parts = [name for name in archive.namelist() if name.startswith("ppt/media/")]
        assert len([name for name in media_parts if name.endswith(".svg")]) == 1
        assert len([name for name in media_parts if name.endswith(".png")]) == 0

        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "asvg:svgBlip" not in slide_xml
        assert "a14:useLocalDpi" not in slide_xml


def test_office_compat_pres_props_emits_image_settings(tmp_path: Path) -> None:
    output = tmp_path / "office-compat-pres-props.pptx"
    scene = IRScene(
        elements=[Rectangle(bounds=Rect(0, 0, 20, 20))],
        width_px=20,
        height_px=20,
    )
    _build(PPTXPackageBuilder(office_profile="office_compat"), output, scene)

    with zipfile.ZipFile(output, "r") as archive:
        root = ET.fromstring(archive.read("ppt/presProps.xml"))
        ignorable = root.get(f"{{{_NS['mc']}}}Ignorable")
        assert ignorable is not None
        assert set(ignorable.split()) == {"p14"}
        discard = root.find(".//p14:discardImageEditData", _NS)
        assert discard is not None
        assert discard.get("val") == "0"
        dpi = root.find(".//p14:defaultImageDpi", _NS)
        assert dpi is not None
        assert dpi.get("val") == "220"


def test_ecma_strict_pres_props_omits_image_settings(tmp_path: Path) -> None:
    output = tmp_path / "ecma-strict-pres-props.pptx"
    scene = IRScene(
        elements=[Rectangle(bounds=Rect(0, 0, 20, 20))],
        width_px=20,
        height_px=20,
    )
    _build(PPTXPackageBuilder(office_profile="ecma_strict"), output, scene)

    with zipfile.ZipFile(output, "r") as archive:
        root = ET.fromstring(archive.read("ppt/presProps.xml"))
        assert root.find(".//p14:discardImageEditData", _NS) is None
        assert root.find(".//p14:defaultImageDpi", _NS) is None


def test_package_builder_propagates_office_profile_to_writer() -> None:
    builder = PPTXPackageBuilder(office_profile="office_compat")
    assert builder._writer._office_profile == "office_compat"


def test_package_builder_rejects_unknown_office_profile() -> None:
    with pytest.raises(ValueError, match="office_profile"):
        PPTXPackageBuilder(office_profile="bad-profile")
