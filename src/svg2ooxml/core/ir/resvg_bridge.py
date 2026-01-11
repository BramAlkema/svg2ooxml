"""Resvg lookup and normalization helpers for IR conversion."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, TYPE_CHECKING

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.core.traversal.bridges import collect_resvg_clip_definitions, collect_resvg_mask_info
from svg2ooxml.drawingml.bridges import (
    describe_linear_gradient,
    describe_pattern,
    describe_radial_gradient,
)

try:  # pragma: no cover - resvg bridge optional while port completes
    from svg2ooxml.core.resvg.normalizer import normalize_svg_bytes as resvg_normalize_bytes
    from svg2ooxml.core.resvg.usvg_tree import BaseNode as ResvgBaseNode, Tree as ResvgTree, PatternNode
    from svg2ooxml.core.resvg.painting.paint import PaintReference
    from svg2ooxml.core.resvg.painting.gradients import LinearGradient, RadialGradient, PatternPaint
    from svg2ooxml.filters.resvg_bridge import resolve_filter_node
except Exception:  # pragma: no cover - defensive fallback when bridge missing
    resvg_normalize_bytes = None  # type: ignore
    ResvgBaseNode = None  # type: ignore
    ResvgTree = None  # type: ignore
    PaintReference = None  # type: ignore
    LinearGradient = None  # type: ignore
    RadialGradient = None  # type: ignore
    PatternNode = None  # type: ignore
    PatternPaint = None  # type: ignore
    resolve_filter_node = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext


class ResvgBridge:
    """Build resvg lookup tables and register resvg assets."""

    def __init__(self, context: "IRConverterContext") -> None:
        self._context = context
        self.tree: ResvgTree | None = None
        self.element_lookup: dict[etree._Element, ResvgBaseNode] = {}
        self.filter_descriptors: dict[str, Any] = {}
        self.clip_definitions: dict[str, ClipDefinition] = {}
        self.mask_info: dict[str, MaskInfo] = {}

    def build(self, svg_root: etree._Element) -> None:
        self.filter_descriptors.clear()
        self.clip_definitions.clear()
        self.mask_info.clear()
        self.element_lookup.clear()
        self.tree = None

        if resvg_normalize_bytes is None:
            self._context.trace_stage("unavailable", stage="resvg", metadata={"reason": "bridge_missing"})
            return

        try:
            svg_bytes = etree.tostring(svg_root, encoding="utf-8")
        except Exception:  # pragma: no cover - defensive: serialization failed
            self._context.trace_stage(
                "serialization_failed",
                stage="resvg",
                metadata={"reason": "etree_tostring_failed"},
            )
            return

        try:
            result = resvg_normalize_bytes(svg_bytes)
        except Exception:  # pragma: no cover - resvg bridge not ready
            self._context.trace_stage(
                "normalization_failed",
                stage="resvg",
                metadata={"reason": "resvg_normalize_error"},
            )
            return

        self.tree = result.tree
        if self.tree is None:
            self._context.trace_stage("empty_tree", stage="resvg")
            return

        dom_signature_map: dict[tuple[tuple[str, int], ...], list[etree._Element]] = defaultdict(list)
        for element in svg_root.iter():
            signature = self._element_signature(element)
            if signature:
                dom_signature_map[signature].append(element)

        id_map = getattr(self.tree, "ids", {})
        if id_map:
            for element in svg_root.iter():
                element_id = element.get("id")
                if not element_id:
                    continue
                resvg_node = id_map.get(element_id)
                if resvg_node is not None:
                    self.element_lookup[element] = resvg_node

        signature_map: dict[tuple[tuple[str, int], ...], list[ResvgBaseNode]] = defaultdict(list)
        resvg_root = getattr(self.tree, "root", None)
        if resvg_root is not None:
            for resvg_node in resvg_root.iter():
                source_elem = getattr(resvg_node, "source", None)
                if isinstance(source_elem, etree._Element):
                    signature = self._element_signature(source_elem)
                    if signature:
                        signature_map[signature].append(resvg_node)
                use_elem = getattr(resvg_node, "use_source", None)
                if isinstance(use_elem, etree._Element):
                    signature = self._element_signature(use_elem)
                    if signature:
                        signature_map[signature].append(resvg_node)

        for signature, dom_elements in dom_signature_map.items():
            nodes = signature_map.get(signature)
            if not nodes:
                continue
            node_index = 0
            for element in dom_elements:
                if element in self.element_lookup:
                    continue
                if node_index >= len(nodes):
                    break
                self.element_lookup[element] = nodes[node_index]
                node_index += 1

        self._context.trace_stage(
            "tree_built",
            stage="resvg",
            metadata={
                "mapped_elements": len(self.element_lookup),
                "signature_groups": len(dom_signature_map),
            },
        )

        self.clip_definitions.update(collect_resvg_clip_definitions(self.tree))
        self.mask_info.update(collect_resvg_mask_info(self.tree))
        self._context.trace_stage(
            "definitions_loaded",
            stage="clip",
            metadata={"count": len(self.clip_definitions)},
        )
        self._context.trace_stage(
            "definitions_loaded",
            stage="mask",
            metadata={"count": len(self.mask_info)},
        )

        self._register_filters()
        self._register_paints()

    def _register_filters(self) -> None:
        if self.tree is None or resolve_filter_node is None:
            return
        services = self._context.services
        if services is None:
            return
        filter_service = getattr(services, "filter_service", None)
        if filter_service is None or not hasattr(filter_service, "register_filter"):
            return

        existing_get = getattr(filter_service, "get", None)
        for filter_id, filter_node in getattr(self.tree, "filters", {}).items():
            if not filter_id:
                continue
            if callable(existing_get) and existing_get(filter_id) is not None:
                continue
            try:
                descriptor = resolve_filter_node(filter_node)
                self.filter_descriptors[filter_id] = descriptor
                filter_service.register_filter(filter_id, descriptor)
            except Exception:  # pragma: no cover - bridge errors fall back to legacy path
                self._context.logger.debug("Failed to register resvg filter %s", filter_id, exc_info=True)

        if self.filter_descriptors:
            self._context.trace_stage(
                "filters_registered",
                stage="filter",
                metadata={"count": len(self.filter_descriptors)},
            )

    def _register_paints(self) -> None:
        if self.tree is None or PaintReference is None:
            return
        services = self._context.services
        if services is None:
            return

        paint_servers = getattr(self.tree, "paint_servers", {})
        gradient_descriptors: dict[str, Any] = {}
        pattern_descriptors: dict[str, Any] = {}

        for paint_id, server_node in paint_servers.items():
            if not paint_id:
                continue
            try:
                resolved = self.tree.resolve_paint(PaintReference(f"#{paint_id}"))
            except Exception:  # pragma: no cover - defensive
                continue

            if isinstance(resolved, LinearGradient):
                gradient_descriptors[paint_id] = describe_linear_gradient(paint_id, resolved)
            elif isinstance(resolved, RadialGradient):
                gradient_descriptors[paint_id] = describe_radial_gradient(paint_id, resolved)
            elif (
                isinstance(resolved, PatternPaint)
                and PatternNode is not None
                and isinstance(server_node, PatternNode)
            ):
                pattern_descriptors[paint_id] = describe_pattern(paint_id, server_node)

        gradient_service = getattr(services, "gradient_service", None)
        if gradient_descriptors and gradient_service is not None and hasattr(gradient_service, "update_definitions"):
            gradient_service.update_definitions(gradient_descriptors)
            self._context.trace_stage(
                "gradients_registered",
                stage="paint",
                metadata={"count": len(gradient_descriptors)},
            )

        pattern_service = getattr(services, "pattern_service", None)
        if pattern_descriptors and pattern_service is not None and hasattr(pattern_service, "update_definitions"):
            pattern_service.update_definitions(pattern_descriptors)
            self._context.trace_stage(
                "patterns_registered",
                stage="paint",
                metadata={"count": len(pattern_descriptors)},
            )

    @staticmethod
    def _local_name(tag: Any) -> str:
        if not isinstance(tag, str):
            return ""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @classmethod
    def _element_signature(cls, element: etree._Element) -> tuple[tuple[str, int], ...] | None:
        if not isinstance(element.tag, str):
            return None
        path: list[tuple[str, int]] = []
        current: etree._Element | None = element
        while isinstance(current, etree._Element):
            parent = current.getparent()
            index = 0
            if parent is not None:
                for sibling in parent:
                    if not isinstance(sibling.tag, str):
                        continue
                    if sibling is current:
                        break
                    if cls._local_name(sibling.tag) == cls._local_name(current.tag):
                        index += 1
            path.append((cls._local_name(current.tag), index))
            if parent is None:
                break
            current = parent
        if not path:
            return None
        return tuple(reversed(path))


__all__ = ["ResvgBridge"]
