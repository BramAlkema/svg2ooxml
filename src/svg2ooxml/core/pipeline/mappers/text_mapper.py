"""Mapper for IR TextFrame elements to DrawingML."""

from __future__ import annotations

import logging
from typing import Any

from svg2ooxml.ir.scene import TextFrame

from .base import Mapper, MapperResult, OutputFormat

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, p_elem, p_sub, to_string


class TextMapper(Mapper):
    """Translate ``TextFrame`` nodes into simple DrawingML text boxes."""

    def __init__(self, policy: Any | None = None, services=None) -> None:
        super().__init__(policy)
        self._logger = logging.getLogger(__name__)
        self._services = services

    def can_map(self, element: Any) -> bool:
        return isinstance(element, TextFrame)

    def map(self, frame: TextFrame) -> MapperResult:
        runs = frame.runs or []

        # Build p:txBody with lxml
        txBody = p_elem("txBody")
        a_sub(txBody, "bodyPr")
        a_sub(txBody, "lstStyle")

        # Build a:p paragraph
        p = a_sub(txBody, "p")

        if runs:
            # Add runs
            for run in runs:
                r = a_sub(p, "r")
                t = a_sub(r, "t")
                t.text = run.text  # lxml handles escaping
        else:
            # Empty paragraph needs endParaRPr
            a_sub(p, "endParaRPr")

        xml = to_string(txBody)

        metadata = {
            "run_count": len(runs),
            "text": frame.text_content,
        }

        return MapperResult(
            element=frame,
            output_format=OutputFormat.NATIVE_DML,
            xml_content=xml,
            policy_decision=None,
            metadata=metadata,
        )


__all__ = ["TextMapper"]
