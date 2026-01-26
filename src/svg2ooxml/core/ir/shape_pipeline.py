"""Shape and traversal pipeline for IR conversion."""

from __future__ import annotations

from typing import Any, Mapping, TYPE_CHECKING

from svg2ooxml.core.ir.shape_converters import ShapeConversionMixin
from svg2ooxml.core.traversal.hooks import TraversalHooksMixin

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext
    from svg2ooxml.core.ir.resource_tracker import ResourceTracker
    from svg2ooxml.core.ir.resvg_bridge import ResvgBridge
    from svg2ooxml.core.ir.text_pipeline import TextPipeline


class ShapePipeline(ShapeConversionMixin, TraversalHooksMixin):
    """Coordinate shape conversion and traversal hooks with shared state."""

    def __init__(
        self,
        *,
        context: "IRConverterContext",
        resources: "ResourceTracker",
        resvg_bridge: "ResvgBridge",
        text_pipeline: "TextPipeline",
    ) -> None:
        self._context = context
        self._resources = resources
        self._resvg_bridge = resvg_bridge
        self._text_pipeline = text_pipeline
        self._text_converter = text_pipeline
        self.refresh_state()

    def refresh_state(self) -> None:
        context = self._context
        self._services = context.services
        self._unit_converter = context.unit_converter
        self._style_resolver = context.style_resolver
        self._style_extractor = context.style_extractor
        self._tracer = context.tracer
        self._logger = context.logger
        self._system_languages = context.system_languages
        self._policy_engine = context.policy_engine
        self._policy_context = context.policy_context
        self._css_context = context.css_context
        self._conversion_context = context.conversion_context
        self._viewport_engine = context.viewport_engine
        self._mask_processor = context.mask_processor
        self._emf_adapter = context.emf_adapter

        resources = self._resources
        self._clip_definitions = resources.clip_definitions
        self._mask_info = resources.mask_info
        self._element_index = resources.element_index
        self._symbol_definitions = resources.symbol_definitions
        self._marker_definitions = resources.marker_definitions
        self._use_expansion_stack = resources.use_expansion_stack
        self._clip_usage = resources.clip_usage
        self._mask_usage = resources.mask_usage
        self._symbol_usage = resources.symbol_usage
        self._marker_usage = resources.marker_usage

        resvg = self._resvg_bridge
        self._resvg_tree = resvg.tree
        self._resvg_element_lookup = resvg.element_lookup
        self._resvg_global_transform_lookup = resvg.global_transform_lookup
        self._resvg_filter_descriptors = resvg.filter_descriptors
        self._resvg_clip_definitions = resvg.clip_definitions
        self._resvg_mask_info = resvg.mask_info

    def _policy_options(self, target: str) -> Mapping[str, Any] | None:
        return self._context.policy_options(target)

    def _attach_policy_metadata(
        self,
        metadata: dict[str, Any],
        target: str,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self._context.attach_policy_metadata(metadata, target, extra=extra)

    @staticmethod
    def _bitmap_fallback_limits(options: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
        from svg2ooxml.core.ir.context import IRConverterContext

        return IRConverterContext.bitmap_fallback_limits(options)

    def _trace_stage(
        self,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
        stage: str = "converter",
    ) -> None:
        self._context.trace_stage(action, metadata=metadata, subject=subject, stage=stage)

    def _matrix_from_transform(self, transform_str: str | None):
        return self._context.matrix_from_transform(transform_str)


__all__ = ["ShapePipeline"]
