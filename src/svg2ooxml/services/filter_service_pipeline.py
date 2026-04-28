"""Pipeline setup and strategy helpers for ``FilterService``."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.services.filter_palette import extract_palette_resolver
from svg2ooxml.services.filter_pipeline_runtime import (
    ALLOWED_STRATEGIES,
)
from svg2ooxml.services.filter_types import FilterEffectResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .conversion import ConversionServices


def _load_pipeline():
    from svg2ooxml.services import filter_service as service_module

    return service_module._load_filter_pipeline()


def _pipeline_warning(error: Exception | None) -> str:
    from svg2ooxml.services import filter_service as service_module

    return service_module._pipeline_warning_message(error)


class FilterServicePipelineMixin:
    """Bind services, configure renderers, and resolve pipeline strategy."""

    def bind_services(self, services: ConversionServices) -> None:
        """Allow the DI container to hydrate the service on registration."""
        self._services = services
        if self._policy_engine is None:
            self._policy_engine = services.resolve("policy_engine")
        self._configure_palette_resolver(services)
        existing = services.resolve("filters")
        if existing:
            self.update_definitions(existing)

    def clone(self):
        """Create a shallow copy that shares definitions and policy context."""
        from svg2ooxml.services.filter_service import FilterService

        clone = FilterService(
            policy_engine=self._policy_engine,
            registry=self._registry.clone() if self._registry else None,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
        )
        clone._descriptors = dict(self._descriptors)
        clone._materialized_filters = {
            key: deepcopy(value) for key, value in self._materialized_filters.items()
        }
        clone._strategy = self._strategy
        clone._raster_adapter = self._raster_adapter
        clone._pipeline_error = self._pipeline_error
        clone._pipeline_warned = self._pipeline_warned
        clone._runtime_capability = self._runtime_capability
        if self._planner is not None:
            clone._planner = self._planner
        if self._renderer is not None and clone._planner is not None:
            clone._renderer = self._renderer.clone(
                registry=clone._registry,
                planner=clone._planner,
            )
        return clone

    def _create_registry(self) -> FilterRegistry:
        try:
            registry = FilterRegistry()
            registry.register_default_filters()
            return registry
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Filter registry initialisation failed", exc_info=True)
            return FilterRegistry()

    def _build_context(
        self,
        filter_element: etree._Element,
        extra: Any | None,
    ) -> FilterContext:
        options: dict[str, Any] = {}
        if isinstance(extra, dict):
            options.update(extra)
        services = self._services
        if "source_path" not in options and services is not None and hasattr(services, "resolve"):
            source_path = services.resolve("source_path")
            if isinstance(source_path, str) and source_path:
                options["source_path"] = source_path
        viewport = None
        unit_converter = None
        conversion_context = None
        if services is not None:
            if hasattr(services, "resolve"):
                unit_converter = services.resolve("unit_converter")
                conversion_context = services.resolve("conversion_context")
                style_context = services.resolve("style_context")
                if conversion_context is None and style_context is not None:
                    conversion_context = getattr(style_context, "conversion", None)
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
            unit_converter=unit_converter,
            conversion_context=conversion_context,
        )

    def set_strategy(self, strategy: str) -> None:
        """Configure the preferred filter rendering strategy."""

        if not isinstance(strategy, str):
            raise ValueError(f"Unsupported filter strategy '{strategy}'")
        normalized = strategy.strip().lower()
        if normalized not in ALLOWED_STRATEGIES:
            raise ValueError(f"Unsupported filter strategy '{strategy}'")
        self._strategy = normalized

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver used for EMF fallback rendering."""

        self._palette_resolver = resolver
        if self._renderer is not None:
            self._renderer.set_palette_resolver(resolver)

    def _configure_palette_resolver(self, services: ConversionServices) -> None:
        resolver = extract_palette_resolver(services)
        if resolver is not None:
            self.set_palette_resolver(resolver)
        elif self._palette_resolver is not None and self._renderer is not None:
            self._renderer.set_palette_resolver(self._palette_resolver)

    def _resolve_strategy(
        self,
        context: FilterContext,
        descriptor: ResolvedFilter | None,
    ) -> str:
        policy_options = context.policy
        policy_strategy = policy_options.get("strategy")
        if isinstance(policy_strategy, str):
            normalized = policy_strategy.strip().lower()
            if normalized in ALLOWED_STRATEGIES:
                if normalized == "native-if-neutral":
                    if self._planner and self._planner.descriptor_is_neutral(descriptor):
                        return "native"
                    return "emf"
                return normalized

        if self._strategy != "auto":
            if self._strategy == "native-if-neutral":
                if self._planner and self._planner.descriptor_is_neutral(descriptor):
                    return "native"
                return "emf"
            return self._strategy

        return self._strategy

    def _attach_emf_metadata(
        self,
        existing_results: list[FilterEffectResult],
        emf_results: list[FilterEffectResult],
    ) -> list[FilterEffectResult]:
        if self._renderer is None:
            return existing_results
        return self._renderer.attach_emf_metadata(existing_results, emf_results)

    def _attach_raster_metadata(
        self,
        existing_results: list[FilterEffectResult],
        raster_results: list[FilterEffectResult],
    ) -> None:
        if self._renderer is not None:
            self._renderer.attach_raster_metadata(existing_results, raster_results)

    def _descriptor_fallback(
        self,
        descriptor: Mapping[str, Any] | None,
        bounds: Mapping[str, Any] | None,
        filter_id: str,
        *,
        strategy_hint: str,
    ) -> list[FilterEffectResult] | None:
        if self._renderer is None:
            return None
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
        if self._planner is None:
            return None, None
        return self._planner.descriptor_payload(context, descriptor)

    def _ensure_pipeline(self) -> bool:
        if self._renderer is not None and self._planner is not None:
            return True
        planner_cls, renderer_cls, error = _load_pipeline()
        if planner_cls is None or renderer_cls is None:
            self._runtime_capability = "disabled"
            self._pipeline_error = error
            if not self._pipeline_warned:
                self._logger.warning(
                    "Filter pipeline unavailable (%s). Install svg2ooxml[render] for full filter support.",
                    _pipeline_warning(error),
                )
                self._pipeline_warned = True
            return False
        if error is not None and not self._pipeline_warned:
            self._logger.warning(
                "Full filter pipeline unavailable (%s). Falling back to lightweight filter pipeline.",
                _pipeline_warning(error),
            )
            self._pipeline_warned = True
        self._runtime_capability = "lightweight" if error is not None else "full"
        self._pipeline_error = None
        self._planner = planner_cls(logger=self._logger)
        self._renderer = renderer_cls(
            registry=self._registry,
            planner=self._planner,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
            raster_adapter=self._raster_adapter,
        )
        return True

    def _disabled_effects(self, filter_ref: str) -> list[FilterEffectResult]:
        metadata = {
            "filter_id": filter_ref,
            "disabled": True,
            "reason": _pipeline_warning(self._pipeline_error),
            "runtime_capability": self.runtime_capability,
        }
        return [
            FilterEffectResult(
                effect=None,
                strategy="emf",
                fallback="emf",
                metadata=metadata,
            )
        ]


__all__ = ["ALLOWED_STRATEGIES", "FilterServicePipelineMixin"]
