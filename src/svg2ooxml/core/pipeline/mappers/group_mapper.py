"""Mapper for IR Group elements to DrawingML."""

from __future__ import annotations

import logging
from typing import Any

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import (
    NS_A,
    NS_P,
    graft_xml_fragment,
    p_elem,
    p_sub,
    to_string,
)
from svg2ooxml.ir.scene import Group

from .base import Mapper, MapperResult, OutputFormat


class GroupMapper(Mapper):
    """Translate IR ``Group`` nodes into grouped DrawingML shapes."""

    def __init__(self, policy: Any | None = None, services=None) -> None:
        super().__init__(policy)
        self._logger = logging.getLogger(__name__)
        self._services = services

    def can_map(self, element: Any) -> bool:
        return isinstance(element, Group)

    def map(self, group: Group) -> MapperResult:
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
            graft_xml_fragment(grpSpPr, child_xml, namespaces={"p": NS_P, "a": NS_A})

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
