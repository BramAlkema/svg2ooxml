"""Filter registry and dispatch helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from lxml import etree

from .base import Filter, FilterContext, FilterResult
from .utils import build_exporter_hook
from .primitives.blend import BlendFilter
from .primitives.color_matrix import ColorMatrixFilter
from .primitives.component_transfer import ComponentTransferFilter
from .primitives.composite import CompositeFilter
from .primitives.convolve_matrix import ConvolveMatrixFilter
from .primitives.displacement_map import DisplacementMapFilter
from .primitives.drop_shadow import DropShadowFilter, GlowFilter
from .primitives.flood import FloodFilter
from .primitives.gaussian_blur import GaussianBlurFilter
from .primitives.image import ImageFilter
from .primitives.merge import MergeFilter
from .primitives.morphology import MorphologyFilter
from .primitives.offset import OffsetFilter
from .primitives.lighting import DiffuseLightingFilter, SpecularLightingFilter
from .primitives.tile import TileFilter
from .primitives.turbulence import TurbulenceFilter


class FilterRegistry:
    """Registry that maps SVG filter primitives to processors."""

    def __init__(self) -> None:
        self._filters_by_type: Dict[str, Filter] = {}
        self._filters_by_tag: Dict[str, List[Filter]] = {}
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def register_default_filters(self) -> None:
        """Populate built-in filter handlers (none yet)."""
        # TODO(ADR-filters-port): Register svg2pptx filter implementations.
        self.register(ColorMatrixFilter())
        self.register(FloodFilter())
        self.register(OffsetFilter())
        self.register(MorphologyFilter())
        self.register(ComponentTransferFilter())
        self.register(ConvolveMatrixFilter())
        self.register(ImageFilter())
        self.register(TileFilter())
        self.register(MergeFilter())
        self.register(CompositeFilter())
        self.register(GaussianBlurFilter())
        self.register(BlendFilter())
        self.register(DisplacementMapFilter())
        self.register(DropShadowFilter())
        self.register(GlowFilter())
        self.register(DiffuseLightingFilter())
        self.register(SpecularLightingFilter())
        self.register(TurbulenceFilter())
        return

    def register(self, filter_obj: Filter) -> None:
        if filter_obj.filter_type in self._filters_by_type:
            self._logger.debug("Replacing existing filter for type %s", filter_obj.filter_type)
        self._filters_by_type[filter_obj.filter_type] = filter_obj
        for tag in filter_obj.primitive_tags:
            bucket = self._filters_by_tag.setdefault(tag, [])
            if filter_obj not in bucket:
                bucket.append(filter_obj)

    def list_filters(self) -> list[str]:
        return sorted(self._filters_by_type.keys())

    def iter_filters(self) -> Iterable[Filter]:
        return tuple(self._filters_by_type.values())

    def get_filter(self, name: str) -> Optional[Filter]:
        return self._filters_by_type.get(name)

    def render_filter_element(
        self,
        filter_element: etree._Element,
        context: FilterContext,
    ) -> list[FilterResult]:
        """Process every primitive child of *filter_element*."""

        results: list[FilterResult] = []
        pipeline = context.pipeline_state
        if pipeline is None:
            pipeline = {}
            context.pipeline_state = pipeline
        self._seed_base_inputs(pipeline)

        for index, node in enumerate(filter_element):
            if not hasattr(node, "tag"):
                continue
            result = self.render_primitive(node, context, index, pipeline)
            if result is not None:
                results.append(result)
        return results

    def render_primitive(
        self,
        primitive: etree._Element,
        context: FilterContext,
        sequence_index: int,
        pipeline: Dict[str, FilterResult],
    ) -> Optional[FilterResult]:
        tag = Filter._local_name(getattr(primitive, "tag", ""))
        candidates = self._filters_by_tag.get(tag, [])
        for filter_obj in candidates:
            try:
                if not filter_obj.matches(primitive, context):
                    continue
                child_context = context.with_primitive(primitive)
                child_context.pipeline_state = pipeline
                result = filter_obj.apply(primitive, child_context)
                if result is None:
                    return None
                name = result.result_name or primitive.get("result") or self._default_result_name(
                    filter_obj, sequence_index, pipeline
                )
                result.result_name = name
                pipeline[name] = result
                return result
            except Exception:  # pragma: no cover - defensive
                self._logger.debug("Filter %s failed for primitive %s", filter_obj.filter_type, tag, exc_info=True)
        return None

    def _default_result_name(
        self,
        filter_obj: Filter,
        sequence_index: int,
        pipeline: Dict[str, FilterResult],
    ) -> str:
        base = filter_obj.filter_type or "filter"
        candidate = base
        counter = 1
        while candidate in pipeline or candidate == "SourceGraphic":
            candidate = f"{base}_{sequence_index}_{counter}"
            counter += 1
        return candidate

    def _seed_base_inputs(self, pipeline: Dict[str, FilterResult]) -> None:
        if "SourceGraphic" not in pipeline:
            pipeline["SourceGraphic"] = FilterResult(
                success=True,
                drawingml=build_exporter_hook("sourceGraphic", {"ref": "SourceGraphic"}),
                metadata={"ref": "SourceGraphic"},
            )
        if "SourceAlpha" not in pipeline:
            pipeline["SourceAlpha"] = FilterResult(
                success=True,
                drawingml=build_exporter_hook("sourceAlpha", {"ref": "SourceAlpha"}),
                metadata={"ref": "SourceAlpha"},
            )

    def clone(self) -> "FilterRegistry":
        clone = FilterRegistry()
        clone._filters_by_type = dict(self._filters_by_type)
        clone._filters_by_tag = {tag: list(filters) for tag, filters in self._filters_by_tag.items()}
        return clone


__all__ = ["FilterRegistry"]
