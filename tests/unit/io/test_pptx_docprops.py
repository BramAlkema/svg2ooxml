from __future__ import annotations

import json
import zipfile
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.io.pptx_docprops import (
    CUSTOM_PROPERTIES_PART,
    CUSTOM_TRACE_PROPERTY,
    embed_trace_docprops,
)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
"""


def test_embed_trace_docprops_adds_custom_property_part(tmp_path: Path) -> None:
    pptx_path = tmp_path / "trace.pptx"
    with zipfile.ZipFile(pptx_path, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("ppt/presentation.xml", "<p:presentation/>")

    embed_trace_docprops(
        pptx_path,
        {"stage_totals": {"parser:normalization": 1}},
    )

    with zipfile.ZipFile(pptx_path, "r") as archive:
        names = set(archive.namelist())
        assert CUSTOM_PROPERTIES_PART in names
        trace_payload = _trace_payload_from_custom_xml(
            archive.read(CUSTOM_PROPERTIES_PART)
        )
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        root_rels = archive.read("_rels/.rels").decode("utf-8")

    assert trace_payload["stage_totals"]["parser:normalization"] == 1
    assert "/docProps/custom.xml" in content_types
    assert "custom-properties" in root_rels


def _trace_payload_from_custom_xml(custom_xml: bytes) -> dict[str, object]:
    root = ET.fromstring(custom_xml)
    namespaces = {
        "cp": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
        "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    }
    prop = root.find(f".//cp:property[@name='{CUSTOM_TRACE_PROPERTY}']", namespaces)
    assert prop is not None
    value = prop.find("vt:lpwstr", namespaces)
    assert value is not None and value.text
    payload = json.loads(value.text)
    assert isinstance(payload, dict)
    return payload
