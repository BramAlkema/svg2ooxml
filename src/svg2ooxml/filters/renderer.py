"""Render filter effects via native, vector, raster, and resvg pipelines."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import (
    FilterRenderer as DrawingMLFilterRenderer,
)
from svg2ooxml.drawingml.raster_adapter import RasterAdapter, _surface_to_png
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.palette import (
    attach_emf_metadata as _attach_emf_metadata,
)
from svg2ooxml.filters.palette import (
    attach_raster_metadata as _attach_raster_metadata,
)
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.filters.strategies.native import (
    aggregate_blip_color_transforms as _aggregate_blip_color_transforms,
)
from svg2ooxml.filters.strategies.native import (
    build_blip_color_transform_stack_effect as _build_blip_color_transform_stack_effect,
)
from svg2ooxml.filters.strategies.native import (
    build_component_transfer_alpha_stack_effect as _build_component_transfer_alpha_stack_effect,
)
from svg2ooxml.filters.strategies.native import (
    build_flood_blur_merge_effect as _build_flood_blur_merge_effect,
)
from svg2ooxml.filters.strategies.native import (
    build_lighting_composite_effect as _build_lighting_composite_effect,
)
from svg2ooxml.filters.strategies.native import (
    build_shadow_stack_effect as _build_shadow_stack_effect,
)
from svg2ooxml.filters.strategies.native import (
    coerce_non_negative_float as _coerce_non_negative_float,
)
from svg2ooxml.filters.strategies.native import (
    component_transfer_alpha_scale as _component_transfer_alpha_scale,
)
from svg2ooxml.filters.strategies.native import (
    is_additive_composite as _is_additive_composite,
)
from svg2ooxml.filters.strategies.native import (
    match_color_transform_stack as _match_color_transform_stack,
)
from svg2ooxml.filters.strategies.native import (
    match_flood_blur_merge_stack as _match_flood_blur_merge_stack,
)
from svg2ooxml.filters.strategies.native import (
    match_lighting_composite_stack as _match_lighting_composite_stack,
)
from svg2ooxml.filters.strategies.native import (
    match_shadow_stack as _match_shadow_stack,
)
from svg2ooxml.filters.strategies.native import (
    parse_float_attr as _parse_float_attr,
)
from svg2ooxml.filters.strategies.native import (
    primitive_local_name as _primitive_local_name,
)
from svg2ooxml.filters.strategies.native import (
    render_color_transform_stack as _render_color_transform_stack,
)
from svg2ooxml.filters.strategies.native import (
    render_editable_stack,
)
from svg2ooxml.filters.strategies.raster_fallback import rasterize_filter
from svg2ooxml.filters.strategies.resvg_bridge import (
    inject_promotion_metadata as _inject_promotion_metadata,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    is_identity_matrix as _is_identity_matrix,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    is_neutral_promotion as _is_neutral_promotion,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    match_plan_elements as _match_plan_elements,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    promote_resvg_plan,
    seed_source_surface,
    turbulence_emf_effect,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    promotion_filter as _promotion_filter,
)
from svg2ooxml.filters.strategies.resvg_bridge import (
    surface_to_bmp as _surface_to_bmp,
)
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.render.filters import FilterPlan, UnsupportedPrimitiveError, apply_filter
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.services.filter_types import FilterEffectResult


class FilterRenderer:
    """Render filter effects and package metadata for downstream rendering."""

    def __init__(
        self,
        *,
        registry: FilterRegistry,
        planner: FilterPlanner,
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
        self._resvg_counter = 0

    def clone(
        self,
        *,
        registry: FilterRegistry | None = None,
        planner: FilterPlanner | None = None,
    ) -> FilterRenderer:
        clone = FilterRenderer(
            registry=registry or self._registry,
            planner=planner or self._planner,
            logger=self._logger,
            palette_resolver=self._palette_resolver,
            raster_adapter=self._raster_adapter,
        )
        clone._resvg_counter = self._resvg_counter
        return clone

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        self._palette_resolver = resolver
        self._drawingml_renderer.set_palette_resolver(resolver)

    # ------------------------------------------------------------------
    # Public render entry-points
    # ------------------------------------------------------------------

    def render_native(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        context.pipeline_state = context.pipeline_state or {}
        editable_stack = render_editable_stack(
            element, context, self._drawingml_renderer
        )
        if editable_stack:
            return editable_stack
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
        source_results: list[FilterResult] = []
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
            source_results.append(result)

        rendered = self._drawingml_renderer.render(coerced, context=context)
        adjusted: list[FilterEffectResult] = []
        for index, effect in enumerate(rendered):
            source = source_results[index] if index < len(source_results) else None
            meta = dict(effect.metadata or {})
            strategy = (
                effect.strategy if effect.strategy in {"vector", "emf"} else "vector"
            )
            fallback = effect.fallback

            if fallback == "emf":
                assets = meta.setdefault("fallback_assets", [])
                if isinstance(assets, list) and not any(
                    isinstance(asset, dict) and asset.get("type") == "emf"
                    for asset in assets
                ):
                    asset = None
                    if (
                        hasattr(self._drawingml_renderer, "_ensure_emf_asset")
                        and source is not None
                    ):
                        try:
                            asset = self._drawingml_renderer._ensure_emf_asset(meta, source)  # type: ignore[attr-defined]
                        except Exception:  # pragma: no cover - defensive
                            asset = None
                    if not any(
                        isinstance(asset, dict) and asset.get("type") == "emf"
                        for asset in assets
                    ):
                        if not asset:
                            if hasattr(self._drawingml_renderer, "_allocate_reuse_id"):
                                placeholder_id = self._drawingml_renderer._allocate_reuse_id()  # type: ignore[attr-defined]
                            else:
                                placeholder_id = f"rIdEmfPlaceholder{len(assets) + 1}"
                            assets.append(
                                {
                                    "type": "emf",
                                    "relationship_id": placeholder_id,
                                    "placeholder": True,
                                }
                            )
                fallback = "emf"

            adjusted.append(
                replace(
                    effect,
                    strategy=strategy,
                    fallback=fallback,
                    metadata=meta,
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
        result = rasterize_filter(
            element,
            context,
            filter_id,
            raster_adapter=self._raster_adapter,
            logger=self._logger,
        )
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

    def render_resvg_filter(
        self,
        descriptor: ResolvedFilter,
        filter_element: etree._Element,
        filter_context: FilterContext,
        filter_id: str,
        *,
        trace: Callable[..., None] | None = None,
    ) -> FilterEffectResult | None:
        options_map = getattr(filter_context, "options", {})

        def _trace(action: str, **meta: Any) -> None:
            if trace is not None:
                trace(action, **meta)

        _trace("resvg_attempt")
        plan = self._planner.build_resvg_plan(
            descriptor,
            options=options_map if isinstance(options_map, Mapping) else None,
        )
        if plan is None:
            _trace("resvg_plan_unsupported")
            return None

        plan_summary = self._planner.plan_summary(plan)
        _trace(
            "resvg_plan_characterised",
            primitive_count=len(plan.primitives),
            primitive_tags=[primitive.tag for primitive in plan.primitives],
            plan_primitives=plan_summary,
        )

        try:
            bounds = self._planner.resvg_bounds(options_map, descriptor)
            viewport = self._planner.resvg_viewport(bounds)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug(
                "Failed to compute resvg viewport for %s", filter_id, exc_info=True
            )
            _trace("resvg_viewport_failed", error=str(exc))
            return None

        policy_overrides = self._planner.policy_primitive_overrides(filter_context)

        policy_block_reason = self._planner.resvg_policy_block(
            plan, viewport, policy_overrides
        )
        if policy_block_reason is not None:
            _trace("resvg_policy_blocked", reason=policy_block_reason)
            return None

        promotion = promote_resvg_plan(
            plan,
            filter_element,
            filter_context,
            viewport,
            policy_overrides,
            descriptor,
            planner=self._planner,
            drawingml_renderer=self._drawingml_renderer,
            trace=_trace,
        )
        if promotion is not None:
            _trace(
                "resvg_promoted_emf",
                primitive=plan.primitives[0].tag,
                width_px=viewport.width,
                height_px=viewport.height,
                primitive_count=len(plan.primitives),
                primitives=[primitive.tag for primitive in plan.primitives],
            )
            return promotion

        source_surface = None
        try:
            source_surface = self._raster_adapter.render_source_surface(
                width_px=viewport.width,
                height_px=viewport.height,
                context=filter_context,
            )
        except Exception:  # pragma: no cover - defensive fallback
            source_surface = None
        if source_surface is None:
            source_surface = seed_source_surface(viewport.width, viewport.height)
        try:
            result_surface = apply_filter(source_surface, plan, bounds, viewport)
        except UnsupportedPrimitiveError as exc:
            _trace("resvg_unsupported_primitive", primitive=str(exc))
            return None
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug(
                "Resvg filter application failed for %s", filter_id, exc_info=True
            )
            _trace("resvg_execution_failed", error=str(exc))
            return None

        if self._planner.plan_has_turbulence(plan):
            try:
                emf_effect = turbulence_emf_effect(
                    result_surface, viewport, plan, filter_id
                )
            except Exception:  # pragma: no cover - fall back to raster
                _trace("resvg_turbulence_emf_failed")
            else:
                _trace(
                    "resvg_turbulence_emf",
                    primitive_count=len(plan.primitives),
                    width_px=viewport.width,
                    height_px=viewport.height,
                )
                return emf_effect

        png_bytes = _surface_to_png(result_surface)
        self._resvg_counter += 1
        relationship_id = f"rIdResvgFilter{self._resvg_counter}"

        descriptor_payload = self._planner.serialize_descriptor(descriptor)
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
            "plan_primitives": plan_summary,
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

    # ------------------------------------------------------------------
    # EMF / raster metadata attachment (static delegates)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Backward-compatible private method delegates
    # ------------------------------------------------------------------

    def _render_editable_stack(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        return render_editable_stack(element, context, self._drawingml_renderer)

    def _render_color_transform_stack(
        self,
        element: etree._Element,
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        return _render_color_transform_stack(element, context, self._drawingml_renderer)

    def _build_flood_blur_merge_effect(
        self,
        context: FilterContext,
        flood_primitive: etree._Element,
        blur_primitive: etree._Element,
        merge_inputs: list[str],
    ) -> FilterEffectResult | None:
        return _build_flood_blur_merge_effect(
            context, flood_primitive, blur_primitive, merge_inputs
        )

    def _build_shadow_stack_effect(
        self,
        context: FilterContext,
        offset_primitive: etree._Element,
        blur_primitive: etree._Element,
        flood_primitive: etree._Element,
        merge_inputs: list[str],
    ) -> FilterEffectResult:
        return _build_shadow_stack_effect(
            context, offset_primitive, blur_primitive, flood_primitive, merge_inputs
        )

    def _match_flood_blur_merge_stack(
        self,
        element: etree._Element,
    ) -> tuple[etree._Element, etree._Element, list[str]] | None:
        return _match_flood_blur_merge_stack(element)

    def _match_shadow_stack(
        self,
        element: etree._Element,
    ) -> tuple[etree._Element, etree._Element, etree._Element, list[str]] | None:
        return _match_shadow_stack(element)

    def _match_lighting_composite_stack(
        self,
        element: etree._Element,
    ) -> tuple[etree._Element, etree._Element] | None:
        return _match_lighting_composite_stack(element)

    def _build_lighting_composite_effect(
        self,
        context: FilterContext,
        lighting_primitive: etree._Element,
        composite_primitive: etree._Element,
    ) -> FilterEffectResult | None:
        return _build_lighting_composite_effect(
            context, lighting_primitive, composite_primitive
        )

    def _build_component_transfer_alpha_stack_effect(
        self,
        steps: list[dict[str, Any]],
    ) -> FilterEffectResult:
        return _build_component_transfer_alpha_stack_effect(steps)

    def _build_blip_color_transform_stack_effect(
        self,
        steps: list[dict[str, Any]],
        context: FilterContext,
    ) -> list[FilterEffectResult]:
        return _build_blip_color_transform_stack_effect(
            steps, context, self._drawingml_renderer
        )

    def _match_color_transform_stack(
        self,
        element: etree._Element,
    ) -> list[etree._Element] | None:
        return _match_color_transform_stack(element)

    @staticmethod
    def _primitive_local_name(primitive: etree._Element) -> str:
        return _primitive_local_name(primitive)

    @staticmethod
    def _component_transfer_alpha_scale(
        transfer_filter: Any,
        functions: list[Any],
    ) -> float | None:
        return _component_transfer_alpha_scale(transfer_filter, functions)

    @staticmethod
    def _aggregate_blip_color_transforms(
        transforms: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return _aggregate_blip_color_transforms(transforms)

    @staticmethod
    def _coerce_non_negative_float(value: object) -> float | None:
        return _coerce_non_negative_float(value)

    @staticmethod
    def _parse_float_attr(value: str | None) -> float:
        return _parse_float_attr(value)

    @staticmethod
    def _is_additive_composite(k1: float, k2: float, k3: float, k4: float) -> bool:
        return _is_additive_composite(k1, k2, k3, k4)

    def _seed_source_surface(self, width: int, height: int):  # noqa: ANN201
        return seed_source_surface(width, height)

    def _promote_resvg_plan(
        self,
        plan: FilterPlan,
        filter_element: etree._Element,
        context: FilterContext,
        viewport: Viewport,
        overrides: dict[str, dict[str, Any]] | None,
        descriptor: ResolvedFilter,
        *,
        trace: Callable[..., None] | None = None,
    ) -> FilterEffectResult | None:
        return promote_resvg_plan(
            plan,
            filter_element,
            context,
            viewport,
            overrides,
            descriptor,
            planner=self._planner,
            drawingml_renderer=self._drawingml_renderer,
            trace=trace,
        )

    @staticmethod
    def _is_neutral_promotion(
        tag: str, element: etree._Element, result: FilterResult
    ) -> bool:
        return _is_neutral_promotion(tag, element, result)

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        return _is_identity_matrix(values)

    @staticmethod
    def _promotion_filter(tag: str):  # noqa: ANN205
        return _promotion_filter(tag)

    @staticmethod
    def _match_plan_elements(
        filter_element: etree._Element,
        plan: FilterPlan,
    ) -> list[etree._Element] | None:
        return _match_plan_elements(filter_element, plan)

    def _inject_promotion_metadata(
        self,
        metadata: dict[str, Any],
        plan: FilterPlan,
        viewport: Viewport,
    ) -> None:
        _inject_promotion_metadata(metadata, plan, viewport, self._planner)

    def _surface_to_bmp(self, surface: Any) -> bytes:
        return _surface_to_bmp(surface)

    def _turbulence_emf_effect(
        self,
        surface: Any,
        viewport: Viewport,
        plan: FilterPlan,
        filter_id: str,
    ) -> FilterEffectResult:
        return turbulence_emf_effect(surface, viewport, plan, filter_id)

    def _rasterize_filter(
        self,
        element: etree._Element,
        context: FilterContext,
        filter_id: str,
    ) -> FilterResult | None:
        return rasterize_filter(
            element,
            context,
            filter_id,
            raster_adapter=self._raster_adapter,
            logger=self._logger,
        )


__all__ = ["FilterRenderer"]
