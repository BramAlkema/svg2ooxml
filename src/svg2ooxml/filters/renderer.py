"""Render filter effects via native, vector, raster, and resvg pipelines."""

from __future__ import annotations

import copy
import logging
import struct
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

import numpy as np
from lxml import etree

from svg2ooxml.drawingml.emf_adapter import PaletteResolver
from svg2ooxml.drawingml.filter_renderer import (
    FilterRenderer as DrawingMLFilterRenderer,
)
from svg2ooxml.drawingml.raster_adapter import RasterAdapter, _surface_to_png
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.primitives.blend import BlendFilter
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter
from svg2ooxml.filters.primitives.composite import CompositeFilter
from svg2ooxml.filters.primitives.convolve_matrix import ConvolveMatrixFilter
from svg2ooxml.filters.primitives.flood import FloodFilter
from svg2ooxml.filters.primitives.gaussian_blur import GaussianBlurFilter
from svg2ooxml.filters.primitives.lighting import (
    DiffuseLightingFilter,
    SpecularLightingFilter,
)
from svg2ooxml.filters.primitives.merge import MergeFilter
from svg2ooxml.filters.primitives.morphology import MorphologyFilter
from svg2ooxml.filters.primitives.offset import OffsetFilter
from svg2ooxml.filters.primitives.tile import TileFilter
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.io.emf.blob import EMU_PER_INCH, EMFBlob
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.render.filters import FilterPlan, UnsupportedPrimitiveError, apply_filter
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.render.surface import Surface
from svg2ooxml.services.filter_types import FilterEffectResult

_PROMOTION_FILTER_FACTORIES = {
    "feflood": FloodFilter,
    "feblend": BlendFilter,
    "fecomposite": CompositeFilter,
    "fecolormatrix": ColorMatrixFilter,
    "femorphology": MorphologyFilter,
    "fetile": TileFilter,
    "femerge": MergeFilter,
    "feoffset": OffsetFilter,
    "fecomponenttransfer": ComponentTransferFilter,
    "feconvolvematrix": ConvolveMatrixFilter,
    "fediffuselighting": DiffuseLightingFilter,
    "fespecularlighting": SpecularLightingFilter,
    "fegaussianblur": GaussianBlurFilter,
}


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
        )
        clone._resvg_counter = self._resvg_counter
        return clone

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
            strategy = effect.strategy if effect.strategy in {"vector", "emf"} else "vector"
            fallback = effect.fallback

            if fallback == "emf":
                assets = meta.setdefault("fallback_assets", [])
                if isinstance(assets, list) and not any(
                    isinstance(asset, dict) and asset.get("type") == "emf" for asset in assets
                ):
                    asset = None
                    if hasattr(self._drawingml_renderer, "_ensure_emf_asset") and source is not None:
                        try:
                            asset = self._drawingml_renderer._ensure_emf_asset(meta, source)  # type: ignore[attr-defined]
                        except Exception:  # pragma: no cover - defensive
                            asset = None
                    if not any(
                        isinstance(asset, dict) and asset.get("type") == "emf" for asset in assets
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
        plan = self._planner.build_resvg_plan(descriptor)
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
            self._logger.debug("Failed to compute resvg viewport for %s", filter_id, exc_info=True)
            _trace("resvg_viewport_failed", error=str(exc))
            return None

        policy_overrides = self._planner.policy_primitive_overrides(filter_context)

        policy_block_reason = self._planner.resvg_policy_block(plan, viewport, policy_overrides)
        if policy_block_reason is not None:
            _trace("resvg_policy_blocked", reason=policy_block_reason)
            return None

        promotion = self._promote_resvg_plan(
            plan,
            filter_element,
            filter_context,
            viewport,
            policy_overrides,
            descriptor,
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

        if self._planner.plan_has_turbulence(plan):
            try:
                emf_effect = self._turbulence_emf_effect(result_surface, viewport, plan, filter_id)
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

    @staticmethod
    def attach_emf_metadata(
        existing_results: list[FilterEffectResult],
        emf_results: list[FilterEffectResult],
    ) -> list[FilterEffectResult]:
        if not existing_results or not emf_results:
            return existing_results

        vector_indexed = [
            (index, result)
            for index, result in enumerate(existing_results)
            if result.fallback and result.fallback.lower() == "emf"
        ]
        if not vector_indexed:
            return existing_results

        base = list(existing_results)
        last_idx, last_result = vector_indexed[-1]
        metadata = dict(last_result.metadata or {})
        original_assets = list(metadata.get("fallback_assets") or [])
        assets = list(original_assets)
        descriptor_result = isinstance(last_result.metadata, dict) and last_result.metadata.get("strategy_source") == "resvg_descriptor"
        best_assets: list[dict[str, Any]] | None = None
        for emf_result in emf_results:
            emf_meta = emf_result.metadata if isinstance(emf_result.metadata, dict) else {}
            emf_assets = emf_meta.get("fallback_assets")
            if not isinstance(emf_assets, list):
                continue
            candidates = [
                asset
                for asset in emf_assets
                if isinstance(asset, dict) and asset.get("type") == "emf"
            ]
            if not candidates:
                continue
            preferred = [asset for asset in candidates if not asset.get("placeholder")]
            if preferred:
                best_assets = preferred
            else:
                best_assets = candidates

        descriptor_info = metadata.get("descriptor") if isinstance(metadata.get("descriptor"), dict) else {}
        primitive_count = None
        primitive_tags: set[str] = set()
        if isinstance(descriptor_info, dict):
            primitive_count = descriptor_info.get("primitive_count")
            tags = descriptor_info.get("primitive_tags")
            if isinstance(tags, (list, tuple, set)):
                primitive_tags = {str(tag).strip().lower() for tag in tags if tag}

        multi_stage_descriptor = descriptor_result and primitive_count and primitive_count > 1
        has_composite = descriptor_result and any("fecomposite" in tag for tag in primitive_tags)

        if descriptor_result:
            if multi_stage_descriptor or has_composite:
                raster_assets = [
                    asset for asset in original_assets if isinstance(asset, dict) and asset.get("type") == "raster"
                ]
                if raster_assets:
                    assets = raster_assets
                elif best_assets:
                    assets = best_assets
                else:
                    assets = original_assets
            else:
                assets = best_assets or original_assets
        else:
            assets = best_assets or original_assets
        metadata["fallback_assets"] = assets
        if assets:
            sample = next((asset for asset in reversed(assets) if isinstance(asset, dict)), None)
            if sample:
                sample_meta = sample.get("metadata")
                if isinstance(sample_meta, dict) and sample_meta.get("filter_type"):
                    metadata["filter_type"] = sample_meta.get("filter_type")

        if assets:
            base[last_idx] = replace(
                last_result,
                metadata=metadata,
                fallback="emf",
            )
        else:
            base[last_idx] = replace(
                last_result,
                metadata=metadata,
                fallback=last_result.fallback,
            )

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
        assets = metadata.setdefault("fallback_assets", [])
        had_emf = any(isinstance(asset, dict) and asset.get("type") == "emf" for asset in assets)
        for raster in raster_results:
            raster_meta = raster.metadata if isinstance(raster.metadata, dict) else {}
            if "renderer" in raster_meta:
                metadata.setdefault("renderer", raster_meta.get("renderer"))
            for key in ("width_px", "height_px", "filter_units", "primitive_units", "descriptor"):
                if key in raster_meta and key not in metadata:
                    metadata[key] = raster_meta[key]
            for asset in raster_meta.get("fallback_assets", []) or []:
                assets.append(asset)
        if (
            metadata.get("strategy_source") == "resvg_descriptor"
            and isinstance(assets, list)
            and not had_emf
        ):
            assets.sort(key=lambda asset: 0 if isinstance(asset, dict) and asset.get("type") == "raster" else 1)
        existing_results[-1] = FilterEffectResult(
            effect=target.effect,
            strategy=target.strategy,
            metadata=metadata,
            fallback=target.fallback,
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
        if not plan.primitives:
            return None

        # Check global promotion policy
        policy = context.options.get("policy") if isinstance(context.options, dict) else None
        if isinstance(policy, Mapping) and policy.get("allow_promotion") is False:
            if trace is not None:
                trace("resvg_promotion_policy_blocked", reason="global_allow_promotion=false")
            return None

        matched_elements = self._match_plan_elements(filter_element, plan)
        if matched_elements is None:
            return None

        pipeline_state: dict[str, FilterResult] = {}
        if isinstance(context.pipeline_state, dict):
            pipeline_state.update(context.pipeline_state)
        original_pipeline = context.pipeline_state
        context.pipeline_state = pipeline_state

        lighting_candidates: list[str] = []
        lighting_primitives: list[str] = []
        try:
            stage_results: list[FilterResult] = []
            no_op_primitives: list[str] = []
            for primitive_plan, element in zip(plan.primitives, matched_elements, strict=True):
                tag = primitive_plan.tag.lower()
                entry_override = (overrides or {}).get(tag)
                promoter = self._promotion_filter(tag)
                if promoter is None:
                    if trace is not None:
                        if tag in {"fediffuselighting", "fespecularlighting"}:
                            trace(
                                "resvg_lighting_candidate",
                                primitive=tag,
                                plan_extra=self._planner.serialise_plan_extra(primitive_plan.extra)
                                if primitive_plan.extra
                                else {},
                            )
                        else:
                            trace(
                                "resvg_promotion_missing_handler",
                                primitive=tag,
                            )
                    if tag in {"fediffuselighting", "fespecularlighting"}:
                        lighting_candidates.append(tag)
                    return None

                promoted_result = promoter.apply(copy.deepcopy(element), context)
                if trace is not None and tag in {"fediffuselighting", "fespecularlighting"}:
                    trace(
                        "resvg_lighting_promoted",
                        primitive=tag,
                        plan_extra=self._planner.serialise_plan_extra(primitive_plan.extra)
                        if primitive_plan.extra
                        else {},
                    )
                    lighting_primitives.append(tag)
                elif tag in {"fediffuselighting", "fespecularlighting"}:
                    lighting_primitives.append(tag)
                is_no_op = self._is_neutral_promotion(tag, element, promoted_result)
                if is_no_op:
                    no_op_primitives.append(tag)
                    if trace is not None:
                        trace("resvg_promotion_noop", primitive=tag)
                    if primitive_plan.result_name:
                        input_name = next((name for name in primitive_plan.inputs if name), None)
                        source = pipeline_state.get(input_name) if input_name else None
                        if source is None and input_name in {"SourceGraphic", "SourceAlpha"}:
                            source = pipeline_state.get(input_name)
                        pipeline_state[primitive_plan.result_name] = source or promoted_result
                    continue

                if entry_override and entry_override.get("allow_promotion") is False:
                    if trace is not None:
                        trace(
                            "resvg_promotion_policy_blocked",
                            primitive=tag,
                            reason="allow_promotion=false",
                        )
                    return None

                violation = None
                if entry_override:
                    violation = self._planner.promotion_policy_violation(tag, promoted_result, entry_override)
                    if violation is not None and trace is not None:
                        trace(
                            "resvg_promotion_policy_blocked",
                            primitive=tag,
                            **violation,
                        )
                if violation is not None:
                    return None

                if primitive_plan.result_name:
                    pipeline_state[primitive_plan.result_name] = promoted_result
                stage_results.append(promoted_result)

            if not stage_results:
                if no_op_primitives:
                    metadata: dict[str, Any] = {
                        "renderer": "resvg",
                        "resvg_promotion": "native",
                        "promotion_source": "resvg",
                        "promotion_primitives": [primitive.tag for primitive in plan.primitives],
                        "no_op": True,
                        "no_op_primitives": list(no_op_primitives),
                        "descriptor": self._planner.serialize_descriptor(descriptor),
                        "primitives": [primitive.tag for primitive in descriptor.primitives],
                        "filter_units": descriptor.filter_units,
                        "primitive_units": descriptor.primitive_units,
                    }
                    if descriptor.filter_id:
                        metadata["filter_id"] = descriptor.filter_id
                    self._inject_promotion_metadata(metadata, plan, viewport)
                    effect = CustomEffect(drawingml="")
                    return FilterEffectResult(
                        effect=effect,
                        strategy="native",
                        metadata=metadata,
                        fallback=None,
                    )
                return None

            final_result = stage_results[-1]
            if final_result.fallback not in {"emf", "vector", None}:
                return None
            if final_result.fallback is None:
                drawingml_payload = final_result.drawingml or ""
                if not drawingml_payload.strip():
                    return None

            rendered = self._drawingml_renderer.render([final_result], context=context)
            if not rendered:
                return None

            effect = rendered[0]
            metadata = dict(effect.metadata or {})
            assets = metadata.get("fallback_assets")
            if isinstance(assets, list):
                metadata["fallback_assets"] = list(assets)
            self._inject_promotion_metadata(metadata, plan, viewport)
            metadata.setdefault("renderer", "resvg")
            metadata.setdefault("resvg_promotion", final_result.fallback or "vector")
            metadata.setdefault("promotion_source", "resvg")
            metadata.setdefault("promotion_primitives", [primitive.tag for primitive in plan.primitives])
            metadata.setdefault("descriptor", self._planner.serialize_descriptor(descriptor))
            metadata.setdefault("primitives", [primitive.tag for primitive in descriptor.primitives])
            if lighting_candidates:
                metadata.setdefault("resvg_lighting_candidate", lighting_candidates)
            if lighting_primitives:
                metadata.setdefault("lighting_primitives", lighting_primitives)
            if descriptor.filter_id:
                metadata.setdefault("filter_id", descriptor.filter_id)
            metadata.setdefault("filter_units", descriptor.filter_units)
            metadata.setdefault("primitive_units", descriptor.primitive_units)
            return FilterEffectResult(
                effect=effect.effect,
                strategy=effect.strategy,
                metadata=metadata,
                fallback=effect.fallback,
            )
        finally:
            context.pipeline_state = original_pipeline

    @staticmethod
    def _is_neutral_promotion(tag: str, element: etree._Element, result: FilterResult) -> bool:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        if metadata.get("no_op"):
            return True

        if tag == "fegaussianblur":
            std_x = metadata.get("std_deviation_x")
            std_y = metadata.get("std_deviation_y")
            try:
                std_x_val = float(std_x) if std_x is not None else 0.0
                std_y_val = float(std_y) if std_y is not None else 0.0
            except (TypeError, ValueError):
                std_x_val = 0.0
                std_y_val = 0.0
            return abs(std_x_val) <= 1e-6 and abs(std_y_val) <= 1e-6

        if tag == "feoffset":
            dx = metadata.get("dx")
            dy = metadata.get("dy")
            try:
                dx_val = float(dx) if dx is not None else 0.0
                dy_val = float(dy) if dy is not None else 0.0
            except (TypeError, ValueError):
                dx_val = 0.0
                dy_val = 0.0
            return abs(dx_val) <= 1e-6 and abs(dy_val) <= 1e-6

        if tag == "fecolormatrix":
            if metadata.get("reason") == "identity_matrix":
                return True
            matrix_type = str(metadata.get("matrix_type") or "matrix").strip().lower()
            if matrix_type != "matrix":
                return False
            values = metadata.get("values")
            if not values:
                return True
            try:
                return FilterRenderer._is_identity_matrix([float(v) for v in values])
            except (TypeError, ValueError):
                return False

        if tag == "fegaussianblur" and element is not None:
            std_attr = element.get("stdDeviation")
            if std_attr:
                parts = [parse_number(token) for token in std_attr.replace(",", " ").split()]
                if parts and all(abs(value) <= 1e-6 for value in parts[:2]):
                    return True

        return False

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

    @staticmethod
    def _promotion_filter(tag: str):
        factory = _PROMOTION_FILTER_FACTORIES.get(tag)
        if factory is None:
            return None
        return factory()

    @staticmethod
    def _match_plan_elements(
        filter_element: etree._Element,
        plan: FilterPlan,
    ) -> list[etree._Element] | None:
        buckets: dict[str, list[etree._Element]] = defaultdict(list)
        results: dict[str, etree._Element] = {}
        for child in filter_element:
            local = child.tag.split("}", 1)[-1].lower() if "}" in child.tag else child.tag.lower()
            buckets[local].append(child)
            result_name = child.get("result")
            if result_name:
                token = result_name.strip()
                if token and token not in results:
                    results[token] = child

        ordered: list[etree._Element] = []
        used: set[etree._Element] = set()
        for primitive in plan.primitives:
            local = primitive.tag.lower()
            candidate: etree._Element | None = None
            if primitive.result_name:
                candidate = results.get(primitive.result_name)
                if candidate in used:
                    candidate = None
            if candidate is None:
                bucket = buckets.get(local)
                while bucket:
                    contender = bucket.pop(0)
                    if contender not in used:
                        candidate = contender
                        break
            if candidate is None:
                return None
            ordered.append(candidate)
            used.add(candidate)
        return ordered

    def _inject_promotion_metadata(
        self,
        metadata: dict[str, Any],
        plan: FilterPlan,
        viewport: Viewport,
    ) -> None:
        metadata.setdefault("width_px", viewport.width)
        metadata.setdefault("height_px", viewport.height)
        metadata.setdefault("promotion_plan_length", len(plan.primitives))
        plan_summary = []
        for primitive_plan in plan.primitives:
            entry = {
                "tag": primitive_plan.tag,
                "inputs": list(primitive_plan.inputs),
                "result": primitive_plan.result_name,
            }
            if primitive_plan.extra:
                entry["metadata"] = self._planner.serialise_plan_extra(primitive_plan.extra)
            plan_summary.append(entry)
        metadata.setdefault("plan_primitives", plan_summary)

    def _surface_to_bmp(self, surface: Surface) -> bytes:
        data = np.clip(surface.data, 0.0, 1.0)
        rgb = data[..., :3]
        alpha = data[..., 3:4]
        safe_alpha = np.where(alpha > 1e-6, alpha, 1.0)
        unpremult = np.where(alpha > 1e-6, rgb / safe_alpha, 0.0)
        unpremult = np.clip(unpremult, 0.0, 1.0)
        bgr = (unpremult[..., ::-1] * 255.0 + 0.5).astype(np.uint8)
        height, width = bgr.shape[:2]
        row_stride = (width * 3 + 3) & ~3
        padding = row_stride - width * 3
        pad_bytes = b"\x00" * padding
        rows = []
        for y in range(height - 1, -1, -1):
            rows.append(bgr[y].tobytes() + pad_bytes)
        pixel_data = b"".join(rows)
        header_size = 40
        dib_header = struct.pack(
            "<IIIHHIIIIII",
            header_size,
            width,
            height,
            1,
            24,
            0,
            len(pixel_data),
            int(96 / 0.0254),
            int(96 / 0.0254),
            0,
            0,
        )
        file_header = b"BM" + struct.pack(
            "<IHHI",
            14 + len(dib_header) + len(pixel_data),
            0,
            0,
            14 + len(dib_header),
        )
        return file_header + dib_header + pixel_data

    def _turbulence_emf_effect(
        self,
        surface: Surface,
        viewport: Viewport,
        plan: FilterPlan,
        filter_id: str,
    ) -> FilterEffectResult:
        width_px = max(1, int(round(viewport.width)))
        height_px = max(1, int(round(viewport.height)))
        bmp_bytes = self._surface_to_bmp(surface)
        width_emu = max(1, int(round(width_px * EMU_PER_INCH / 96)))
        height_emu = max(1, int(round(height_px * EMU_PER_INCH / 96)))
        blob = EMFBlob(width_emu=width_emu, height_emu=height_emu)
        blob.draw_bitmap(
            0,
            0,
            width_emu,
            height_emu,
            0,
            0,
            width_px,
            height_px,
            bmp_bytes,
        )
        emf_bytes = blob.finalize()
        metadata: dict[str, Any] = {
            "renderer": "resvg",
            "resvg_promotion": "emf",
            "promotion_source": "resvg",
            "promotion_primitives": [primitive.tag for primitive in plan.primitives],
            "fallback_assets": [
                {
                    "type": "emf",
                    "format": "emf",
                    "data": emf_bytes,
                    "width_px": width_px,
                    "height_px": height_px,
                }
            ],
            "turbulence_emf": True,
            "filter_id": filter_id,
        }
        effect = CustomEffect(drawingml="")
        return FilterEffectResult(effect=effect, strategy="vector", metadata=metadata, fallback="emf")

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


__all__ = ["FilterRenderer"]
