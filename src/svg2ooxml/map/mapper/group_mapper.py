"""Mapper for IR Group elements to DrawingML."""

from __future__ import annotations

import logging
from typing import Any

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
        xml = (
            "<p:grpSp>"
            "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"Group\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
            f"<p:grpSpPr>{child_xml}</p:grpSpPr>"
            "</p:grpSp>"
        )

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
