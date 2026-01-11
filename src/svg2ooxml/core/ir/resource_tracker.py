"""Track clip/mask/symbol/marker usage during IR conversion."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext
    from svg2ooxml.core.ir.resvg_bridge import ResvgBridge
    from svg2ooxml.core.parser import ParseResult


class ResourceTracker:
    """Maintain conversion resource definitions and usage."""

    def __init__(self) -> None:
        self.clip_definitions: dict[str, ClipDefinition] = {}
        self.mask_info: dict[str, MaskInfo] = {}
        self.symbol_definitions: dict[str, etree._Element] = {}
        self.marker_definitions: dict[str, Any] = {}
        self.element_index: dict[str, etree._Element] = {}
        self.use_expansion_stack: set[str] = set()

        self.clip_usage: set[str] = set()
        self.mask_usage: set[str] = set()
        self.symbol_usage: set[str] = set()
        self.marker_usage: set[str] = set()

    def reset_usage(self) -> None:
        self.clip_usage.clear()
        self.mask_usage.clear()
        self.symbol_usage.clear()
        self.marker_usage.clear()

    def prepare(
        self,
        result: "ParseResult",
        *,
        resvg_bridge: "ResvgBridge | None",
        context: "IRConverterContext",
    ) -> None:
        self.clip_definitions.clear()
        self.mask_info.clear()
        if resvg_bridge is not None:
            self.clip_definitions.update(resvg_bridge.clip_definitions)
            self.mask_info.update(resvg_bridge.mask_info)

        self.element_index.clear()
        if result.svg_root is not None:
            self.element_index.update(self._build_element_index(result.svg_root))
        context.element_index = self.element_index

        self.symbol_definitions.clear()
        if result.symbols:
            self.symbol_definitions.update(result.symbols)
            context.trace_stage(
                "symbol_definitions",
                stage="symbol",
                metadata={"count": len(self.symbol_definitions)},
            )

        self.marker_definitions.clear()
        if result.markers:
            self.marker_definitions.update(result.markers)
            context.trace_stage(
                "marker_definitions",
                stage="marker",
                metadata={"count": len(self.marker_definitions)},
            )

        self.use_expansion_stack.clear()

    def trace_unused_resources(self, context: "IRConverterContext") -> None:
        if self.clip_definitions:
            unused_clips = sorted(set(self.clip_definitions.keys()) - self.clip_usage)
            for clip_id in unused_clips:
                context.trace_stage("unused_definition", stage="clip", subject=clip_id)

        if self.mask_info:
            unused_masks = sorted(set(self.mask_info.keys()) - self.mask_usage)
            for mask_id in unused_masks:
                context.trace_stage("unused_definition", stage="mask", subject=mask_id)

        if self.symbol_definitions:
            unused_symbols = sorted(set(self.symbol_definitions.keys()) - self.symbol_usage)
            for symbol_id in unused_symbols:
                context.trace_stage("unused_symbol", stage="symbol", subject=symbol_id)

        if self.marker_definitions:
            unused_markers = sorted(set(self.marker_definitions.keys()) - self.marker_usage)
            for marker_id in unused_markers:
                context.trace_stage("unused_marker", stage="marker", subject=marker_id)

    @staticmethod
    def _build_element_index(root: etree._Element) -> dict[str, etree._Element]:
        index: dict[str, etree._Element] = {}
        for node in root.iter():
            node_id = node.get("id")
            if node_id:
                index[node_id] = node
        return index


__all__ = ["ResourceTracker"]
