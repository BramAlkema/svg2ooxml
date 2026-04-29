"""Optional PPTX document-property metadata helpers."""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lxml import etree as ET

from svg2ooxml.common.boundaries import next_relationship_id
from svg2ooxml.io.pptx_package_constants import CONTENT_NS, REL_NS
from svg2ooxml.io.pptx_xml import serialize_xml

CUSTOM_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
CUSTOM_PROPERTIES_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    "custom-properties"
)
CUSTOM_PROPERTIES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.custom-properties+xml"
)
CUSTOM_PROPERTIES_PART = "docProps/custom.xml"
CUSTOM_TRACE_PROPERTY = "svg2ooxmlTraceJson"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_CUSTOM_PROPERTY_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def embed_trace_docprops(
    pptx_path: str | Path,
    trace_report: Mapping[str, Any],
    *,
    property_name: str = CUSTOM_TRACE_PROPERTY,
) -> None:
    """Embed a trace report as an opt-in PPTX custom document property."""

    path = Path(pptx_path)
    trace_json = json.dumps(
        trace_report,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    parts = _read_zip_parts(path)
    parts["[Content_Types].xml"] = _with_custom_content_type(
        parts["[Content_Types].xml"]
    )
    parts["_rels/.rels"] = _with_custom_properties_relationship(parts["_rels/.rels"])
    parts[CUSTOM_PROPERTIES_PART] = _custom_properties_xml(
        parts.get(CUSTOM_PROPERTIES_PART),
        property_name=property_name,
        value=trace_json,
    )
    _write_zip_parts(path, parts)


def _read_zip_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {
            item.filename: archive.read(item.filename)
            for item in archive.infolist()
            if not item.is_dir()
        }


def _write_zip_parts(path: Path, parts: Mapping[str, bytes]) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    try:
        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, data in parts.items():
                archive.writestr(name, data)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _with_custom_content_type(content_types_xml: bytes) -> bytes:
    root = ET.fromstring(content_types_xml)
    part_name = f"/{CUSTOM_PROPERTIES_PART}"
    for node in root.findall(f"{{{CONTENT_NS}}}Override"):
        if node.get("PartName") == part_name:
            node.set("ContentType", CUSTOM_PROPERTIES_CONTENT_TYPE)
            return serialize_xml(root)
    ET.SubElement(
        root,
        f"{{{CONTENT_NS}}}Override",
        {
            "PartName": part_name,
            "ContentType": CUSTOM_PROPERTIES_CONTENT_TYPE,
        },
    )
    return serialize_xml(root)


def _with_custom_properties_relationship(rels_xml: bytes) -> bytes:
    root = ET.fromstring(rels_xml)
    existing_ids = {
        node.get("Id") for node in root.findall(f"{{{REL_NS}}}Relationship")
    }
    for node in root.findall(f"{{{REL_NS}}}Relationship"):
        if (
            node.get("Type") == CUSTOM_PROPERTIES_REL_TYPE
            or node.get("Target") == CUSTOM_PROPERTIES_PART
        ):
            node.set("Type", CUSTOM_PROPERTIES_REL_TYPE)
            node.set("Target", CUSTOM_PROPERTIES_PART)
            return serialize_xml(root)
    rel_id = next_relationship_id(existing_ids)
    ET.SubElement(
        root,
        f"{{{REL_NS}}}Relationship",
        {
            "Id": rel_id,
            "Type": CUSTOM_PROPERTIES_REL_TYPE,
            "Target": CUSTOM_PROPERTIES_PART,
        },
    )
    return serialize_xml(root)


def _custom_properties_xml(
    existing_xml: bytes | None,
    *,
    property_name: str,
    value: str,
) -> bytes:
    if existing_xml:
        root = ET.fromstring(existing_xml)
    else:
        root = ET.Element(
            f"{{{CUSTOM_PROPERTIES_NS}}}Properties",
            nsmap={None: CUSTOM_PROPERTIES_NS, "vt": VT_NS},
        )

    prop = _find_custom_property(root, property_name)
    if prop is None:
        prop = ET.SubElement(
            root,
            f"{{{CUSTOM_PROPERTIES_NS}}}property",
            {
                "fmtid": _CUSTOM_PROPERTY_FMTID,
                "pid": str(_next_property_pid(root)),
                "name": property_name,
            },
        )
    else:
        prop.set("fmtid", _CUSTOM_PROPERTY_FMTID)
        prop.set("name", property_name)
        for child in list(prop):
            prop.remove(child)

    ET.SubElement(prop, f"{{{VT_NS}}}lpwstr").text = value
    return serialize_xml(root)


def _find_custom_property(root: ET._Element, property_name: str) -> ET._Element | None:
    for prop in root.findall(f"{{{CUSTOM_PROPERTIES_NS}}}property"):
        if prop.get("name") == property_name:
            return prop
    return None


def _next_property_pid(root: ET._Element) -> int:
    pids: list[int] = []
    for prop in root.findall(f"{{{CUSTOM_PROPERTIES_NS}}}property"):
        try:
            pids.append(int(prop.get("pid", "0")))
        except ValueError:
            continue
    return max([1, *pids]) + 1


__all__ = [
    "CUSTOM_PROPERTIES_PART",
    "CUSTOM_TRACE_PROPERTY",
    "embed_trace_docprops",
]
