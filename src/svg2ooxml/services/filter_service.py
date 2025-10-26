"""Filter service scaffolding mirroring svg2pptx architecture."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from lxml import etree

from svg2ooxml.drawingml.emf_adapter import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import FilterRenderer
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import (
    ResolvedFilter,
    build_filter_element,
    resolve_filter_element,
)
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .conversion import ConversionServices


ALLOWED_STRATEGIES = {"auto", "native", "vector", "raster", "emf"}

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
        strategy = self._resolve_strategy(filter_context)

        if strategy in {"auto", "native"}:
            native_results = self._render_native(filter_element, filter_context)
            if native_results:
                results.extend(native_results)
                emf_sources.extend(result for result in native_results if result.fallback == "emf")
                if strategy == "native":
                    return results

        if strategy in {"vector", "emf"} or (not results and strategy == "auto"):
            computed_vector = self._render_vector(filter_element, filter_context)
            if computed_vector:
                emf_sources.extend(result for result in computed_vector if result.fallback == "emf")
                if results:
                    results.extend(computed_vector)
                else:
                    results = list(computed_vector)
                if strategy in {"vector", "emf"}:
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

        if strategy in {"auto", "raster"}:
            raster_results = self._render_raster(filter_element, filter_context, filter_ref, strategy=strategy)
            if raster_results:
                if descriptor_results:
                    self._attach_raster_metadata(results, raster_results)
                else:
                    results.extend(raster_results)

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
        return [
            FilterEffectResult(
                effect=effect,
                strategy=strategy if strategy in {"raster", "auto"} else "raster",
                metadata=dict(result.metadata or {}),
                fallback=result.fallback or "bitmap",
            )
        ]

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
