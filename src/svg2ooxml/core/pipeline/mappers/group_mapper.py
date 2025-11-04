"""Mapper for IR Group elements to DrawingML."""

from __future__ import annotations

import logging
from typing import Any

from svg2ooxml.ir.scene import Group

from .base import Mapper, MapperResult, OutputFormat

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub, to_string


class GroupMapper(Mapper):
    """Translate IR ``Group`` nodes into grouped DrawingML shapes."""

    def __init__(self, policy: Any | None = None, services=None) -> None:
        super().__init__(policy)
        self._logger = logging.getLogger(__name__)
        self._services = services

    def can_map(self, element: Any) -> bool:
        return isinstance(element, Group)

    def map(self, group: Group) -> MapperResult:
        from lxml import etree

        child_xml = "".join(
            getattr(child, "metadata", {}).get("generated_xml", "") for child in group.children
        )

        # Build p:grpSp with lxml
        grpSp = p_elem("grpSp")

        # Build p:nvGrpSpPr
        nvGrpSpPr = p_sub(grpSp, "nvGrpSpPr")
        p_sub(nvGrpSpPr, "cNvPr", id="1", name="Group")
        p_sub(nvGrpSpPr, "cNvGrpSpPr")
        p_sub(nvGrpSpPr, "nvPr")

        # Build p:grpSpPr and append child_xml
        grpSpPr = p_sub(grpSp, "grpSpPr")
        if child_xml:
            wrapped = f'<root xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">{child_xml}</root>'
            temp = etree.fromstring(wrapped.encode('utf-8'))
            for child in temp:
                grpSpPr.append(child)

        xml = to_string(grpSp)

        metadata = {
            "child_count": len(group.children),
            "clip": getattr(group, "clip", None),
        }

        return MapperResult(
            element=group,
            output_format=OutputFormat.NATIVE_DML,
            xml_content=xml,
            policy_decision=None,
            metadata=metadata,
        )


__all__ = ["GroupMapper"]
