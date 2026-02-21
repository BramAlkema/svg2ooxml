from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from svg2ooxml.core.ir import IRScene
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import EmbeddedFontPlan, Run, TextAnchor, TextFrame
from svg2ooxml.services.fonts import FontEmbeddingEngine, FontEmbeddingRequest


@pytest.mark.integration
def test_embedded_fonts_emit_eot_parts(tmp_path):
    pytest.importorskip("fontforge")
    font_path = Path("tests/resources/ScheherazadeRegOT.ttf")

    engine = FontEmbeddingEngine()
    request = FontEmbeddingRequest(
        font_path=str(font_path),
        glyph_ids=tuple(ord(ch) for ch in "Hello"),
        metadata={"font_family": "Scheherazade", "font_style_kind": "regular"},
    )
    result = engine.subset_font(request)
    assert result is not None

    plan = EmbeddedFontPlan(
        font_family="Scheherazade",
        requires_embedding=True,
        subset_strategy="glyph",
        glyph_count=result.glyph_count,
        metadata=dict(result.packaging_metadata),
    )

    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 160, 40),
        runs=[Run(text="Hello", font_family="Scheherazade", font_size_pt=24.0)],
        embedding_plan=plan,
    )

    scene = IRScene(elements=[frame], width_px=160, height_px=40)
    output = tmp_path / "embedded_fonts.pptx"
    PPTXPackageBuilder().build(scene, output)

    with zipfile.ZipFile(output, "r") as archive:
        fntdata_parts = [name for name in archive.namelist() if name.startswith("ppt/fonts/")]
        assert fntdata_parts == ["ppt/fonts/font1.fntdata"]
        payload = archive.read(fntdata_parts[0])
        assert struct.unpack_from("<L", payload, 0)[0] == len(payload)
        assert struct.unpack_from("<H", payload, 34)[0] == 0x504C  # Magic number

        content_xml = archive.read("[Content_Types].xml")
        assert b'Extension="fntdata"' in content_xml
        assert b"application/x-fontdata" in content_xml

        rels = archive.read("ppt/_rels/presentation.xml.rels")
        assert b'relationships/font' in rels
        assert b'fonts/font1.fntdata' in rels

        pres_root = etree.fromstring(archive.read("ppt/presentation.xml"))
        ns = {
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        entries = pres_root.findall(".//p:embeddedFont", ns)
        assert len(entries) == 1
        entry = entries[0]
        font_el = entry.find("p:font", ns)
        assert font_el is not None
        assert font_el.get("typeface") == "Scheherazade"
        font_key = entry.find("p:fontKey", ns)
        assert font_key is None
        regular = entry.find("p:regular", ns)
        assert regular is not None
        assert regular.get(f"{{{ns['r']}}}id")
