"""Filter service scaffolding mirroring svg2pptx architecture."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from lxml import etree

from svg2ooxml.drawingml.emf_adapter import PaletteResolver
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.renderer import FilterRenderer as FilterPipelineRenderer
from svg2ooxml.filters.resvg_bridge import (
    ResolvedFilter,
    build_filter_element,
    resolve_filter_element,
)
from svg2ooxml.services.filter_types import FilterEffectResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .conversion import ConversionServices


ALLOWED_STRATEGIES = {
    "auto",
    "native",
    "native-if-neutral",
    "vector",
    "raster",
    "emf",
    "legacy",
    "resvg",
    "resvg-only",
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
        self._services: ConversionServices | None = None
        self._policy_engine = policy_engine
        self._registry = registry or self._create_registry()
        self._logger = logger or logging.getLogger(__name__)
        self._strategy: str = "auto"
        self._palette_resolver: PaletteResolver | None = palette_resolver
        self._planner = FilterPlanner(logger=self._logger)
        self._renderer = FilterPipelineRenderer(
            registry=self._registry,
            planner=self._planner,
            logger=self._logger,
            palette_resolver=palette_resolver,
            raster_adapter=raster_adapter,
        )

    # ------------------------------------------------------------------ #
    # Binding & cloning                                                  #
    # ------------------------------------------------------------------ #

    def bind_services(self, services: ConversionServices) -> None:
        """Allow the DI container to hydrate the service on registration."""
        self._services = services
        if self._policy_engine is None:
            self._policy_engine = services.resolve("policy_engine")
        self._configure_palette_resolver(services)
        existing = services.resolve("filters")
        if existing:
            self.update_definitions(existing)

    def clone(self) -> FilterService:
        """Create a shallow copy that shares definitions and policy context."""
        clone = FilterService(
            policy_engine=self._policy_engine,
            registry=self._registry.clone() if self._registry else None,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
        )
        clone._descriptors = dict(self._descriptors)
        clone._materialized_filters = dict(self._materialized_filters)
        clone._renderer = self._renderer.clone(
            registry=clone._registry,
            planner=clone._planner,
        )
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
        descriptor_results: list[FilterEffectResult] | None = None
        strategy = self._resolve_strategy(filter_context, descriptor)

        resvg_enabled = strategy not in {"legacy", "vector", "emf", "raster"}
        resvg_preferred = strategy in {"resvg", "resvg-only"}
        resvg_only = strategy == "resvg-only"

        resvg_result: FilterEffectResult | None = None
        if resvg_enabled:
            resvg_result = self._render_resvg_filter(descriptor, filter_element, filter_context, filter_ref)
            if resvg_result is not None and resvg_only:
                return [resvg_result]

        if strategy in {"auto", "native", "legacy", "resvg", "resvg-only"}:
            native_results = self._render_native(filter_element, filter_context)
            if native_results:
                results.extend(native_results)
                emf_sources.extend(result for result in native_results if result.fallback == "emf")
                if strategy == "native" and not resvg_preferred:
                    return results
                if strategy == "auto" and not resvg_preferred:
                    if all(result.fallback is None for result in native_results):
                        return results

        skip_legacy = resvg_result is not None and not resvg_preferred and not results

        if not skip_legacy:
            if strategy in {"vector", "emf", "auto", "legacy"}:
                computed_vector = self._render_vector(filter_element, filter_context)
                if computed_vector:
                    emf_sources.extend(
                        result for result in computed_vector if result.fallback == "emf"
                    )
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
                    results = self._attach_emf_metadata(results, emf_sources)

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
                preferred_results = self._attach_emf_metadata(preferred_results, emf_sources)
            if raster_results_cache:
                self._attach_raster_metadata(preferred_results, raster_results_cache)
            return preferred_results
        if resvg_result is not None and resvg_enabled:
            if not results:
                return [resvg_result]
            results.append(resvg_result)
        return results

    # ------------------------------------------------------------------ #
    # Accessors                                                          #
    # ------------------------------------------------------------------ #

    @property
    def policy_engine(self) -> Any | None:
        return self._policy_engine

    def set_policy_engine(self, engine: Any | None) -> None:
        """Update the policy engine used for filter evaluation."""

        self._policy_engine = engine

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
        return self._renderer.render_native(element, context)

    def _render_vector(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        return self._renderer.render_vector(element, context)

    def _render_raster(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
        *,
        strategy: str,
    ) -> list[FilterEffectResult]:
        return self._renderer.render_raster(element, context, filter_id, strategy=strategy)

    def _render_resvg_filter(
        self,
        descriptor: ResolvedFilter,
        filter_element: etree._Element,
        filter_context: FilterContext,
        filter_id: str,
    ) -> FilterEffectResult | None:
        options_map = getattr(filter_context, "options", {})
        tracer = options_map.get("tracer") if isinstance(options_map, dict) else None

        def _trace(action: str, **meta: Any) -> None:
            if tracer is None:
                return
            payload = dict(meta)
            payload.setdefault("strategy", self._strategy)
            tracer.record_stage_event(
                stage="filter",
                action=action,
                subject=filter_id,
                metadata=payload,
            )

        return self._renderer.render_resvg_filter(
            descriptor,
            filter_element,
            filter_context,
            filter_id,
            trace=_trace,
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
        services = self._services
        if "source_path" not in options and services is not None and hasattr(services, "resolve"):
            source_path = services.resolve("source_path")
            if isinstance(source_path, str) and source_path:
                options["source_path"] = source_path
        viewport = None
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

    def _configure_palette_resolver(self, services: ConversionServices) -> None:
        resolver = self._extract_palette_resolver(services)
        if resolver is not None:
            self.set_palette_resolver(resolver)
        elif self._palette_resolver is not None:
            self._renderer.set_palette_resolver(self._palette_resolver)

    def _extract_palette_resolver(self, services: ConversionServices) -> PaletteResolver | None:
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

    def _resolve_strategy(self, context: FilterContext, descriptor: ResolvedFilter | None) -> str:
        policy_options = {}
        if isinstance(context.options, dict):
            policy_options = context.options.get("policy") or {}

        # Prioritize policy-defined strategy if present
        policy_strategy = policy_options.get("strategy")
        if isinstance(policy_strategy, str):
            normalized = policy_strategy.strip().lower()
            if normalized in ALLOWED_STRATEGIES:
                if normalized == "native-if-neutral":
                    if self._planner.descriptor_is_neutral(descriptor):
                        return "native"
                    return "emf"
                return normalized

        if self._strategy != "auto":
            if self._strategy == "native-if-neutral":
                if self._planner.descriptor_is_neutral(descriptor):
                    return "native"
                return "emf"
            return self._strategy

        return self._strategy

    def _attach_emf_metadata(
        self,
        existing_results: list[FilterEffectResult],
        emf_results: list[FilterEffectResult],
    ) -> list[FilterEffectResult]:
        return self._renderer.attach_emf_metadata(existing_results, emf_results)

    def _attach_raster_metadata(
        self,
        existing_results: list[FilterEffectResult],
        raster_results: list[FilterEffectResult],
    ) -> None:
        self._renderer.attach_raster_metadata(existing_results, raster_results)

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
    def _promotion_policy_violation(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        return FilterPlanner.promotion_policy_violation(tag, result, policy_entry)

    @staticmethod
    def _promotion_policy_allows(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> bool:
        return FilterPlanner.promotion_policy_allows(tag, result, policy_entry)

    def _descriptor_fallback(
        self,
        descriptor: Mapping[str, Any] | None,
        bounds: Mapping[str, Any] | None,
        filter_id: str,
        *,
        strategy_hint: str,
    ) -> list[FilterEffectResult] | None:
        return self._renderer.descriptor_fallback(
            dict(descriptor) if isinstance(descriptor, Mapping) else None,
            dict(bounds) if isinstance(bounds, Mapping) else None,
            filter_id,
            strategy_hint=strategy_hint,
        )

    def _descriptor_payload(
        self,
        context: FilterContext,
        descriptor: ResolvedFilter | None,
    ) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
        return self._planner.descriptor_payload(context, descriptor)


__all__ = ["FilterService"]
