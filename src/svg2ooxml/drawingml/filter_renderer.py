"""Filter rendering orchestrator for svg2ooxml."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from svg2ooxml.drawingml.emf_adapter import EMFAdapter
from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.drawingml.filter_renderer_assets import FilterRendererAssetMixin
from svg2ooxml.drawingml.filter_renderer_hooks import (
    ATTR_PATTERN,
    HOOK_PATTERN,
    FilterRendererHookMixin,
)
from svg2ooxml.drawingml.filter_renderer_policy import FilterRendererPolicyMixin
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import is_effect_container
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult


class FilterRenderer(
    FilterRendererHookMixin,
    FilterRendererAssetMixin,
    FilterRendererPolicyMixin,
):
    """Bridge between FilterRegistry outputs and IR effects."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        palette_resolver: PaletteResolver | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._emf_adapter = EMFAdapter(palette_resolver=palette_resolver)
        self._raster_adapter = RasterAdapter()
        self._reuse_counter = 0

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver used for EMF fallback rendering."""

        self._emf_adapter.set_palette_resolver(resolver)

    def render(
        self,
        filter_results: Iterable[FilterResult],
        *,
        context: FilterContext | None = None,
    ) -> list[FilterEffectResult]:
        outputs: list[FilterEffectResult] = []
        policy = self._policy_from_context(context)
        for result in filter_results:
            if not isinstance(result, FilterResult) or not result.is_success():
                continue

            drawingml = result.drawingml or ""
            metadata = self._metadata_copy(result.metadata)
            drawingml = self._materialize_hook_fragment(drawingml, result, context)

            fragment = drawingml.strip()
            if fragment and not fragment.startswith("<!--") and not is_effect_container(fragment):
                drawingml = f"<a:effectLst>{fragment}</a:effectLst>"

            if not drawingml and result.fallback == "emf":
                drawingml = self._placeholder_emf(metadata, result, policy=policy)
                strategy = "vector"
            elif not drawingml and result.fallback in {"bitmap", "raster"}:
                drawingml = self._placeholder_raster(metadata, result, policy=policy)
                strategy = "raster"
            else:
                strategy = self._strategy_from_policy(result, policy)

            outputs.append(
                FilterEffectResult(
                    effect=CustomEffect(drawingml=drawingml),
                    strategy=strategy,
                    metadata=metadata,
                    fallback=result.fallback,
                )
            )
        return outputs

    def _materialize_hook_fragment(
        self,
        drawingml: str,
        result: FilterResult,
        context: FilterContext | None,
    ) -> str:
        hook_name, attrs, remainder = self._extract_hook(drawingml)
        if hook_name:
            builder = self._hook_builders().get(hook_name)
            if builder:
                try:
                    return builder(hook_name, attrs, remainder, result, context)
                except Exception:  # pragma: no cover - defensive logging
                    self._logger.debug("Hook builder %s failed", hook_name, exc_info=True)
                    return remainder or ""
            return remainder or ""
        stripped = drawingml.strip()
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            return ""
        return drawingml


__all__ = ["FilterRenderer", "HOOK_PATTERN", "ATTR_PATTERN"]
