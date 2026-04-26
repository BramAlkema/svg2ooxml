"""Resvg lookup and normalization helpers for IR conversion."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.svg_refs import local_name as svg_local_name
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.core.traversal.bridges import (
    collect_resvg_clip_definitions,
    collect_resvg_mask_info,
)
from svg2ooxml.drawingml.bridges import (
    describe_linear_gradient,
    describe_pattern,
    describe_radial_gradient,
)

try:  # pragma: no cover - resvg bridge optional while port completes
    from svg2ooxml.core.resvg.normalizer import (
        normalize_svg_element as resvg_normalize_element,
    )
    from svg2ooxml.core.resvg.painting.gradients import (
        LinearGradient,
        PatternPaint,
        RadialGradient,
    )
    from svg2ooxml.core.resvg.painting.paint import PaintReference
    from svg2ooxml.core.resvg.usvg_tree import BaseNode as ResvgBaseNode
    from svg2ooxml.core.resvg.usvg_tree import PatternNode
    from svg2ooxml.core.resvg.usvg_tree import Tree as ResvgTree
    from svg2ooxml.filters.resvg_bridge import resolve_filter_node
except Exception:  # pragma: no cover - defensive fallback when bridge missing
    resvg_normalize_element = None  # type: ignore
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

    def __init__(self, context: IRConverterContext) -> None:
        self._context = context
        self.tree: ResvgTree | None = None
        self.element_lookup: dict[etree._Element, ResvgBaseNode] = {}
        self.global_transform_lookup: dict[tuple[tuple[str, int], ...], Any] = {}
        self.node_global_transform_lookup: dict[int, Any] = {}
        self.filter_descriptors: dict[str, Any] = {}
        self.clip_definitions: dict[str, ClipDefinition] = {}
        self.mask_info: dict[str, MaskInfo] = {}

    def build(self, svg_root: etree._Element) -> None:
        self.filter_descriptors.clear()
        self.clip_definitions.clear()
        self.mask_info.clear()
        self.element_lookup.clear()
        self.global_transform_lookup.clear()
        self.node_global_transform_lookup.clear()
        self.tree = None

        if resvg_normalize_element is None:
            self._context.trace_stage("unavailable", stage="resvg", metadata={"reason": "bridge_missing"})
            return

        try:
            result = resvg_normalize_element(svg_root)
        except Exception:
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

        # 1. Signature Pre-computation
        xml_signatures: dict[tuple[tuple[str, int], ...], etree._Element] = {}
        ignored_tags = {"style", "metadata", "title", "desc", "animate", "animateTransform", "animateMotion", "animateColor", "set", "mpath"}
        for element in svg_root.iter():
            if not isinstance(element.tag, str):
                continue
            tag = self._local_name(element.tag).lower()
            if tag in ignored_tags:
                continue
            sig = self._element_signature(element)
            if sig:
                xml_signatures[sig] = element

        # 2. Recursive Tree Traversal
        resvg_root_node = getattr(self.tree, "root", None)
        resvg_signatures: dict[tuple[tuple[str, int], ...], ResvgBaseNode] = {}
        from svg2ooxml.common.geometry import Matrix2D
        
        def _walk_resvg(node: ResvgBaseNode, current_path: list[tuple[str, int]], parent_transform: Matrix2D):
            # Calculate global transform for this node
            local_transform = getattr(node, "transform", None)
            if local_transform is not None:
                if not isinstance(local_transform, Matrix2D):
                    local_transform = Matrix2D.from_values(
                        getattr(local_transform, 'a', 1.0),
                        getattr(local_transform, 'b', 0.0),
                        getattr(local_transform, 'c', 0.0),
                        getattr(local_transform, 'd', 1.0),
                        getattr(local_transform, 'e', 0.0),
                        getattr(local_transform, 'f', 0.0)
                    )
                global_transform = parent_transform.multiply(local_transform)
            else:
                global_transform = parent_transform

            sig = tuple(current_path)
            self.global_transform_lookup[sig] = global_transform
            self.node_global_transform_lookup[id(node)] = global_transform

            # A. Primary Link
            source_elem = getattr(node, "source", None)
            if isinstance(source_elem, etree._Element):
                self.element_lookup[source_elem] = node

            # A2. Map <use> elements when available (resvg exposes use_source).
            use_source = getattr(node, "use_source", None)
            if isinstance(use_source, etree._Element):
                use_sig = self._element_signature(use_source)
                if use_sig is not None:
                    xml_elem = xml_signatures.get(use_sig, use_source)
                    self.element_lookup.setdefault(xml_elem, node)
                    self.global_transform_lookup.setdefault(use_sig, global_transform)
                else:
                    self.element_lookup.setdefault(use_source, node)

            # B. Record signature
            if sig not in resvg_signatures:
                resvg_signatures[sig] = node
            
            # Recurse through children
            counts = defaultdict(int)
            for child in getattr(node, 'children', []):
                child_tag = self._local_name(child.tag).lower()
                child_index = counts[child_tag]
                counts[child_tag] += 1
                _walk_resvg(child, current_path + [(child_tag, child_index)], global_transform)

        if resvg_root_node is not None:
            root_tag = self._local_name(resvg_root_node.tag).lower()
            _walk_resvg(resvg_root_node, [(root_tag, 0)], Matrix2D.identity())

        # 3. Fallback Pass: Match by ID
        id_map = getattr(self.tree, "ids", {})
        if id_map:
            for element in svg_root.iter():
                if element in self.element_lookup or not isinstance(element.tag, str):
                    continue
                tag = self._local_name(element.tag).lower()
                if tag in ignored_tags:
                    continue
                element_id = element.get("id")
                if element_id and element_id in id_map:
                    self.element_lookup[element] = id_map[element_id]

        # 3b. Map <use> elements to referenced nodes (common in W3C suite).
        for element in svg_root.iter():
            if element in self.element_lookup or not isinstance(element.tag, str):
                continue
            if self._local_name(element.tag).lower() != "use":
                continue
            href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
            ref_id = local_url_id(href)
            if ref_id is None:
                continue
            resvg_node = id_map.get(ref_id) if id_map else None
            if resvg_node is None:
                try:
                    matches = svg_root.xpath(f".//*[@id='{ref_id}']")
                except Exception:
                    matches = []
                if matches:
                    ref_element = matches[0]
                    resvg_node = self.element_lookup.get(ref_element)
            if resvg_node is not None:
                self.element_lookup[element] = resvg_node

        # 4. Final Resort: Match by signature
        for sig, element in xml_signatures.items():
            if element in self.element_lookup:
                continue
            resvg_node = resvg_signatures.get(sig)
            if resvg_node is not None:
                self.element_lookup[element] = resvg_node

        self._context.trace_stage(
            "tree_built",
            stage="resvg",
            metadata={
                "mapped_elements": len(self.element_lookup),
                "xml_signatures": len(xml_signatures),
                "resvg_signatures": len(resvg_signatures),
            },
        )

        self.clip_definitions.update(collect_resvg_clip_definitions(self.tree))
        self.mask_info.update(collect_resvg_mask_info(self.tree))
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
            except Exception:
                self._context.logger.debug("Failed to register resvg filter %s", filter_id, exc_info=True)

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
            except Exception:
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

        pattern_service = getattr(services, "pattern_service", None)
        if pattern_descriptors and pattern_service is not None and hasattr(pattern_service, "update_definitions"):
            pattern_service.update_definitions(pattern_descriptors)

    @staticmethod
    def _local_name(tag: Any) -> str:
        return svg_local_name(tag)

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
