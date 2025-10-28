"""Core IR converter implementation."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, TYPE_CHECKING

from lxml import etree

import locale
import os

from svg2ooxml.css import StyleResolver
from svg2ooxml.ir.scene import SceneGraph
from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.core.parser import ParseResult, UnitConverter
from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.policy import PolicyContext, PolicyEngine
from svg2ooxml.services import ConversionServices
from svg2ooxml.viewbox.core import ViewportEngine

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    from svg2ooxml.core.tracing import ConversionTracer

try:  # pragma: no cover - resvg bridge optional while port completes
    from svg2ooxml.core.resvg.normalizer import normalize_svg_bytes as resvg_normalize_bytes
    from svg2ooxml.core.resvg.usvg_tree import BaseNode as ResvgBaseNode, Tree as ResvgTree, PatternNode, UseNode
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
    UseNode = None  # type: ignore
    PatternPaint = None  # type: ignore
    resolve_filter_node = None  # type: ignore

from svg2ooxml.core.hyperlinks import HyperlinkProcessor
from svg2ooxml.core.masks import MaskProcessor
from svg2ooxml.core.styling import StyleExtractor
from svg2ooxml.core.traversal.bridges import collect_resvg_clip_definitions, collect_resvg_mask_info
from svg2ooxml.core.ir.policy_hooks import PolicyHooksMixin
from svg2ooxml.drawingml.bridges import (
    describe_linear_gradient,
    describe_pattern,
    describe_radial_gradient,
)
from svg2ooxml.core.ir.shape_converters import ShapeConversionMixin
from svg2ooxml.map.converter.text import TextConverter
from svg2ooxml.map.converter.traversal import ElementTraversal
from svg2ooxml.map.converter.traversal_hooks import TraversalHooksMixin


@dataclass
class IRScene:
    elements: SceneGraph
    width_px: float | None = None
    height_px: float | None = None
    metadata: dict[str, Any] | None = None


class IRConverter(PolicyHooksMixin, ShapeConversionMixin, TraversalHooksMixin):
    """Convert parser output into IR scene graph objects."""

    def __init__(
        self,
        *,
        services: ConversionServices,
        unit_converter: UnitConverter | None = None,
        style_resolver: StyleResolver | None = None,
        logger: logging.Logger | None = None,
        policy_engine: PolicyEngine | None = None,
        policy_context: PolicyContext | None = None,
        tracer: "ConversionTracer | None" = None,
    ) -> None:
        self._services = services
        self._unit_converter = unit_converter or UnitConverter()

        resolved_style_resolver = style_resolver
        if resolved_style_resolver is None and services is not None:
            try:
                resolved_style_resolver = services.resolve("style_resolver")
            except AttributeError:  # pragma: no cover - defensive fallback
                resolved_style_resolver = None

        self._style_resolver = resolved_style_resolver or StyleResolver(self._unit_converter)
        self._style_extractor = StyleExtractor(self._style_resolver)
        self._tracer = tracer
        self._style_extractor.set_tracer(tracer)
        self._logger = logger or logging.getLogger(__name__)
        self._system_languages = self._detect_system_languages()

        self._policy_engine = policy_engine
        self._policy_context = policy_context

        self._css_context = None
        self._clip_definitions: dict[str, ClipDefinition] = {}
        self._mask_info: dict[str, MaskInfo] = {}
        self._element_index: dict[str, etree._Element] = {}
        self._symbol_definitions: dict[str, etree._Element] = {}
        self._use_expansion_stack: set[str] = set()
        self._conversion_context = None
        self._viewport_engine = ViewportEngine()
        self._text_converter = TextConverter(self)
        self._resvg_tree: ResvgTree | None = None
        self._resvg_element_lookup: dict[etree._Element, ResvgBaseNode] = {}
        self._resvg_filter_descriptors: dict[str, Any] = {}
        self._resvg_clip_definitions: dict[str, ClipDefinition] = {}
        self._resvg_mask_info: dict[str, MaskInfo] = {}
        self._clip_usage: set[str] = set()
        self._mask_usage: set[str] = set()
        self._symbol_usage: set[str] = set()
        self._marker_usage: set[str] = set()
        self._marker_definitions: dict[str, Any] = {}
        self._preloaded_stage_events: list[tuple[str, str, str | None, dict[str, Any]]] = []
        mask_processor = None
        if services is not None:
            mask_processor = getattr(services, "mask_processor", None)
            if mask_processor is None and hasattr(services, "resolve"):
                mask_processor = services.resolve("mask_processor")
        self._mask_processor = mask_processor or MaskProcessor(services)
        if hasattr(self._mask_processor, "set_tracer"):
            self._mask_processor.set_tracer(tracer)

        emf_adapter = None
        if services is not None:
            emf_adapter = getattr(services, "emf_path_adapter", None)
            if emf_adapter is None and hasattr(services, "resolve"):
                emf_adapter = services.resolve("emf_path_adapter")
        self._emf_adapter = emf_adapter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, result: ParseResult) -> IRScene:
        if not result.success or result.svg_root is None:
            raise ValueError("ParseResult must represent a successful parse with svg_root")

        if self._tracer is not None:
            self._tracer.reset()
            if self._preloaded_stage_events:
                for stage, action, subject, metadata in self._preloaded_stage_events:
                    self._tracer.record_stage_event(
                        stage=stage,
                        action=action,
                        subject=subject,
                        metadata=metadata,
                )
                self._preloaded_stage_events.clear()

        self._clip_usage.clear()
        self._mask_usage.clear()
        self._symbol_usage.clear()
        self._marker_usage.clear()

        if self._policy_context is None and self._policy_engine is not None:
            self._policy_context = self._policy_engine.evaluate()

        hyperlink_processor = getattr(self._services, "hyperlink_processor", None)
        if hyperlink_processor is None:
            hyperlink_processor = HyperlinkProcessor(self._logger)
        self._build_resvg_lookup(result.svg_root)
        self._prepare_context(result)
        self._style_extractor.clear_cache()

        traversal = ElementTraversal(
            ir_converter=self,
            hyperlink_processor=hyperlink_processor,
            logger=self._logger,
            normalized_lookup={},
        )

        elements = traversal.extract(result.svg_root)
        self._trace_unused_resources()
        self._trace_stage(
            "conversion_complete",
            stage="converter",
            metadata={"element_count": result.element_count},
        )
        scene_metadata = {
            "element_count": result.element_count,
            "namespaces": result.namespaces,
            "has_external_references": result.has_external_references,
        }
        if self._tracer is not None:
            scene_metadata["trace_report"] = self._tracer.report().to_dict()
        return IRScene(
            elements=elements,
            width_px=result.width_px,
            height_px=result.height_px,
            metadata=scene_metadata,
        )

    @property
    def text_converter(self) -> TextConverter:
        """Expose text converter helper for downstream integrations/tests."""

        return self._text_converter

    def _trace_stage(
        self,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
        stage: str = "converter",
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage=stage, action=action, metadata=metadata, subject=subject)

    def preload_stage_events(
        self,
        events: Iterable[tuple[str, str, str | None, dict[str, Any]]],
    ) -> None:
        self._preloaded_stage_events = [
            (stage, action, subject, dict(metadata) if isinstance(metadata, dict) else {})
            for stage, action, subject, metadata in events
        ]

    def _trace_unused_resources(self) -> None:
        if not self._tracer:
            return

        if self._clip_definitions:
            unused_clips = sorted(set(self._clip_definitions.keys()) - self._clip_usage)
            for clip_id in unused_clips:
                self._trace_stage("unused_definition", stage="clip", subject=clip_id)

        if self._mask_info:
            unused_masks = sorted(set(self._mask_info.keys()) - self._mask_usage)
            for mask_id in unused_masks:
                self._trace_stage("unused_definition", stage="mask", subject=mask_id)

        if self._symbol_definitions:
            unused_symbols = sorted(set(self._symbol_definitions.keys()) - self._symbol_usage)
            for symbol_id in unused_symbols:
                self._trace_stage("unused_symbol", stage="symbol", subject=symbol_id)

        marker_defs = getattr(self, "_marker_definitions", {})
        if marker_defs:
            unused_markers = sorted(set(marker_defs.keys()) - self._marker_usage)
            for marker_id in unused_markers:
                self._trace_stage("unused_marker", stage="marker", subject=marker_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_resvg_lookup(self, svg_root: etree._Element) -> None:
        self._resvg_filter_descriptors = {}
        self._resvg_clip_definitions = {}
        self._resvg_mask_info = {}
        if resvg_normalize_bytes is None:
            self._trace_stage("unavailable", stage="resvg", metadata={"reason": "bridge_missing"})
            self._resvg_tree = None
            self._resvg_element_lookup = {}
            return

        try:
            svg_bytes = etree.tostring(svg_root, encoding="utf-8")
        except Exception:  # pragma: no cover - defensive: serialization failed
            self._trace_stage(
                "serialization_failed",
                stage="resvg",
                metadata={"reason": "etree_tostring_failed"},
            )
            self._resvg_tree = None
            self._resvg_element_lookup = {}
            self._resvg_clip_definitions = {}
            self._resvg_mask_info = {}
            return

        try:
            result = resvg_normalize_bytes(svg_bytes)
        except Exception:  # pragma: no cover - resvg bridge not ready
            self._trace_stage(
                "normalization_failed",
                stage="resvg",
                metadata={"reason": "resvg_normalize_error"},
            )
            self._resvg_tree = None
            self._resvg_element_lookup = {}
            self._resvg_clip_definitions = {}
            self._resvg_mask_info = {}
            return

        self._resvg_tree = result.tree
        lookup: dict[etree._Element, ResvgBaseNode] = {}
        if self._resvg_tree is None:
            self._trace_stage("empty_tree", stage="resvg")
            self._resvg_element_lookup = lookup
            self._resvg_clip_definitions = {}
            self._resvg_mask_info = {}
            return

        dom_signature_map: dict[tuple[tuple[str, int], ...], list[etree._Element]] = defaultdict(list)
        for element in svg_root.iter():
            signature = self._element_signature(element)
            if signature:
                dom_signature_map[signature].append(element)

        id_map = getattr(self._resvg_tree, "ids", {})
        if id_map:
            for element in svg_root.iter():
                element_id = element.get("id")
                if not element_id:
                    continue
                resvg_node = id_map.get(element_id)
                if resvg_node is not None:
                    lookup[element] = resvg_node

        signature_map: dict[tuple[tuple[str, int], ...], list[ResvgBaseNode]] = defaultdict(list)
        resvg_root = getattr(self._resvg_tree, "root", None)
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
                if element in lookup:
                    continue
                if node_index >= len(nodes):
                    break
                lookup[element] = nodes[node_index]
                node_index += 1

        self._trace_stage(
            "tree_built",
            stage="resvg",
            metadata={
                "mapped_elements": len(lookup),
                "signature_groups": len(dom_signature_map),
            },
        )
        self._resvg_element_lookup = lookup

        if self._resvg_tree is not None:
            self._resvg_clip_definitions = collect_resvg_clip_definitions(self._resvg_tree)
            self._resvg_mask_info = collect_resvg_mask_info(self._resvg_tree)
            self._trace_stage(
                "definitions_loaded",
                stage="clip",
                metadata={"count": len(self._resvg_clip_definitions)},
            )
            self._trace_stage(
                "definitions_loaded",
                stage="mask",
                metadata={"count": len(self._resvg_mask_info)},
            )
        else:
            self._resvg_clip_definitions = {}
            self._resvg_mask_info = {}

        if self._services is not None and resolve_filter_node is not None:
            filter_service = getattr(self._services, "filter_service", None)
            if filter_service is not None and hasattr(filter_service, "register_filter"):
                existing_get = getattr(filter_service, "get", None)
                for filter_id, filter_node in getattr(self._resvg_tree, "filters", {}).items():
                    if not filter_id:
                        continue
                    if callable(existing_get) and existing_get(filter_id) is not None:
                        continue
                    try:
                        descriptor = resolve_filter_node(filter_node)
                        self._resvg_filter_descriptors[filter_id] = descriptor
                        filter_service.register_filter(filter_id, descriptor)
                    except Exception:  # pragma: no cover - bridge errors fall back to legacy path
                        self._logger.debug("Failed to register resvg filter %s", filter_id, exc_info=True)
                if self._resvg_filter_descriptors:
                    self._trace_stage(
                        "filters_registered",
                        stage="filter",
                        metadata={"count": len(self._resvg_filter_descriptors)},
                    )
        else:
            self._resvg_filter_descriptors = {}

        if self._services is not None and self._resvg_tree is not None and PaintReference is not None:
            paint_servers = getattr(self._resvg_tree, "paint_servers", {})

            gradient_descriptors: dict[str, Any] = {}
            pattern_descriptors: dict[str, Any] = {}

            for paint_id, server_node in paint_servers.items():
                if not paint_id:
                    continue
                try:
                    resolved = self._resvg_tree.resolve_paint(PaintReference(f"#{paint_id}"))
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

            gradient_service = getattr(self._services, "gradient_service", None)
            if gradient_descriptors and gradient_service is not None and hasattr(gradient_service, "update_definitions"):
                gradient_service.update_definitions(gradient_descriptors)
                self._trace_stage(
                    "gradients_registered",
                    stage="paint",
                    metadata={"count": len(gradient_descriptors)},
                )

            pattern_service = getattr(self._services, "pattern_service", None)
            if pattern_descriptors and pattern_service is not None and hasattr(pattern_service, "update_definitions"):
                pattern_service.update_definitions(pattern_descriptors)
                self._trace_stage(
                    "patterns_registered",
                    stage="paint",
                    metadata={"count": len(pattern_descriptors)},
                )

    def _matrix_from_transform(self, transform_str: str | None) -> Matrix2D:
        """Return a transformation matrix parsed from ``transform_str``."""

        if not transform_str or not transform_str.strip():
            return Matrix2D.identity()
        try:
            matrix = parse_transform_list(transform_str.strip())
        except Exception:
            matrix = None
        if matrix is None:
            return Matrix2D.identity()
        return matrix

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

    def _detect_system_languages(self) -> tuple[str, ...]:
        override = os.getenv("SVG2OOXML_SYSTEM_LANGUAGE")
        tokens: list[str] = []
        if override:
            tokens.extend(token.strip() for token in override.split(",") if token.strip())
        else:
            try:
                lang, _ = locale.getdefaultlocale()
            except Exception:
                lang = None
            if lang:
                tokens.append(lang)
        if not tokens:
            tokens.append("en")

        normalized: list[str] = []
        for token in tokens:
            canonical = token.replace("_", "-").lower()
            if canonical and canonical not in normalized:
                normalized.append(canonical)
            if "-" in canonical:
                primary = canonical.split("-", 1)[0]
                if primary and primary not in normalized:
                    normalized.append(primary)
        if "en" not in normalized:
            normalized.append("en")
        return tuple(normalized)


__all__ = ["IRConverter", "IRScene"]
