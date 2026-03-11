from __future__ import annotations

import pytest
from lxml import etree as ET

from svg2office.common.office_profile import NS_A14, NS_ASVG, NS_MC
from svg2office.drawingml.writer import DrawingMLWriter
from svg2office.ir.geometry import Point, Rect
from svg2office.ir.scene import Image


def _slide_root(xml: str):
    return ET.fromstring(xml.encode("utf-8"))


def test_writer_default_profile_omits_office_extension_namespaces() -> None:
    writer = DrawingMLWriter()

    result = writer.render_scene([])
    root = _slide_root(result.slide_xml)

    assert "mc" not in root.nsmap
    assert "a14" not in root.nsmap
    assert "asvg" not in root.nsmap
    assert root.get(f"{{{NS_MC}}}Ignorable") is None


def test_writer_office_profile_adds_mc_ignorable_namespaces() -> None:
    writer = DrawingMLWriter(office_profile="office_compat")

    result = writer.render_scene([])
    root = _slide_root(result.slide_xml)

    assert root.nsmap.get("mc") == NS_MC
    assert root.nsmap.get("a14") == NS_A14
    assert root.nsmap.get("asvg") == NS_ASVG
    ignorable = root.get(f"{{{NS_MC}}}Ignorable")
    assert ignorable is not None
    assert set(ignorable.split()) == {"a14", "asvg"}


def test_writer_rejects_unknown_office_profile() -> None:
    with pytest.raises(ValueError, match="office_profile"):
        DrawingMLWriter(office_profile="not-a-profile")


def test_writer_office_profile_svg_emits_svg_blip_with_png_fallback() -> None:
    writer = DrawingMLWriter(office_profile="office_compat")
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 16, 16),
        data=b"<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'><rect width='16' height='16' fill='red'/></svg>",
        format="svg",
    )

    result = writer.render_scene([image])
    root = _slide_root(result.slide_xml)
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "asvg": NS_ASVG,
        "a14": NS_A14,
    }

    blip = root.find(".//a:blip", ns)
    assert blip is not None
    fallback_rid = blip.get(f"{{{ns['r']}}}embed")
    assert fallback_rid

    svg_blip = root.find(".//asvg:svgBlip", ns)
    assert svg_blip is not None
    svg_rid = svg_blip.get(f"{{{ns['r']}}}embed")
    assert svg_rid
    assert svg_rid != fallback_rid

    use_local_dpi = root.find(".//a14:useLocalDpi", ns)
    assert use_local_dpi is not None
    assert use_local_dpi.get("val") == "0"

    media = list(result.assets.media)
    assert {entry.content_type for entry in media} == {"image/png", "image/svg+xml"}
    assert fallback_rid in {entry.relationship_id for entry in media}
    assert svg_rid in {entry.relationship_id for entry in media}


def test_writer_ecma_strict_svg_omits_office_extensions() -> None:
    writer = DrawingMLWriter(office_profile="ecma_strict")
    image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 12, 12),
        data=b"<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12'><circle cx='6' cy='6' r='5'/></svg>",
        format="svg",
    )

    result = writer.render_scene([image])
    assert "asvg:svgBlip" not in result.slide_xml
    assert "a14:useLocalDpi" not in result.slide_xml
    media = list(result.assets.media)
    assert len(media) == 1
    assert media[0].content_type == "image/svg+xml"


def test_writer_profile_switch_does_not_leak_svg_extension_state() -> None:
    shared_image = Image(
        origin=Point(0, 0),
        size=Rect(0, 0, 20, 20),
        data=b"<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='black'/></svg>",
        format="svg",
        metadata={},
    )

    compat_writer = DrawingMLWriter(office_profile="office_compat")
    compat_result = compat_writer.render_scene([shared_image])
    assert "asvg:svgBlip" in compat_result.slide_xml

    strict_writer = DrawingMLWriter(office_profile="ecma_strict")
    strict_result = strict_writer.render_scene([shared_image])
    assert "asvg:svgBlip" not in strict_result.slide_xml
    assert "a14:useLocalDpi" not in strict_result.slide_xml
    strict_root = _slide_root(strict_result.slide_xml)
    assert "asvg" not in strict_root.nsmap
    assert "_office_svg_blip" not in shared_image.metadata
