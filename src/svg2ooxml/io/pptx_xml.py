"""Shared XML serialization helpers for PPTX package parts."""

from __future__ import annotations

from io import BytesIO

from lxml import etree as ET


def serialize_xml(root: ET._Element) -> bytes:
    """Serialize an lxml element as UTF-8 XML bytes with declaration."""

    output = BytesIO()
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()


__all__ = ["serialize_xml"]
