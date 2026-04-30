"""High-level filter effect resolution for ``FilterService``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from svg2ooxml.services.filter_types import FilterEffectResult

_RASTER_ONLY_FILTER_INPUTS = frozenset(
    {
        "BackgroundAlpha",
        "BackgroundImage",
    }
)


class FilterResolutionMixin:
    """Resolve filter references into IR effect results."""

    def resolve_effects(
        self,
        filter_ref: str,
        *,
        context: Any | None = None,
    ) -> list[FilterEffectResult]:
        """Resolve a filter reference into IR effect objects."""
        lookup_id = self._lookup_filter_id(filter_ref)
        if lookup_id is None:
            return []
        filter_ref = lookup_id

        if not self._ensure_pipeline():
            return self._finalize_results(
                filter_ref,
                self._disabled_effects(filter_ref),
                context,
            )

        descriptor = self.get(filter_ref)
        if descriptor is None:
            self._logger.debug(
                "Filter %s is not defined; skipping effect resolution",
                filter_ref,
            )
            return self._finalize_results(filter_ref, [], context)

        filter_element = self._materialize_filter(filter_ref, descriptor)
        filter_context = self._build_context(filter_element, context)
        descriptor_payload, bounds_payload = self._descriptor_payload(
            filter_context,
            descriptor,
        )
        results: list[FilterEffectResult] = []
        emf_sources: list[FilterEffectResult] = []
        raster_results_cache: list[FilterEffectResult] = []
        descriptor_results: list[FilterEffectResult] | None = None
        strategy = self._resolve_strategy(filter_context, descriptor)
        filter_context.options["resolved_strategy"] = strategy

        resvg_enabled = strategy not in {"vector", "emf", "raster"}
        resvg_preferred = strategy in {"resvg", "resvg-only"}
        resvg_only = strategy == "resvg-only"

        if strategy in {"raster", "resvg"} and _uses_raster_only_filter_input(
            descriptor
        ):
            raster_results = self._render_raster(
                filter_element,
                filter_context,
                filter_ref,
                strategy=strategy,
            )
            if raster_results:
                return self._finalize_results(
                    filter_ref,
                    _annotate_raster_input_results(raster_results),
                    filter_context,
                )
            if strategy == "raster":
                return self._finalize_results(filter_ref, [], filter_context)

        resvg_result = None
        if resvg_enabled:
            resvg_result = self._render_resvg_filter(
                descriptor,
                filter_element,
                filter_context,
                filter_ref,
            )
            if resvg_result is not None and resvg_only:
                return self._finalize_results(
                    filter_ref, [resvg_result], filter_context
                )
            if resvg_result is None and resvg_only:
                return self._finalize_results(filter_ref, [], filter_context)

        if strategy in {"auto", "native", "resvg", "resvg-only"}:
            native_results = self._render_native(filter_element, filter_context)
            if native_results:
                results.extend(native_results)
                emf_sources.extend(
                    result for result in native_results if result.fallback == "emf"
                )
                if strategy == "native" and not resvg_preferred:
                    return self._finalize_results(filter_ref, results, filter_context)
                if strategy == "auto" and not resvg_preferred:
                    if all(result.fallback is None for result in native_results) or all(
                        isinstance(result.metadata, dict)
                        and result.metadata.get("terminal_stack") is True
                        for result in native_results
                    ):
                        return self._finalize_results(
                            filter_ref, results, filter_context
                        )

        skip_fallbacks = (
            resvg_result is not None and not resvg_preferred and not results
        )

        if not skip_fallbacks:
            descriptor_results, raster_results_cache, results, emf_sources = (
                self._resolve_fallbacks(
                    strategy=strategy,
                    filter_element=filter_element,
                    filter_context=filter_context,
                    filter_ref=filter_ref,
                    descriptor_payload=descriptor_payload,
                    bounds_payload=bounds_payload,
                    results=results,
                    emf_sources=emf_sources,
                )
            )

        if resvg_result is not None and resvg_preferred:
            return self._resolve_preferred_resvg_results(
                filter_ref,
                filter_context,
                resvg_result,
                results,
                emf_sources,
                raster_results_cache,
            )
        if resvg_result is not None and resvg_enabled:
            if not results:
                return self._finalize_results(
                    filter_ref, [resvg_result], filter_context
                )
            results.append(resvg_result)
        return self._finalize_results(filter_ref, results, filter_context)

    def _resolve_fallbacks(
        self,
        *,
        strategy: str,
        filter_element,
        filter_context,
        filter_ref: str,
        descriptor_payload,
        bounds_payload,
        results: list[FilterEffectResult],
        emf_sources: list[FilterEffectResult],
    ) -> tuple[
        list[FilterEffectResult] | None,
        list[FilterEffectResult],
        list[FilterEffectResult],
        list[FilterEffectResult],
    ]:
        descriptor_results = None
        raster_results_cache: list[FilterEffectResult] = []
        if strategy in {"vector", "emf", "auto"}:
            computed_vector = self._render_vector(filter_element, filter_context)
            if computed_vector:
                emf_sources.extend(
                    result for result in computed_vector if result.fallback == "emf"
                )
                if results:
                    results.extend(computed_vector)
                else:
                    results = list(computed_vector)
                if strategy in {"vector", "emf"}:
                    return (
                        descriptor_results,
                        raster_results_cache,
                        results,
                        emf_sources,
                    )

        if strategy != "raster":
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

        if strategy in {"auto", "raster"}:
            raster_results = self._render_raster(
                filter_element,
                filter_context,
                filter_ref,
                strategy=strategy,
            )
            if raster_results:
                raster_results_cache = list(raster_results)
                if descriptor_results:
                    self._attach_raster_metadata(results, raster_results)
                else:
                    results.extend(raster_results)
        return descriptor_results, raster_results_cache, results, emf_sources

    def _resolve_preferred_resvg_results(
        self,
        filter_ref: str,
        filter_context,
        resvg_result: FilterEffectResult,
        results: list[FilterEffectResult],
        emf_sources: list[FilterEffectResult],
        raster_results_cache: list[FilterEffectResult],
    ) -> list[FilterEffectResult]:
        native_results = [result for result in results if result.fallback is None]
        if native_results and not _prefer_resvg_bitmap_result(resvg_result):
            return self._finalize_results(filter_ref, native_results, filter_context)
        preferred_results = [resvg_result]
        if emf_sources:
            preferred_results = self._attach_emf_metadata(
                preferred_results, emf_sources
            )
        if raster_results_cache:
            self._attach_raster_metadata(preferred_results, raster_results_cache)
        return self._finalize_results(filter_ref, preferred_results, filter_context)


__all__ = ["FilterResolutionMixin"]


def _uses_raster_only_filter_input(descriptor: Any) -> bool:
    primitives = getattr(descriptor, "primitives", ())
    if not isinstance(primitives, Iterable):
        return False
    return any(_primitive_uses_raster_only_input(primitive) for primitive in primitives)


def _primitive_uses_raster_only_input(primitive: Any) -> bool:
    attributes = getattr(primitive, "attributes", None)
    if isinstance(attributes, dict):
        for key in ("in", "in2"):
            value = attributes.get(key)
            if isinstance(value, str) and value.strip() in _RASTER_ONLY_FILTER_INPUTS:
                return True
    children = getattr(primitive, "children", ())
    if isinstance(children, Iterable):
        return any(_primitive_uses_raster_only_input(child) for child in children)
    return False


def _annotate_raster_input_results(
    results: list[FilterEffectResult],
) -> list[FilterEffectResult]:
    annotated: list[FilterEffectResult] = []
    for result in results:
        metadata = dict(result.metadata or {})
        metadata.setdefault("raster_reason", "svg_filter_input_surface")
        annotated.append(replace(result, metadata=metadata))
    return annotated


def _prefer_resvg_bitmap_result(result: FilterEffectResult) -> bool:
    if result.fallback != "bitmap":
        return False
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    if metadata.get("renderer") != "resvg":
        return False
    primitives = metadata.get("primitives")
    if not isinstance(primitives, list):
        return False
    return any(
        isinstance(primitive, str)
        and primitive.lower() in {"fediffuselighting", "fespecularlighting"}
        for primitive in primitives
    )
