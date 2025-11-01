"""Filter service scaffolding mirroring svg2pptx architecture."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from lxml import etree

from svg2ooxml.drawingml.emf_adapter import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import FilterRenderer
from svg2ooxml.drawingml.raster_adapter import RasterAdapter, _surface_to_png
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import (
    ResolvedFilter,
    build_filter_element,
    build_filter_node,
    resolve_filter_element,
)
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.render.filters import UnsupportedPrimitiveError, apply_filter, plan_filter
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.render.surface import Surface
from svg2ooxml.services.filter_types import FilterEffectResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .conversion import ConversionServices


ALLOWED_STRATEGIES = {"auto", "native", "vector", "raster", "emf", "legacy", "resvg", "resvg-only"}

# Primitive tags that hint at preferred fallback strategies when native rendering fails.
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


class FilterService:
    """Manage SVG filter definitions and provide conversion hooks."""

    def __init__(
        self,
        *,
        policy_engine: Any | None = None,
        registry: FilterRegistry | None = None,
        logger: logging.Logger | None = None,
        palette_resolver: PaletteResolver | None = None,
        raster_adapter: RasterAdapter | None = None,
    ) -> None:
        self._descriptors: dict[str, ResolvedFilter] = {}
        self._materialized_filters: dict[str, etree._Element] = {}
        self._services: "ConversionServices | None" = None
        self._policy_engine = policy_engine
        self._registry = registry or self._create_registry()
        self._logger = logger or logging.getLogger(__name__)
        self._strategy: str = "auto"
        self._palette_resolver: PaletteResolver | None = palette_resolver
        self._renderer = FilterRenderer(logger=self._logger, palette_resolver=palette_resolver)
        self._raster_adapter = raster_adapter or RasterAdapter()
        self._resvg_counter: int = 0

    # ------------------------------------------------------------------ #
    # Binding & cloning                                                  #
    # ------------------------------------------------------------------ #

    def bind_services(self, services: "ConversionServices") -> None:
        """Allow the DI container to hydrate the service on registration."""
        self._services = services
        if self._policy_engine is None:
            self._policy_engine = services.resolve("policy_engine")
        self._configure_palette_resolver(services)
        existing = services.resolve("filters")
        if existing:
            self.update_definitions(existing)

    def clone(self) -> "FilterService":
        """Create a shallow copy that shares definitions and policy context."""
        clone = FilterService(
            policy_engine=self._policy_engine,
            registry=self._registry.clone() if self._registry else None,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
        )
        clone._descriptors = dict(self._descriptors)
        clone._materialized_filters = dict(self._materialized_filters)
        clone._resvg_counter = self._resvg_counter
        return clone

    # ------------------------------------------------------------------ #
    # Definition management                                              #
    # ------------------------------------------------------------------ #

    def update_definitions(
        self,
        filters: Mapping[str, ResolvedFilter | etree._Element] | None,
    ) -> None:
        """Replace the known filter definitions."""
        self._descriptors.clear()
        self._materialized_filters.clear()
        for filter_id, definition in (filters or {}).items():
            descriptor = self._coerce_descriptor(filter_id, definition)
            if descriptor is None:
                continue
            key = descriptor.filter_id or filter_id
            self._descriptors[key] = descriptor

    def register_filter(self, filter_id: str, definition: ResolvedFilter | etree._Element) -> None:
        """Register a single filter definition."""
        if not filter_id:
            raise ValueError("filter id must be non-empty")
        descriptor = self._coerce_descriptor(filter_id, definition)
        if descriptor is None:
            return
        key = descriptor.filter_id or filter_id
        self._descriptors[key] = descriptor
        self._materialized_filters.pop(key, None)

    def get(self, filter_id: str) -> ResolvedFilter | None:
        """Return the stored filter descriptor if known."""
        return self._descriptors.get(filter_id)

    def require(self, filter_id: str) -> ResolvedFilter:
        """Return the filter descriptor or raise if missing."""
        element = self.get(filter_id)
        if element is None:
            raise KeyError(f"filter {filter_id!r} is not defined")
        return element

    def ids(self) -> Iterable[str]:
        """Iterate over registered filter ids."""
        return tuple(self._descriptors.keys())

    # ------------------------------------------------------------------ #
    # Conversion hooks (stubs)                                           #
    # ------------------------------------------------------------------ #

    def get_filter_content(self, filter_id: str, *, context: Any | None = None) -> str | None:
        """Return DrawingML content for the requested filter reference."""
        descriptor = self.get(filter_id)
        if descriptor is None:
            return None
        element = self._materialize_filter(filter_id, descriptor)
        try:
            return etree.tostring(element, encoding="unicode")
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Failed to serialise filter %s", filter_id, exc_info=True)
            return None

    def resolve_effects(self, filter_ref: str, *, context: Any | None = None) -> list[FilterEffectResult]:
        """Resolve a filter reference into IR effect objects."""
        descriptor = self.get(filter_ref)
        if descriptor is None:
            self._logger.debug("Filter %s is not defined; skipping effect resolution", filter_ref)
            return []

        filter_element = self._materialize_filter(filter_ref, descriptor)
        filter_context = self._build_context(filter_element, context)
        descriptor_payload, bounds_payload = self._descriptor_payload(filter_context, descriptor)
        results: list[FilterEffectResult] = []
        emf_sources: list[FilterEffectResult] = []
        raster_results_cache: list[FilterEffectResult] = []
        strategy = self._resolve_strategy(filter_context)

        resvg_enabled = strategy not in {"legacy", "vector", "emf", "raster"}
        resvg_preferred = strategy in {"resvg", "resvg-only"}
        resvg_only = strategy == "resvg-only"

        resvg_result: FilterEffectResult | None = None
        if resvg_enabled:
            resvg_result = self._render_resvg_filter(descriptor, filter_context, filter_ref)
            if resvg_result is not None and resvg_only:
                return [resvg_result]

        if strategy in {"auto", "native", "legacy", "resvg", "resvg-only"}:
            native_results = self._render_native(filter_element, filter_context)
            if native_results:
                results.extend(native_results)
                emf_sources.extend(result for result in native_results if result.fallback == "emf")
                if strategy == "native" and not resvg_preferred:
                    return results

        if strategy in {"vector", "emf"} or (not results and strategy in {"auto", "legacy"}):
            computed_vector = self._render_vector(filter_element, filter_context)
            if computed_vector:
                emf_sources.extend(result for result in computed_vector if result.fallback == "emf")
                if results:
                    results.extend(computed_vector)
                else:
                    results = list(computed_vector)
                if strategy in {"vector", "emf"} and not resvg_preferred:
                    return results

        descriptor_results = self._descriptor_fallback(
            descriptor_payload,
            bounds_payload,
            filter_ref,
            strategy_hint=strategy,
        )
        if descriptor_results:
            results.extend(descriptor_results)
            if emf_sources:
                self._attach_emf_metadata(results, emf_sources)

        if strategy in {"auto", "raster", "legacy"}:
            raster_results = self._render_raster(filter_element, filter_context, filter_ref, strategy=strategy)
            if raster_results:
                raster_results_cache = list(raster_results)
                if descriptor_results:
                    self._attach_raster_metadata(results, raster_results)
                else:
                    results.extend(raster_results)
        if resvg_result is not None and resvg_preferred:
            preferred_results = [resvg_result]
            if emf_sources:
                self._attach_emf_metadata(preferred_results, emf_sources)
            if raster_results_cache:
                self._attach_raster_metadata(preferred_results, raster_results_cache)
            return preferred_results
        if resvg_result is not None and resvg_enabled:
            results.append(resvg_result)
        return results

    # ------------------------------------------------------------------ #
    # Accessors                                                          #
    # ------------------------------------------------------------------ #

    @property
    def policy_engine(self) -> Any | None:
        return self._policy_engine

    @property
    def registry(self) -> FilterRegistry | None:
        return self._registry

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _render_native(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        context.pipeline_state = context.pipeline_state or {}
        filter_results = self._registry.render_filter_element(element, context)
        return self._renderer.render(filter_results, context=context)

    def _render_vector(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        if self._registry is None:
            return []

        context.pipeline_state = {}
        filter_results = self._registry.render_filter_element(element, context)
        if not filter_results:
            return []

        coerced: list[FilterResult] = []
        for result in filter_results:
            metadata = dict(result.metadata or {})
            fallback = result.fallback or "emf"
            drawingml = result.drawingml
            if fallback not in {"emf", "vector"}:
                fallback = "emf"
                metadata.setdefault("vector_forced", True)
                drawingml = ""
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

        rendered = self._renderer.render(coerced, context=context)
        for effect in rendered:
            if effect.strategy not in {"vector", "emf"}:
                effect.strategy = "vector"
        return rendered

    def _render_raster(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
        *,
        strategy: str,
    ) -> list[FilterEffectResult]:
        result = self._rasterize_filter(element, context, filter_id)
        if result is None or not result.is_success():
            return []
        drawingml = result.drawingml or f"<!-- svg2ooxml:raster rel={filter_id} -->"
        effect = CustomEffect(drawingml=drawingml)
        metadata = dict(result.metadata or {})
        metadata.setdefault("renderer", "raster")
        return [
            FilterEffectResult(
                effect=effect,
                strategy=strategy if strategy in {"raster", "auto"} else "raster",
                metadata=metadata,
                fallback=result.fallback or "bitmap",
            )
        ]

    def _render_resvg_filter(
        self,
        descriptor: ResolvedFilter,
        filter_context: FilterContext,
        filter_id: str,
    ) -> FilterEffectResult | None:
        options_map = getattr(filter_context, "options", {})
        tracer = options_map.get("tracer") if isinstance(options_map, dict) else None

        def _trace(action: str, **meta: Any) -> None:
            if tracer is not None:
                payload = dict(meta)
                payload.setdefault("strategy", self._strategy)
                tracer.record_stage_event(
                    stage="filter",
                    action=action,
                    subject=filter_id,
                    metadata=payload,
                )

        _trace("resvg_attempt")
        try:
            filter_node = build_filter_node(descriptor)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug("Failed to construct filter node for %s", filter_id, exc_info=True)
            _trace("resvg_build_failed", error=str(exc))
            return None

        plan = plan_filter(filter_node)
        if plan is None:
            _trace("resvg_plan_unsupported")
            return None

        try:
            bounds = self._resvg_bounds(options_map, descriptor)
            viewport = self._resvg_viewport(bounds)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug("Failed to compute resvg viewport for %s", filter_id, exc_info=True)
            _trace("resvg_viewport_failed", error=str(exc))
            return None

        source_surface = self._seed_source_surface(viewport.width, viewport.height)
        try:
            result_surface = apply_filter(source_surface, plan, bounds, viewport)
        except UnsupportedPrimitiveError as exc:
            _trace("resvg_unsupported_primitive", primitive=str(exc))
            return None
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug("Resvg filter application failed for %s", filter_id, exc_info=True)
            _trace("resvg_execution_failed", error=str(exc))
            return None

        png_bytes = _surface_to_png(result_surface)
        self._resvg_counter += 1
        relationship_id = f"rIdResvgFilter{self._resvg_counter}"

        descriptor_payload = self._serialize_descriptor(descriptor)
        primitives = [primitive.tag for primitive in descriptor.primitives]
        metadata: dict[str, Any] = {
            "renderer": "resvg",
            "filter_id": filter_id,
            "filter_units": descriptor.filter_units,
            "primitive_units": descriptor.primitive_units,
            "primitives": primitives,
            "width_px": viewport.width,
            "height_px": viewport.height,
            "descriptor": descriptor_payload,
            "bounds": {
                "x": bounds[0],
                "y": bounds[1],
                "width": bounds[2] - bounds[0],
                "height": bounds[3] - bounds[1],
            },
            "plan_primitives": [
                {
                    "tag": primitive_plan.tag,
                    "inputs": list(primitive_plan.inputs),
                    "result": primitive_plan.result_name,
                }
                for primitive_plan in plan.primitives
            ],
        }
        metadata["fallback_assets"] = [
            {
                "type": "raster",
                "format": "png",
                "data": png_bytes,
                "relationship_id": relationship_id,
                "width_px": viewport.width,
                "height_px": viewport.height,
            }
        ]

        effect = CustomEffect(drawingml=f"<!-- svg2ooxml:resvg filter={filter_id} -->")
        _trace(
            "resvg_success",
            primitive_count=len(plan.primitives),
            width_px=viewport.width,
            height_px=viewport.height,
        )
        return FilterEffectResult(
            effect=effect,
            strategy="resvg",
            metadata=metadata,
            fallback="bitmap",
        )

    def _resvg_bounds(
        self,
        options: Mapping[str, Any] | None,
        descriptor: ResolvedFilter,
    ) -> tuple[float, float, float, float]:
        bbox: Mapping[str, Any] = {}
        if isinstance(options, Mapping):
            candidate = options.get("ir_bbox")
            if isinstance(candidate, Mapping):
                bbox = candidate

        x = self._coerce_float(bbox.get("x"), 0.0)
        y = self._coerce_float(bbox.get("y"), 0.0)
        width = self._coerce_float(bbox.get("width"), 0.0)
        height = self._coerce_float(bbox.get("height"), 0.0)

        region = descriptor.region or {}
        region_width = self._coerce_float(region.get("width"), 0.0)
        region_height = self._coerce_float(region.get("height"), 0.0)

        base_width = width if width > 0 else 128.0
        base_height = height if height > 0 else 96.0

        if descriptor.filter_units == "objectBoundingBox" and region_width > 0:
            width = max(width, region_width * base_width)
        elif region_width > 0:
            width = max(width, region_width)
        if descriptor.filter_units == "objectBoundingBox" and region_height > 0:
            height = max(height, region_height * base_height)
        elif region_height > 0:
            height = max(height, region_height)

        if width <= 0:
            width = base_width
        if height <= 0:
            height = base_height

        width = max(width, 1.0)
        height = max(height, 1.0)
        return (x, y, x + width, y + height)

    def _resvg_viewport(self, bounds: tuple[float, float, float, float]) -> Viewport:
        min_x, min_y, max_x, max_y = bounds
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        width_px = max(1, int(math.ceil(width)))
        height_px = max(1, int(math.ceil(height)))
        scale_x = width_px / width
        scale_y = height_px / height
        return Viewport(
            width=width_px,
            height=height_px,
            min_x=min_x,
            min_y=min_y,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def _seed_source_surface(self, width: int, height: int) -> Surface:
        width = max(1, width)
        height = max(1, height)
        surface = Surface.make(width, height)
        xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

        red = 0.15 + 0.75 * xs
        green = 0.2 + 0.6 * (1.0 - ys)
        radial = np.sqrt((xs - 0.5) ** 2 + (ys - 0.5) ** 2)
        blue = np.clip(0.9 - 0.8 * radial, 0.1, 0.9)

        base_alpha = np.clip(0.6 + 0.4 * (1.0 - radial * 1.2), 0.25, 1.0)
        stripe = ((xs + ys) % 0.25) < 0.02
        base_alpha = np.where(stripe, np.minimum(base_alpha, 0.4), base_alpha)

        surface.data[..., 0] = red
        surface.data[..., 1] = green
        surface.data[..., 2] = blue
        surface.data[..., 3] = base_alpha
        surface.data[..., :3] *= surface.data[..., 3:4]
        return surface

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if math.isnan(number) or math.isinf(number):
            return default
        return number

    def _rasterize_filter(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
    ) -> FilterResult | None:
        try:
            raster = self._raster_adapter.render_filter(
                filter_id=filter_id,
                filter_element=element,
                context=context,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug("Raster adapter failed for %s: %s", filter_id, exc)
            raster = None

        if raster is None:
            placeholder = self._raster_adapter.generate_placeholder(
                metadata={"renderer": "placeholder", "filter_id": filter_id}
            )
            asset = {
                "type": "raster",
                "format": "png",
                "data": placeholder.image_bytes,
                "relationship_id": placeholder.relationship_id,
                "width_px": placeholder.width_px,
                "height_px": placeholder.height_px,
            }
            metadata = dict(placeholder.metadata)
            metadata.setdefault("fallback_assets", []).append(asset)
            drawingml = f"<!-- svg2ooxml:raster placeholder rel={placeholder.relationship_id} filter={filter_id} -->"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback="bitmap",
                metadata=metadata,
                warnings=["Raster fallback placeholder used"],
            )

        asset = {
            "type": "raster",
            "format": "png",
            "data": raster.image_bytes,
            "relationship_id": raster.relationship_id,
            "width_px": raster.width_px,
            "height_px": raster.height_px,
        }
        metadata = dict(raster.metadata)
        metadata.setdefault("fallback_assets", []).append(asset)
        drawingml = f"<!-- svg2ooxml:raster rel={raster.relationship_id} filter={filter_id} -->"
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback="bitmap",
            metadata=metadata,
        )

    def _create_registry(self) -> FilterRegistry:
        try:
            registry = FilterRegistry()
            registry.register_default_filters()
            return registry
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Filter registry initialisation failed", exc_info=True)
            return FilterRegistry()

    def _build_context(self, filter_element: etree._Element, extra: Any | None) -> FilterContext:
        options: dict[str, Any] = {}
        if isinstance(extra, dict):
            options.update(extra)
        viewport = None
        services = self._services
        if services is not None:
            width = getattr(services, "viewport_width", None)
            height = getattr(services, "viewport_height", None)
            if width is not None or height is not None:
                viewport = {"width": width, "height": height}
        return FilterContext(
            filter_element=filter_element,
            services=services,
            policy_engine=self._policy_engine,
            options=options,
            viewport=viewport,
        )

    def set_strategy(self, strategy: str) -> None:
        """Configure the preferred filter rendering strategy."""

        normalized = strategy.lower()
        if normalized not in ALLOWED_STRATEGIES:
            raise ValueError(f"Unsupported filter strategy '{strategy}'")
        self._strategy = normalized

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver used for EMF fallback rendering."""

        self._palette_resolver = resolver
        self._renderer.set_palette_resolver(resolver)

    # ------------------------------------------------------------------ #
    # Strategy helpers                                                   #
    # ------------------------------------------------------------------ #

    def _configure_palette_resolver(self, services: "ConversionServices") -> None:
        resolver = self._extract_palette_resolver(services)
        if resolver is not None:
            self.set_palette_resolver(resolver)
        elif self._palette_resolver is not None:
            self._renderer.set_palette_resolver(self._palette_resolver)

    def _extract_palette_resolver(self, services: "ConversionServices") -> PaletteResolver | None:
        candidate_names = (
            "filter_palette_resolver",
            "palette_resolver",
            "filter_palette",
        )
        for name in candidate_names:
            resolver = services.resolve(name)
            if resolver is None:
                resolver = getattr(services, name, None)
            coerced = self._coerce_palette_resolver(resolver)
            if coerced is not None:
                return coerced

        theming_candidates = (
            services.resolve("theme"),
            services.resolve("theming"),
            getattr(services, "theme_service", None),
            getattr(services, "theming_service", None),
        )
        for theming in theming_candidates:
            coerced = self._coerce_palette_resolver(theming)
            if coerced is not None:
                return coerced
            if theming is None:
                continue
            attr_names = (
                "resolve_filter_palette",
                "get_filter_palette_resolver",
                "palette_resolver",
                "resolve_palette",
                "resolve",
            )
            for attr in attr_names:
                bound = getattr(theming, attr, None)
                coerced = self._coerce_palette_resolver(bound)
                if coerced is not None:
                    return coerced

        return None

    def _coerce_palette_resolver(self, candidate: Any) -> PaletteResolver | None:
        if candidate is None:
            return None
        if callable(candidate):
            return cast(PaletteResolver, candidate)
        method_names = (
            "resolve_filter_palette",
            "get_filter_palette_resolver",
            "palette_resolver",
            "resolve_palette",
            "resolve",
        )
        for name in method_names:
            method = getattr(candidate, name, None)
            if callable(method):
                return cast(PaletteResolver, method)
        return None

    def _resolve_strategy(self, context: FilterContext) -> str:
        policy_options = {}
        if isinstance(context.options, dict):
            policy_options = context.options.get("policy") or {}

        policy_strategy = policy_options.get("strategy")
        if isinstance(policy_strategy, str):
            normalized = policy_strategy.strip().lower()
            if normalized in ALLOWED_STRATEGIES:
                return normalized

        return self._strategy

    @staticmethod
    def _attach_emf_metadata(
        existing_results: list[FilterEffectResult],
        emf_results: list[FilterEffectResult],
    ) -> None:
        if not existing_results or not emf_results:
            return

        target = existing_results[-1]
        metadata = dict(target.metadata or {})
        assets = metadata.setdefault("fallback_assets", [])
        vector_asset_pool: list[dict[str, Any]] = []

        # Preserve the first EMF asset for downstream consumers while allowing additional metadata.
        for emf_result in emf_results:
            emf_meta = emf_result.metadata if isinstance(emf_result.metadata, dict) else {}
            emf_assets = list(emf_meta.get("fallback_assets") or [])
            if emf_assets:
                vector_asset_pool.extend(emf_assets)
            emf_summary = emf_meta.get("emf_asset")
            if emf_summary and "emf_asset" not in metadata:
                metadata["emf_asset"] = emf_summary
            elif emf_summary:
                metadata.setdefault("emf_assets", []).append(emf_summary)

        if vector_asset_pool:
            assets[0:0] = vector_asset_pool

        existing_results[-1] = FilterEffectResult(
            effect=target.effect,
            strategy=target.strategy,
            metadata=metadata,
            fallback=target.fallback,
        )

    @staticmethod
    def _attach_raster_metadata(
        existing_results: list[FilterEffectResult],
        raster_results: list[FilterEffectResult],
    ) -> None:
        if not existing_results:
            return
        target = existing_results[-1]
        metadata = dict(target.metadata or {})
        assets = metadata.setdefault("fallback_assets", [])
        for raster in raster_results:
            raster_meta = raster.metadata if isinstance(raster.metadata, dict) else {}
            if "renderer" in raster_meta:
                metadata.setdefault("renderer", raster_meta.get("renderer"))
            for key in ("width_px", "height_px", "filter_units", "primitive_units", "descriptor"):
                if key in raster_meta and key not in metadata:
                    metadata[key] = raster_meta[key]
            for asset in raster_meta.get("fallback_assets", []) or []:
                assets.append(asset)
        existing_results[-1] = FilterEffectResult(
            effect=target.effect,
            strategy=target.strategy,
            metadata=metadata,
            fallback=target.fallback,
        )

    def _materialize_filter(self, filter_id: str, descriptor: ResolvedFilter) -> etree._Element:
        cached = self._materialized_filters.get(filter_id)
        if cached is not None:
            return cached
        element = build_filter_element(descriptor)
        self._materialized_filters[filter_id] = element
        return element

    def _coerce_descriptor(
        self,
        filter_id: str,
        definition: ResolvedFilter | etree._Element,
    ) -> ResolvedFilter | None:
        if isinstance(definition, ResolvedFilter):
            descriptor = definition
        elif isinstance(definition, etree._Element):
            descriptor = resolve_filter_element(definition)
        else:
            self._logger.debug("Unsupported filter definition type for %s: %r", filter_id, type(definition))
            return None
        if not descriptor.filter_id:
            descriptor = replace(descriptor, filter_id=filter_id)
        return descriptor

    @staticmethod
    def _serialize_descriptor(descriptor: ResolvedFilter) -> dict[str, Any]:
        return {
            "filter_id": descriptor.filter_id,
            "filter_units": descriptor.filter_units,
            "primitive_units": descriptor.primitive_units,
            "primitive_count": len(descriptor.primitives),
            "primitive_tags": [primitive.tag for primitive in descriptor.primitives],
            "filter_region": dict(descriptor.region or {}),
        }

    @staticmethod
    def _numeric_region(region: Mapping[str, Any] | None) -> dict[str, float] | None:
        if not isinstance(region, Mapping):
            return None
        numeric: dict[str, float] = {}
        for key in ("x", "y", "width", "height"):
            value = region.get(key)
            if isinstance(value, (int, float)):
                numeric[key] = float(value)
                continue
            if isinstance(value, str):
                try:
                    numeric[key] = float(value)
                except ValueError:
                    continue
        return numeric or None

    def _descriptor_fallback(
        self,
        descriptor: Mapping[str, Any] | None,
        bounds: Mapping[str, Any] | None,
        filter_id: str,
        *,
        strategy_hint: str,
    ) -> list[FilterEffectResult] | None:
        if descriptor is None:
            return None

        inferred = self._infer_descriptor_strategy(descriptor, strategy_hint=strategy_hint)
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
            metadata.setdefault("filter_region", dict(region))

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

    def _descriptor_payload(
        self,
        context: FilterContext,
        descriptor: ResolvedFilter | None,
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
            payload = self._serialize_descriptor(descriptor)

        if bounds is None and payload is not None:
            numeric_bounds = self._numeric_region(payload.get("filter_region"))
            if numeric_bounds:
                bounds = numeric_bounds

        return payload, bounds

    def _infer_descriptor_strategy(
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


__all__ = ["FilterService"]
