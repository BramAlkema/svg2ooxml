"""Lightweight filter pipeline used when full render dependencies are unavailable."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import (
    FilterRenderer as DrawingMLFilterRenderer,
)
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.utils import parse_float_list
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult

_VECTOR_HINT_TAGS = {
    "fecomponenttransfer",
    "fedisplacementmap",
    "feturbulence",
    "feconvolvematrix",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fetile",
    "fediffuselighting",
    "fespecularlighting",
}
_RASTER_HINT_TAGS = {
    "feimage",
}


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
                bounds = {
                    key: bbox_candidate[key]
                    for key in ("x", "y", "width", "height")
                    if key in bbox_candidate
                }

        if payload is None and descriptor is not None:
            payload = self.serialize_descriptor(descriptor)

        if bounds is None and payload is not None:
            region = payload.get("filter_region")
            if isinstance(region, dict):
                numeric: dict[str, float | Any] = {}
                for key in ("x", "y", "width", "height"):
                    if key in region:
                        numeric[key] = region[key]
                if numeric:
                    bounds = numeric

        return payload, bounds

    def infer_descriptor_strategy(
        self,
        descriptor: Mapping[str, Any],
        *,
        strategy_hint: str,
    ) -> str | None:
        tags = descriptor.get("primitive_tags")
        if not isinstance(tags, Iterable):
            return None
        lowered = {str(tag).strip().lower() for tag in tags if tag}
        if not lowered:
            return "vector" if strategy_hint in {"vector", "emf"} else None

        if any(tag in _RASTER_HINT_TAGS for tag in lowered):
            return "raster"
        if any(tag in _VECTOR_HINT_TAGS for tag in lowered):
            return "vector"

        if strategy_hint in {"vector", "emf"}:
            return "vector"
        if strategy_hint == "raster":
            return "raster"
        return None

    @staticmethod
    def serialize_descriptor(descriptor: Any) -> dict[str, Any]:
        primitives = getattr(descriptor, "primitives", ()) or ()
        region = getattr(descriptor, "region", {}) or {}
        return {
            "filter_id": getattr(descriptor, "filter_id", None),
            "filter_units": getattr(descriptor, "filter_units", None),
            "primitive_units": getattr(descriptor, "primitive_units", None),
            "primitive_count": len(primitives),
            "primitive_tags": [primitive.tag for primitive in primitives],
            "filter_region": dict(region),
            "primitive_metadata": [dict(getattr(primitive, "extras", {}) or {}) for primitive in primitives],
        }

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
            1.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1.0, 0.0,
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
        inferred = self._planner.infer_descriptor_strategy(descriptor, strategy_hint=strategy_hint)
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
        if not existing_results or not emf_results:
            return existing_results
        target = existing_results[-1]
        if target.fallback != "emf":
            return existing_results

        metadata = dict(target.metadata or {})
        assets = list(metadata.get("fallback_assets") or [])
        for result in emf_results:
            source = result.metadata if isinstance(result.metadata, dict) else {}
            source_assets = source.get("fallback_assets")
            if not isinstance(source_assets, list):
                continue
            for asset in source_assets:
                if isinstance(asset, dict) and asset.get("type") == "emf":
                    assets.append(dict(asset))
                    break
            if assets:
                break
        if not assets:
            return existing_results

        metadata["fallback_assets"] = assets
        base = list(existing_results)
        base[-1] = replace(target, metadata=metadata, fallback="emf")
        return base

    @staticmethod
    def attach_raster_metadata(
        existing_results: list[FilterEffectResult],
        raster_results: list[FilterEffectResult],
    ) -> None:
        if not existing_results:
            return
        target = existing_results[-1]
        metadata = dict(target.metadata or {})
        assets = list(metadata.get("fallback_assets") or [])
        for raster in raster_results:
            source = raster.metadata if isinstance(raster.metadata, dict) else {}
            source_assets = source.get("fallback_assets")
            if isinstance(source_assets, list):
                for asset in source_assets:
                    if isinstance(asset, dict):
                        assets.append(dict(asset))
        if not assets:
            return
        metadata["fallback_assets"] = assets
        existing_results[-1] = replace(target, metadata=metadata)


__all__ = [
    "LightweightFilterPlanner",
    "LightweightFilterRenderer",
]
