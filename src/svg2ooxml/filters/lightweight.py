"""Lightweight filter pipeline used when full render dependencies are unavailable."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import (
    FilterRenderer as DrawingMLFilterRenderer,
)
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.palette import (
    attach_emf_metadata as _attach_emf_metadata,
)
from svg2ooxml.filters.palette import (
    attach_raster_metadata as _attach_raster_metadata,
)
from svg2ooxml.filters.planner_neutral import NeutralPrimitiveMixin
from svg2ooxml.filters.planner_payload import DescriptorPayloadMixin
from svg2ooxml.filters.planner_policy import PolicyPlanningMixin
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult


class LightweightFilterPlanner(
    NeutralPrimitiveMixin,
    DescriptorPayloadMixin,
    PolicyPlanningMixin,
):
    """Subset planner that avoids any raster/filter execution imports."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)


class LightweightFilterRenderer:
    """Fallback renderer that supports native/vector/placeholder flows only."""

    def __init__(
        self,
        *,
        registry: FilterRegistry,
        planner: LightweightFilterPlanner,
        logger: logging.Logger | None = None,
        palette_resolver: PaletteResolver | None = None,
        raster_adapter: RasterAdapter | None = None,
    ) -> None:
        self._registry = registry
        self._planner = planner
        self._logger = logger or logging.getLogger(__name__)
        self._palette_resolver = palette_resolver
        self._drawingml_renderer = DrawingMLFilterRenderer(
            logger=self._logger,
            palette_resolver=palette_resolver,
        )
        self._raster_adapter = raster_adapter or RasterAdapter()

    def clone(
        self,
        *,
        registry: FilterRegistry | None = None,
        planner: LightweightFilterPlanner | None = None,
    ) -> LightweightFilterRenderer:
        return LightweightFilterRenderer(
            registry=registry or self._registry,
            planner=planner or self._planner,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
            raster_adapter=self._raster_adapter,
        )

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        self._palette_resolver = resolver
        self._drawingml_renderer.set_palette_resolver(resolver)

    def render_native(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        context.pipeline_state = context.pipeline_state or {}
        filter_results = self._registry.render_filter_element(element, context)
        return self._drawingml_renderer.render(filter_results, context=context)

    def render_vector(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        context.pipeline_state = {}
        filter_results = self._registry.render_filter_element(element, context)
        if not filter_results:
            return []

        coerced: list[FilterResult] = []
        for result in filter_results:
            metadata = dict(result.metadata or {})
            fallback = result.fallback
            drawingml = result.drawingml
            if fallback not in {None, "vector", "emf"}:
                fallback = "emf"
                drawingml = ""
                metadata.setdefault("vector_forced", True)
            coerced.append(
                FilterResult(
                    success=result.success,
                    drawingml=drawingml,
                    fallback=fallback,
                    metadata=metadata,
                    warnings=result.warnings,
                    result_name=result.result_name,
                )
            )

        rendered = self._drawingml_renderer.render(coerced, context=context)
        adjusted: list[FilterEffectResult] = []
        for effect in rendered:
            fallback = effect.fallback
            if fallback in {"bitmap", "raster"}:
                fallback = "emf"
            adjusted.append(
                replace(
                    effect,
                    strategy="vector",
                    fallback=fallback,
                )
            )
        return adjusted

    def render_raster(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
        *,
        strategy: str,
    ) -> list[FilterEffectResult]:
        raster = self._raster_adapter.render_filter(
            filter_id=filter_id,
            filter_element=element,
            context=context,
        )
        metadata = dict(raster.metadata or {})
        metadata.setdefault("renderer", "placeholder")
        metadata["fallback_assets"] = [
            {
                "type": "raster",
                "format": "png",
                "data": raster.image_bytes,
                "relationship_id": raster.relationship_id,
                "width_px": raster.width_px,
                "height_px": raster.height_px,
            }
        ]
        effect = CustomEffect(drawingml=f"<!-- svg2ooxml:raster filter={filter_id} -->")
        return [
            FilterEffectResult(
                effect=effect,
                strategy=strategy if strategy in {"raster", "auto"} else "raster",
                metadata=metadata,
                fallback="bitmap",
            )
        ]

    def render_resvg_filter(
        self,
        descriptor: Any,  # noqa: ARG002
        filter_element: etree._Element,  # noqa: ARG002
        filter_context: FilterContext,  # noqa: ARG002
        filter_id: str,  # noqa: ARG002
        *,
        trace: Any | None = None,  # noqa: ARG002
    ) -> FilterEffectResult | None:
        return None

    def descriptor_fallback(
        self,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, Any] | None,
        filter_id: str,
        *,
        strategy_hint: str,
    ) -> list[FilterEffectResult] | None:
        if descriptor is None:
            return None
        inferred = self._planner.infer_descriptor_strategy(
            descriptor, strategy_hint=strategy_hint
        )
        if inferred is None:
            return None

        metadata: dict[str, Any] = {
            "descriptor": descriptor,
            "strategy_source": "resvg_descriptor",
        }
        if bounds:
            metadata["bounds"] = bounds
        region = descriptor.get("filter_region")
        if isinstance(region, dict) and region:
            metadata["filter_region"] = dict(region)

        fallback_mode = "emf" if inferred in {"vector", "emf"} else "bitmap"
        metadata["fallback"] = fallback_mode
        effect = CustomEffect(
            drawingml=f"<!-- svg2ooxml:descriptor fallback strategy={inferred} filter={filter_id} -->"
        )
        return [
            FilterEffectResult(
                effect=effect,
                strategy="vector" if inferred == "emf" else inferred,
                metadata=metadata,
                fallback=fallback_mode,
            )
        ]

    attach_emf_metadata = staticmethod(_attach_emf_metadata)
    attach_raster_metadata = staticmethod(_attach_raster_metadata)


__all__ = [
    "LightweightFilterPlanner",
    "LightweightFilterRenderer",
]
