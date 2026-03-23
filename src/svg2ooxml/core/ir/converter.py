"""Core IR converter implementation."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.core.parser import ParseResult
from svg2ooxml.core.parser.units import UnitConverter
from svg2ooxml.css import StyleResolver
from svg2ooxml.ir.scene import SceneGraph
from svg2ooxml.policy import PolicyContext, PolicyEngine
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    from svg2ooxml.core.ir.text_converter import TextConverter
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.ir.animation import AnimationDefinition

from svg2ooxml.core.hyperlinks import HyperlinkProcessor
from svg2ooxml.core.ir.context import IRConverterContext
from svg2ooxml.core.ir.resource_tracker import ResourceTracker
from svg2ooxml.core.ir.resvg_bridge import ResvgBridge
from svg2ooxml.core.ir.shape_pipeline import ShapePipeline
from svg2ooxml.core.ir.text_pipeline import TextPipeline
from svg2ooxml.core.traversal.traversal import ElementTraversal


@dataclass
class IRScene:
    elements: SceneGraph
    width_px: float | None = None
    height_px: float | None = None
    animations: list[AnimationDefinition] | None = None
    metadata: dict[str, Any] | None = None
    background_color: str | None = None


class IRConverter:
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
        tracer: ConversionTracer | None = None,
    ) -> None:
        self._context = IRConverterContext(
            services=services,
            unit_converter=unit_converter,
            style_resolver=style_resolver,
            logger=logger,
            policy_engine=policy_engine,
            policy_context=policy_context,
            tracer=tracer,
        )
        self._resources = ResourceTracker()
        self._resvg_bridge = ResvgBridge(self._context)
        self._text_pipeline = TextPipeline(self._context)
        self._shape_pipeline = ShapePipeline(
            context=self._context,
            resources=self._resources,
            resvg_bridge=self._resvg_bridge,
            text_pipeline=self._text_pipeline,
        )
        self._shape_pipeline_convert_path_to_emf = self._shape_pipeline._convert_path_to_emf
        self._shape_pipeline._convert_path_to_emf = self._convert_path_to_emf

        # Backwards-compatible attributes used across the conversion helpers.
        self._services = self._context.services
        self._unit_converter = self._context.unit_converter
        self._style_resolver = self._context.style_resolver
        self._style_extractor = self._context.style_extractor
        self._tracer = self._context.tracer
        self._logger = self._context.logger
        self._system_languages = self._context.system_languages
        self._policy_engine = self._context.policy_engine
        self._policy_context = self._context.policy_context
        self._css_context = self._context.css_context
        self._conversion_context = self._context.conversion_context
        self._viewport_engine = self._context.viewport_engine
        self._mask_processor = self._context.mask_processor
        self._emf_adapter = self._context.emf_adapter
        self._text_converter = self._text_pipeline.converter

        self._clip_definitions = self._resources.clip_definitions
        self._mask_info = self._resources.mask_info
        self._element_index = self._resources.element_index
        self._symbol_definitions = self._resources.symbol_definitions
        self._marker_definitions = self._resources.marker_definitions
        self._use_expansion_stack = self._resources.use_expansion_stack
        self._clip_usage = self._resources.clip_usage
        self._mask_usage = self._resources.mask_usage
        self._symbol_usage = self._resources.symbol_usage
        self._marker_usage = self._resources.marker_usage

        self._resvg_tree = None
        self._resvg_element_lookup = self._resvg_bridge.element_lookup
        self._resvg_filter_descriptors = self._resvg_bridge.filter_descriptors
        self._resvg_clip_definitions = self._resvg_bridge.clip_definitions
        self._resvg_mask_info = self._resvg_bridge.mask_info

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, result: ParseResult) -> IRScene:
        if not result.success or result.svg_root is None:
            raise ValueError("ParseResult must represent a successful parse with svg_root")

        self._context.reset_tracer()
        self._resources.reset_usage()

        source_path = None
        if isinstance(result.metadata, dict):
            source_path = result.metadata.get("source_path")
        if isinstance(source_path, str) and source_path:
            if self._services.resolve("source_path") is None:
                self._services.register("source_path", source_path)

        if self._context.policy_context is None and self._context.policy_engine is not None:
            self._context.policy_context = self._context.policy_engine.evaluate()
            self._policy_context = self._context.policy_context

        hyperlink_processor = getattr(self._context.services, "hyperlink_processor", None)
        if hyperlink_processor is None:
            hyperlink_processor = HyperlinkProcessor(self._context.logger)

        self._resvg_bridge.build(result.svg_root)
        self._resvg_tree = self._resvg_bridge.tree
        self._context.resvg_tree = self._resvg_tree
        self._shape_pipeline._svg_root = result.svg_root # Store root for baking
        self._context.prepare_style_context(result)
        self._css_context = self._context.css_context
        self._conversion_context = self._context.conversion_context
        self._resources.prepare(result, resvg_bridge=self._resvg_bridge, context=self._context)
        self._shape_pipeline.refresh_state()
        self._style_extractor.clear_cache()

        traversal = ElementTraversal(
            ir_converter=self,
            hyperlink_processor=hyperlink_processor,
            logger=self._context.logger,
            normalized_lookup={},
        )

        elements = traversal.extract(result.svg_root)
        self._resources.trace_unused_resources(self._context)
        self._context.trace_stage(
            "conversion_complete",
            stage="converter",
            metadata={"element_count": result.element_count},
        )
        scene_metadata = {
            "element_count": result.element_count,
            "namespaces": result.namespaces,
            "has_external_references": result.has_external_references,
        }
        if self._context.tracer is not None:
            scene_metadata["trace_report"] = self._context.tracer.report().to_dict()
        background_color = _extract_background(
            elements, result.width_px, result.height_px,
        )
        return IRScene(
            elements=elements,
            width_px=result.width_px,
            height_px=result.height_px,
            animations=result.animations,
            metadata=scene_metadata,
            background_color=background_color,
        )

    @property
    def text_converter(self) -> TextConverter:
        """Expose text converter helper for downstream integrations/tests."""

        return self._text_pipeline.converter

    def convert_group(self, element: etree._Element, children: list, matrix):
        return self._shape_pipeline.convert_group(element, children, matrix)

    def convert_element(
        self,
        *,
        tag: str,
        element: etree._Element,
        coord_space,
        current_navigation,
        traverse_callback,
    ):
        return self._shape_pipeline.convert_element(
            tag=tag,
            element=element,
            coord_space=coord_space,
            current_navigation=current_navigation,
            traverse_callback=traverse_callback,
        )

    def expand_use(
        self,
        *,
        element: etree._Element,
        coord_space,
        current_navigation,
        traverse_callback,
    ):
        return self._shape_pipeline.expand_use(
            element=element,
            coord_space=coord_space,
            current_navigation=current_navigation,
            traverse_callback=traverse_callback,
        )

    def attach_metadata(self, ir_object, element: etree._Element, navigation_spec) -> None:
        self._shape_pipeline.attach_metadata(ir_object, element, navigation_spec)

    def _apply_filter_metadata(self, ir_object, element: etree._Element, metadata: dict[str, Any]) -> None:
        self._sync_policy_context()
        self._shape_pipeline._apply_filter_metadata(ir_object, element, metadata)

    def __getattr__(self, name: str):
        if name.startswith("_") and hasattr(self._shape_pipeline, name):
            return getattr(self._shape_pipeline, name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def _trace_stage(
        self,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
        stage: str = "converter",
    ) -> None:
        self._context.trace_stage(action, metadata=metadata, subject=subject, stage=stage)

    def preload_stage_events(
        self,
        events: Iterable[tuple[str, str, str | None, dict[str, Any]]],
    ) -> None:
        self._context.preload_stage_events(events)

    def _trace_unused_resources(self) -> None:
        self._resources.trace_unused_resources(self._context)

    def _build_resvg_lookup(self, svg_root: etree._Element) -> None:
        self._resvg_bridge.build(svg_root)
        self._resvg_tree = self._resvg_bridge.tree
        self._context.resvg_tree = self._resvg_tree
        self._shape_pipeline.refresh_state()

    def _prepare_context(self, result: ParseResult) -> None:
        self._context.prepare_style_context(result)
        self._css_context = self._context.css_context
        self._conversion_context = self._context.conversion_context
        self._resources.prepare(result, resvg_bridge=self._resvg_bridge, context=self._context)
        self._shape_pipeline.refresh_state()

    def _trace_geometry_decision(self, element, decision: str, metadata: dict[str, Any] | None) -> None:
        self._context.trace_geometry_decision(element, decision, metadata)

    def _policy_options(self, target: str) -> Mapping[str, Any] | None:
        self._sync_policy_context()
        return self._context.policy_options(target)

    def _attach_policy_metadata(
        self,
        metadata: dict[str, Any],
        target: str,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self._sync_policy_context()
        self._context.attach_policy_metadata(metadata, target, extra=extra)

    @staticmethod
    def _bitmap_fallback_limits(options: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
        return IRConverterContext.bitmap_fallback_limits(options)

    def _matrix_from_transform(self, transform_str: str | None):
        return self._context.matrix_from_transform(transform_str)

    @staticmethod
    def _local_name(tag: Any) -> str:
        return IRConverterContext.local_name(tag)

    @staticmethod
    def _normalize_href_reference(href: str | None) -> str | None:
        return IRConverterContext.normalize_href_reference(href)

    @staticmethod
    def _make_namespaced_tag(reference: etree._Element, local: str) -> str:
        return IRConverterContext.make_namespaced_tag(reference, local)

    def _convert_path_to_emf(self, *args, **kwargs):
        return self._shape_pipeline_convert_path_to_emf(*args, **kwargs)

    def _can_use_resvg(self, element: etree._Element) -> bool:
        if self._resvg_tree is None:
            return False
        return element in self._resvg_element_lookup

    def _sync_policy_context(self) -> None:
        if self._policy_context is None:
            return
        if self._context.policy_context is self._policy_context:
            return
        self._context.policy_context = self._policy_context


def _extract_background(
    elements: SceneGraph,
    width_px: float | None,
    height_px: float | None,
) -> str | None:
    """Detect a full-coverage background rect and remove it from elements.

    Checks the first element (and the first child of a root Group) for a
    Rectangle or simple Path that fills ≥95% of the viewport with a solid color.

    Returns the background color as an RRGGBB hex string, or None.
    """
    from svg2ooxml.ir.paint import SolidPaint
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.shapes import Rectangle

    if not elements or width_px is None or height_px is None:
        return None
    if width_px <= 0 or height_px <= 0:
        return None

    # Try the first element directly
    color = _check_background_candidate(elements[0], width_px, height_px)
    if color is not None:
        elements.pop(0)
        return color

    # Try the first child of a root Group (common pattern: <g> wrapping everything)
    first = elements[0]
    if isinstance(first, Group) and first.children:
        color = _check_background_candidate(first.children[0], width_px, height_px)
        if color is not None:
            first.children.pop(0)
            return color

    return None


def _check_background_candidate(
    elem: object,
    width_px: float,
    height_px: float,
) -> str | None:
    """Return the fill color if *elem* is a full-coverage solid-fill rect."""
    from svg2ooxml.ir.paint import SolidPaint
    from svg2ooxml.ir.shapes import Rectangle

    if not isinstance(elem, Rectangle):
        return None
    if elem.corner_radius > 0 or elem.stroke is not None or elem.effects:
        return None
    if not isinstance(elem.fill, SolidPaint):
        return None
    if elem.element_id:
        return None

    coverage_x = elem.bounds.width / width_px
    coverage_y = elem.bounds.height / height_px
    if coverage_x < 0.95 or coverage_y < 0.95:
        return None

    if abs(elem.bounds.x) > width_px * 0.05 or abs(elem.bounds.y) > height_px * 0.05:
        return None

    return elem.fill.rgb


__all__ = ["IRConverter", "IRScene"]
