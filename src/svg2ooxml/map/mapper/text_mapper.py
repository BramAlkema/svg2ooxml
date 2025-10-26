"""Mapper for IR TextFrame elements to DrawingML."""

from __future__ import annotations

import logging
from typing import Any

from svg2ooxml.ir.scene import TextFrame

from .base import Mapper, MapperResult, OutputFormat


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
        paragraphs = "".join(f"<a:r><a:t>{run.text}</a:t></a:r>" for run in runs)
        xml = (
            "<p:txBody>"
            "<a:bodyPr/>"
            "<a:lstStyle/>"
            f"<a:p>{paragraphs or '<a:endParaRPr/>'}</a:p>"
            "</p:txBody>"
        )

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
