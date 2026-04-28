"""Filter rendering delegates for :mod:`svg2ooxml.services.filter_service`."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.services.filter_types import FilterEffectResult


class FilterRenderRuntimeMixin:
    """Renderer-facing helpers mixed into ``FilterService``."""

    def _render_native(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        if self._renderer is None:
            return []
        return self._renderer.render_native(element, context)

    def _render_vector(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        if self._renderer is None:
            return []
        return self._renderer.render_vector(element, context)

    def _render_raster(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
        *,
        strategy: str,
    ) -> list[FilterEffectResult]:
        if self._renderer is None:
            return []
        return self._renderer.render_raster(
            element, context, filter_id, strategy=strategy
        )

    def _render_resvg_filter(
        self,
        descriptor: ResolvedFilter,
        filter_element: etree._Element,
        filter_context: FilterContext,
        filter_id: str,
    ) -> FilterEffectResult | None:
        if self._renderer is None:
            return None
        options_map = getattr(filter_context, "options", {})
        tracer = options_map.get("tracer") if isinstance(options_map, dict) else None

        def _trace(action: str, **meta: Any) -> None:
            if tracer is None:
                return
            payload = dict(meta)
            resolved_strategy = (
                options_map.get("resolved_strategy", self._strategy)
                if isinstance(options_map, dict)
                else self._strategy
            )
            payload.setdefault("strategy", resolved_strategy)
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

    def _finalize_results(
        self,
        filter_ref: str,
        results: list[FilterEffectResult],
        context: Any | None,
    ) -> list[FilterEffectResult]:
        capability = self.runtime_capability
        self._trace_runtime_capability(filter_ref, context, capability=capability)
        if not results:
            return results
        annotated: list[FilterEffectResult] = []
        for result in results:
            metadata = dict(result.metadata or {})
            metadata.setdefault("runtime_capability", capability)
            annotated.append(replace(result, metadata=metadata))
        return annotated

    def _trace_runtime_capability(
        self,
        filter_ref: str,
        context: Any | None,
        *,
        capability: str,
    ) -> None:
        tracer = None
        if isinstance(context, FilterContext):
            options = context.options if isinstance(context.options, dict) else {}
            tracer = options.get("tracer") if isinstance(options, dict) else None
            strategy = (
                options.get("resolved_strategy", self._strategy)
                if isinstance(options, dict)
                else self._strategy
            )
        elif isinstance(context, dict):
            tracer = context.get("tracer")
            strategy = self._strategy
        else:
            strategy = self._strategy
        if tracer is None:
            return
        recorder = getattr(tracer, "record_stage_event", None)
        if not callable(recorder):
            return
        recorder(
            stage="filter",
            action="runtime_capability",
            subject=filter_ref,
            metadata={
                "capability": capability,
                "strategy": strategy,
            },
        )


__all__ = ["FilterRenderRuntimeMixin"]
