"""Lightweight filter pipeline used when full render dependencies are unavailable."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import (
    FilterRenderer as DrawingMLFilterRenderer,
)
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters import planner_common as _common
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.palette import (
    attach_emf_metadata as _attach_emf_metadata,
)
from svg2ooxml.filters.palette import (
    attach_raster_metadata as _attach_raster_metadata,
)
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.utils import parse_float_list
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult


class LightweightFilterPlanner:
    """Subset planner that avoids any raster/filter execution imports."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def descriptor_is_neutral(self, descriptor: Any | None) -> bool:
        primitives = getattr(descriptor, "primitives", None)
        if descriptor is None or not primitives:
            return False
        return all(self._primitive_is_neutral(primitive) for primitive in primitives)

    def descriptor_payload(
        self,
        context: FilterContext,
        descriptor: Any | None,
    ) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
        payload: dict[str, Any] | None = None
        bounds: dict[str, float | Any] | None = None

        options = context.options if isinstance(context.options, dict) else {}
        if isinstance(options, dict):
            candidate = options.get("resvg_descriptor")
            if isinstance(candidate, dict):
                payload = dict(candidate)
            bbox_candidate = options.get("ir_bbox")
            if isinstance(bbox_candidate, dict):
                bounds = _common.finite_bounds(bbox_candidate)

        if payload is None and descriptor is not None:
            payload = self.serialize_descriptor(descriptor)

        if bounds is None and payload is not None:
            bounds = _common.numeric_region(payload.get("filter_region"))

        return payload, bounds

    def policy_primitive_overrides(
        self, context: FilterContext
    ) -> dict[str, dict[str, Any]]:
        options = context.options if isinstance(context.options, dict) else {}
        policy = options.get("policy")
        if not isinstance(policy, Mapping):
            return {}
        primitives = policy.get("primitives")
        if not isinstance(primitives, Mapping):
            return {}
        overrides: dict[str, dict[str, Any]] = {}
        for name, config in primitives.items():
            key = str(name).strip().lower()
            if not key or not isinstance(config, Mapping):
                continue
            entry: dict[str, Any] = {}
            entry.update(_common.policy_flag(config, "allow_resvg"))
            entry.update(_common.policy_flag(config, "allow_promotion"))
            entry.update(_common.policy_limit(config, "max_pixels"))
            entry.update(_common.policy_limit(config, "max_arithmetic_coeff", float))
            entry.update(_common.policy_limit(config, "max_offset_distance", float))
            entry.update(_common.policy_limit(config, "max_merge_inputs", int))
            entry.update(_common.policy_limit(config, "max_component_functions", int))
            entry.update(
                _common.policy_limit(config, "max_component_table_values", int)
            )
            entry.update(_common.policy_limit(config, "max_convolve_kernel", int))
            entry.update(_common.policy_limit(config, "max_convolve_order", int))
            if entry:
                overrides[key] = entry
        return overrides

    def infer_descriptor_strategy(
        self,
        descriptor: Mapping[str, Any],
        *,
        strategy_hint: str,
    ) -> str | None:
        return _common.infer_descriptor_strategy(
            descriptor,
            strategy_hint=strategy_hint,
        )

    @staticmethod
    def serialize_descriptor(descriptor: Any) -> dict[str, Any]:
        return _common.serialize_descriptor(descriptor)

    @staticmethod
    def _attribute(attributes: Mapping[str, Any], name: str) -> str | None:
        if name in attributes:
            return str(attributes[name])
        lowered = name.lower()
        for key, value in attributes.items():
            if str(key).lower() == lowered:
                return str(value)
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        if len(values) != 20:
            return False
        identity = [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
        ]
        tol = 1e-6
        return all(abs(a - b) <= tol for a, b in zip(values, identity, strict=True))

    def _primitive_is_neutral(self, primitive: Any) -> bool:
        tag = (getattr(primitive, "tag", "") or "").strip().lower()
        attrs = getattr(primitive, "attributes", {}) or {}
        if tag == "fegaussianblur":
            raw = self._attribute(attrs, "stdDeviation")
            std_values = parse_float_list(raw)
            if not std_values:
                return True
            return all(abs(value) <= 1e-6 for value in std_values[:2])
        if tag == "feoffset":
            dx = self._parse_float(self._attribute(attrs, "dx")) or 0.0
            dy = self._parse_float(self._attribute(attrs, "dy")) or 0.0
            return abs(dx) <= 1e-6 and abs(dy) <= 1e-6
        if tag == "fecolormatrix":
            matrix_type = (self._attribute(attrs, "type") or "matrix").strip().lower()
            if matrix_type != "matrix":
                return False
            values = parse_float_list(self._attribute(attrs, "values"))
            if not values:
                return True
            return self._is_identity_matrix(values)
        return False


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

    @staticmethod
    def attach_emf_metadata(
        existing_results: list[FilterEffectResult],
        emf_results: list[FilterEffectResult],
    ) -> list[FilterEffectResult]:
        return _attach_emf_metadata(existing_results, emf_results)

    @staticmethod
    def attach_raster_metadata(
        existing_results: list[FilterEffectResult],
        raster_results: list[FilterEffectResult],
    ) -> None:
        _attach_raster_metadata(existing_results, raster_results)


__all__ = [
    "LightweightFilterPlanner",
    "LightweightFilterRenderer",
]
