"""Backward-compatible private delegates for ``FilterRenderer``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
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
from svg2ooxml.filters.strategies.native import render_editable_stack
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
from svg2ooxml.filters.strategies.resvg_bridge import surface_to_bmp as _surface_to_bmp
from svg2ooxml.render.filters import FilterPlan
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.services.filter_types import FilterEffectResult


class FilterRendererCompatibilityMixin:
    """Private compatibility surface retained after strategy extraction."""

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
