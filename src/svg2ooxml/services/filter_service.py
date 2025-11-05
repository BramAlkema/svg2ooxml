"""Filter service scaffolding mirroring svg2pptx architecture."""

from __future__ import annotations

import copy
import logging
import math
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Callable, cast

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
from svg2ooxml.filters.primitives.blend import BlendFilter
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter
from svg2ooxml.filters.primitives.composite import CompositeFilter
from svg2ooxml.filters.primitives.convolve_matrix import ConvolveMatrixFilter
from svg2ooxml.filters.primitives.flood import FloodFilter
from svg2ooxml.filters.primitives.gaussian_blur import GaussianBlurFilter
from svg2ooxml.filters.primitives.lighting import DiffuseLightingFilter, SpecularLightingFilter
from svg2ooxml.filters.primitives.merge import MergeFilter
from svg2ooxml.filters.primitives.morphology import MorphologyFilter
from svg2ooxml.filters.primitives.offset import OffsetFilter
from svg2ooxml.filters.primitives.tile import TileFilter
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.io.emf.blob import EMFBlob, EMU_PER_INCH
from svg2ooxml.render.filters import FilterPlan, UnsupportedPrimitiveError, apply_filter, plan_filter
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
        descriptor_results: list[FilterEffectResult] | None = None
        strategy = self._resolve_strategy(filter_context)

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

        rendered = self._renderer.render(coerced, context=context)
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
                    if hasattr(self._renderer, "_ensure_emf_asset") and source is not None:
                        try:
                            asset = self._renderer._ensure_emf_asset(meta, source)  # type: ignore[attr-defined]
                        except Exception:  # pragma: no cover - defensive
                            asset = None
                    if not any(
                        isinstance(asset, dict) and asset.get("type") == "emf" for asset in assets
                    ):
                        if not asset:
                            if hasattr(self._renderer, "_allocate_reuse_id"):
                                placeholder_id = self._renderer._allocate_reuse_id()  # type: ignore[attr-defined]
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
        filter_element: etree._Element,
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

        plan_summary = [
            {
                key: value
                for key, value in {
                    "tag": primitive_plan.tag,
                    "inputs": list(primitive_plan.inputs),
                    "result": primitive_plan.result_name,
                    "metadata": self._serialise_plan_extra(primitive_plan.extra) if primitive_plan.extra else None,
                }.items()
                if value is not None and value != []
            }
            for primitive_plan in plan.primitives
        ]
        _trace(
            "resvg_plan_characterised",
            primitive_count=len(plan.primitives),
            primitive_tags=[primitive.tag for primitive in plan.primitives],
            plan_primitives=plan_summary,
        )

        try:
            bounds = self._resvg_bounds(options_map, descriptor)
            viewport = self._resvg_viewport(bounds)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug("Failed to compute resvg viewport for %s", filter_id, exc_info=True)
            _trace("resvg_viewport_failed", error=str(exc))
            return None

        policy_overrides = self._policy_primitive_overrides(filter_context)

        policy_block_reason = self._resvg_policy_block(plan, viewport, filter_context, policy_overrides)
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

        if self._plan_has_turbulence(plan):
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
            for primitive_plan, element in zip(plan.primitives, matched_elements):
                tag = primitive_plan.tag.lower()
                entry_override = (overrides or {}).get(tag)
                if entry_override and entry_override.get("allow_promotion") is False:
                    if trace is not None:
                        trace(
                            "resvg_promotion_policy_blocked",
                            primitive=tag,
                            reason="allow_promotion=false",
                        )
                    return None

                promoter = self._promotion_filter(tag)
                if promoter is None:
                    if trace is not None:
                        if tag in {"fediffuselighting", "fespecularlighting"}:
                            trace(
                                "resvg_lighting_candidate",
                                primitive=tag,
                                plan_extra=self._serialise_plan_extra(primitive_plan.extra) if primitive_plan.extra else {},
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
                        plan_extra=self._serialise_plan_extra(primitive_plan.extra) if primitive_plan.extra else {},
                    )
                    lighting_primitives.append(tag)
                elif tag in {"fediffuselighting", "fespecularlighting"}:
                    lighting_primitives.append(tag)
                violation = None
                if entry_override:
                    violation = self._promotion_policy_violation(tag, promoted_result, entry_override)
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

            final_result = stage_results[-1]
            if final_result.fallback not in {"emf", "vector", None}:
                return None
            if final_result.fallback is None:
                drawingml_payload = final_result.drawingml or ""
                if not drawingml_payload.strip():
                    return None

            rendered = self._renderer.render([final_result], context=context)
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
            metadata.setdefault("descriptor", self._serialize_descriptor(descriptor))
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

    @staticmethod
    def _promotion_policy_violation(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(policy_entry, Mapping):
            return None
        metadata = result.metadata if isinstance(result.metadata, dict) else {}

        max_coeff = policy_entry.get("max_arithmetic_coeff")
        if (
            tag == "fecomposite"
            and metadata.get("operator") == "arithmetic"
            and isinstance(max_coeff, (int, float))
        ):
            limit = abs(float(max_coeff))
            for key in ("k1", "k2", "k3", "k4"):
                coeff = metadata.get(key)
                if isinstance(coeff, (int, float)) and abs(coeff) > limit:
                    return {
                        "rule": "max_arithmetic_coeff",
                        "limit": limit,
                        "coefficient": key,
                        "observed": float(coeff),
                    }

        if tag == "feoffset":
            max_distance = policy_entry.get("max_offset_distance")
            if isinstance(max_distance, (int, float)):
                dx = metadata.get("dx")
                dy = metadata.get("dy")
                dx_val = float(dx) if isinstance(dx, (int, float)) else 0.0
                dy_val = float(dy) if isinstance(dy, (int, float)) else 0.0
                distance = math.hypot(dx_val, dy_val)
                if distance > float(max_distance):
                    return {
                        "rule": "max_offset_distance",
                        "limit": float(max_distance),
                        "observed": distance,
                        "dx": dx_val,
                        "dy": dy_val,
                    }

        if tag == "femerge":
            max_inputs = policy_entry.get("max_merge_inputs")
            if isinstance(max_inputs, (int, float)):
                inputs = metadata.get("inputs")
                count = len(inputs) if isinstance(inputs, (list, tuple)) else 0
                if count > int(max_inputs):
                    return {
                        "rule": "max_merge_inputs",
                        "limit": int(max_inputs),
                        "observed": count,
                    }

        if tag == "fecomponenttransfer":
            functions = metadata.get("functions")
            if isinstance(functions, list):
                max_functions = policy_entry.get("max_component_functions")
                if isinstance(max_functions, (int, float)) and len(functions) > int(max_functions):
                    return {
                        "rule": "max_component_functions",
                        "limit": int(max_functions),
                        "observed": len(functions),
                    }
                max_table_values = policy_entry.get("max_component_table_values")
                if isinstance(max_table_values, (int, float)):
                    limit = int(max_table_values)
                    for func in functions:
                        params = func.get("params") if isinstance(func, Mapping) else None
                        values = params.get("values") if isinstance(params, Mapping) else None
                        if isinstance(values, list) and len(values) > limit:
                            return {
                                "rule": "max_component_table_values",
                                "limit": limit,
                                "observed": len(values),
                                "channel": func.get("channel"),
                            }

        if tag == "feconvolvematrix":
            max_kernel = policy_entry.get("max_convolve_kernel")
            if isinstance(max_kernel, (int, float)):
                kernel = metadata.get("kernel")
                count = len(kernel) if isinstance(kernel, list) else 0
                if count > int(max_kernel):
                    return {
                        "rule": "max_convolve_kernel",
                        "limit": int(max_kernel),
                        "observed": count,
                    }
            max_order = policy_entry.get("max_convolve_order")
            if isinstance(max_order, (int, float)):
                order = metadata.get("order")
                if isinstance(order, (list, tuple)) and order:
                    span = 1
                    numeric = True
                    for axis in order:
                        if isinstance(axis, (int, float)):
                            span *= int(axis)
                        else:
                            numeric = False
                            break
                    if numeric and span > int(max_order):
                        return {
                            "rule": "max_convolve_order",
                            "limit": int(max_order),
                            "observed": span,
                        }

        return None

    @staticmethod
    def _promotion_policy_allows(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> bool:
        violation = FilterService._promotion_policy_violation(tag, result, policy_entry)
        return violation is None

    @staticmethod
    def _inject_promotion_metadata(metadata: dict[str, Any], plan: FilterPlan, viewport: Viewport) -> None:
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
                entry["metadata"] = FilterService._serialise_plan_extra(primitive_plan.extra)
            plan_summary.append(entry)
        metadata.setdefault("plan_primitives", plan_summary)

    def _resvg_policy_block(
        self,
        plan: "FilterPlan",
        viewport: Viewport,
        context: FilterContext,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> str | None:
        if overrides is None:
            overrides = self._policy_primitive_overrides(context)
        if not overrides:
            return None
        pixels = viewport.width * viewport.height
        for primitive_plan in plan.primitives:
            tag = primitive_plan.tag.lower()
            policy_entry = overrides.get(tag)
            if not policy_entry:
                continue
            if policy_entry.get("allow_resvg") is False:
                return f"{tag}:disabled"
            max_pixels = policy_entry.get("max_pixels")
            if isinstance(max_pixels, (int, float)) and max_pixels > 0 and pixels > max_pixels:
                return f"{tag}:max_pixels_exceeded"
        return None

    def _policy_primitive_overrides(self, context: FilterContext) -> dict[str, dict[str, Any]]:
        options = context.options if isinstance(context.options, dict) else {}
        policy = options.get("policy")
        if not isinstance(policy, Mapping):
            return {}
        primitives = policy.get("primitives")
        if not isinstance(primitives, Mapping):
            return {}
        overrides: dict[str, dict[str, Any]] = {}
        for name, config in primitives.items():
            key = str(name).strip().lower()
            if not key:
                continue
            if not isinstance(config, Mapping):
                continue
            entry: dict[str, Any] = {}
            if "allow_resvg" in config:
                allow_value = config.get("allow_resvg")
                if isinstance(allow_value, str):
                    token = allow_value.strip().lower()
                    if token in {"true", "1", "yes", "on"}:
                        entry["allow_resvg"] = True
                    elif token in {"false", "0", "no", "off"}:
                        entry["allow_resvg"] = False
                elif isinstance(allow_value, bool):
                    entry["allow_resvg"] = allow_value
                elif allow_value is not None:
                    entry["allow_resvg"] = bool(allow_value)
            if "allow_promotion" in config:
                promote_value = config.get("allow_promotion")
                if isinstance(promote_value, str):
                    token = promote_value.strip().lower()
                    if token in {"true", "1", "yes", "on"}:
                        entry["allow_promotion"] = True
                    elif token in {"false", "0", "no", "off"}:
                        entry["allow_promotion"] = False
                elif isinstance(promote_value, bool):
                    entry["allow_promotion"] = promote_value
                elif promote_value is not None:
                    entry["allow_promotion"] = bool(promote_value)
            if "max_pixels" in config:
                try:
                    value = float(config.get("max_pixels"))
                except (TypeError, ValueError):
                    value = None
                if value is not None and value > 0:
                    entry["max_pixels"] = int(value)
            if "max_arithmetic_coeff" in config:
                try:
                    coeff_value = float(config.get("max_arithmetic_coeff"))
                except (TypeError, ValueError):
                    coeff_value = None
                if coeff_value is not None and coeff_value >= 0:
                    entry["max_arithmetic_coeff"] = float(coeff_value)
            if "max_offset_distance" in config:
                try:
                    distance = float(config.get("max_offset_distance"))
                except (TypeError, ValueError):
                    distance = None
                if distance is not None and distance >= 0:
                    entry["max_offset_distance"] = float(distance)
            if "max_merge_inputs" in config:
                try:
                    merge_inputs = float(config.get("max_merge_inputs"))
                except (TypeError, ValueError):
                    merge_inputs = None
                if merge_inputs is not None and merge_inputs >= 0:
                    entry["max_merge_inputs"] = int(merge_inputs)
            if "max_component_functions" in config:
                try:
                    func_limit = float(config.get("max_component_functions"))
                except (TypeError, ValueError):
                    func_limit = None
                if func_limit is not None and func_limit >= 0:
                    entry["max_component_functions"] = int(func_limit)
            if "max_component_table_values" in config:
                try:
                    table_limit = float(config.get("max_component_table_values"))
                except (TypeError, ValueError):
                    table_limit = None
                if table_limit is not None and table_limit >= 0:
                    entry["max_component_table_values"] = int(table_limit)
            if "max_convolve_kernel" in config:
                try:
                    kernel_limit = float(config.get("max_convolve_kernel"))
                except (TypeError, ValueError):
                    kernel_limit = None
                if kernel_limit is not None and kernel_limit >= 0:
                    entry["max_convolve_kernel"] = int(kernel_limit)
            if "max_convolve_order" in config:
                try:
                    order_limit = float(config.get("max_convolve_order"))
                except (TypeError, ValueError):
                    order_limit = None
                if order_limit is not None and order_limit >= 0:
                    entry["max_convolve_order"] = int(order_limit)
            if entry:
                overrides[key] = entry
        return overrides

    @staticmethod
    def _serialise_plan_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
        def _coerce(value: Any) -> Any:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, Mapping):
                return {k: _coerce(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_coerce(v) for v in value]
            return str(value)

        return {key: _coerce(val) for key, val in extra.items()}

    @staticmethod
    def _plan_has_turbulence(plan: FilterPlan) -> bool:
        return any(primitive.tag.lower() == "feturbulence" for primitive in plan.primitives)

    @staticmethod
    def _surface_to_bmp(surface: Surface) -> bytes:
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

        if self._strategy != "auto":
            return self._strategy

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
    def _attach_raster_metadata(
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
            "primitive_metadata": [dict(primitive.extras) for primitive in descriptor.primitives],
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
