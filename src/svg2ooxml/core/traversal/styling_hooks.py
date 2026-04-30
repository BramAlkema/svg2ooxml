"""Filter/style application hooks for the IR converter."""

from __future__ import annotations

import copy
from typing import Any

from lxml import etree

from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.filters.input_descriptors import paint_input_descriptors
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.scene import Group
from svg2ooxml.services.filter_types import FilterEffectResult


class StylingHooksMixin:
    """Mixin providing filter metadata and styling hook methods."""

    def _apply_filter_metadata(
        self,
        ir_object,
        element: etree._Element,
        metadata: dict[str, Any],
    ) -> None:
        filter_attr = element.get("filter")
        if not filter_attr:
            filter_attr = parse_style_attr(element.get("style")).get("filter")
        filter_id = self._normalize_href_reference(filter_attr)
        if not filter_id:
            return

        filters_meta = metadata.setdefault("filters", [])
        filter_entry = next(
            (
                entry
                for entry in filters_meta
                if isinstance(entry, dict) and entry.get("id") == filter_id
            ),
            None,
        )
        if filter_entry is None:
            filter_entry = {"id": filter_id}
            filters_meta.append(filter_entry)

        tracer = getattr(self, "_tracer", None)
        filter_service = getattr(self._services, "filter_service", None)
        effect_results: list[FilterEffectResult] = []
        descriptor_payload = None
        bbox_dict: dict[str, float] | None = None
        if filter_service is not None:
            try:
                filter_policy = self._policy_options("filter") or {}
                bbox_value = getattr(ir_object, "bbox", None)
                if bbox_value is not None and all(
                    hasattr(bbox_value, attr) for attr in ("x", "y", "width", "height")
                ):
                    bbox_dict = {
                        "x": float(bbox_value.x),
                        "y": float(bbox_value.y),
                        "width": float(bbox_value.width),
                        "height": float(bbox_value.height),
                    }

                descriptor_map = getattr(self, "_resvg_filter_descriptors", {})
                descriptor = (
                    descriptor_map.get(filter_id)
                    if isinstance(descriptor_map, dict)
                    else None
                )
                if descriptor is not None:
                    descriptor_payload = {
                        "filter_units": descriptor.filter_units,
                        "primitive_units": descriptor.primitive_units,
                        "primitive_count": len(descriptor.primitives),
                        "primitive_tags": [
                            primitive.tag for primitive in descriptor.primitives
                        ],
                        "filter_region": dict(descriptor.region or {}),
                    }

                filter_context_payload = {"element": element, "policy": filter_policy}
                if isinstance(filter_id, str) and filter_id:
                    filter_context_payload["filter_id"] = filter_id
                filter_inputs = self._collect_filter_inputs(ir_object)
                if filter_inputs:
                    filter_context_payload["filter_inputs"] = filter_inputs
                if bbox_dict is not None:
                    filter_context_payload["ir_bbox"] = bbox_dict
                if descriptor_payload is not None:
                    filter_context_payload["resvg_descriptor"] = descriptor_payload
                ctm = metadata.get("_ctm")
                if isinstance(ctm, dict):
                    filter_context_payload["ctm"] = dict(ctm)
                if tracer is not None:
                    filter_context_payload["tracer"] = tracer

                effect_results = filter_service.resolve_effects(
                    filter_id,
                    context=filter_context_payload,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.debug(
                    "Failed to resolve effects for filter %s: %s", filter_id, exc
                )

        if not effect_results:
            effect_results = [
                FilterEffectResult(
                    effect=CustomEffect(drawingml=f"FILTER:{filter_id}"),
                    strategy="raster",
                    metadata={},
                    fallback="bitmap",
                )
            ]

        if tracer is not None:
            for result in effect_results:
                decision = result.fallback or result.strategy or "native"
                tracer.record_paint_decision(
                    paint_type="filter",
                    paint_id=filter_id,
                    decision=decision,
                    metadata={
                        "strategy": result.strategy,
                        "fallback": result.fallback,
                        "metadata": dict(result.metadata or {}),
                    },
                )
                self._trace_stage(
                    "filter_effect",
                    stage="filter",
                    subject=filter_id,
                    metadata={
                        "strategy": result.strategy,
                        "fallback": result.fallback,
                        "metadata": dict(result.metadata or {}),
                    },
                )

        selected_result = self._select_filter_result(effect_results)
        chosen_strategy = selected_result.strategy
        fallback_mode = selected_result.fallback
        effective_fallback = fallback_mode
        if effective_fallback is None and chosen_strategy == "native":
            fallback_ranks = {"bitmap": 3, "raster": 3, "emf": 2, "vector": 1}
            for candidate in effect_results:
                candidate_fallback = (
                    candidate.fallback.lower()
                    if isinstance(candidate.fallback, str)
                    else None
                )
                if candidate_fallback not in fallback_ranks:
                    continue
                if effective_fallback is None:
                    effective_fallback = candidate_fallback
                    continue
                if fallback_ranks[candidate_fallback] > fallback_ranks.get(
                    effective_fallback, 0
                ):
                    effective_fallback = candidate_fallback

        filter_entry["strategy"] = chosen_strategy

        if effective_fallback:
            filter_entry["fallback"] = effective_fallback

        detailed = metadata.setdefault("filter_metadata", {})
        selected_meta = dict(selected_result.metadata or {})
        if "descriptor" not in selected_meta and descriptor_payload is not None:
            selected_meta["descriptor"] = descriptor_payload
        if "bounds" not in selected_meta and bbox_dict is not None:
            selected_meta["bounds"] = bbox_dict
        selected_meta["strategy"] = chosen_strategy
        if effective_fallback:
            selected_meta["fallback"] = effective_fallback

        if len(effect_results) > 1:
            assets = selected_meta.setdefault("fallback_assets", [])
            if isinstance(assets, list):
                for prior in effect_results:
                    if prior is selected_result:
                        continue
                    prior_assets = (
                        prior.metadata.get("fallback_assets")
                        if isinstance(prior.metadata, dict)
                        else None
                    )
                    if isinstance(prior_assets, list):
                        assets.extend(prior_assets)
        detailed[filter_id] = selected_meta

        if isinstance(ir_object, Group):
            filter_types = {
                str(result.metadata.get("filter_type", "")).lower()
                for result in effect_results
                if isinstance(result.metadata, dict)
                and result.metadata.get("filter_type")
            }
            stack_types = {
                str(result.metadata.get("stack_type", "")).lower()
                for result in effect_results
                if isinstance(result.metadata, dict)
                and result.metadata.get("stack_type")
            }
            if not filter_types:
                fallback_type = selected_meta.get("filter_type")
                if isinstance(fallback_type, str) and fallback_type:
                    filter_types = {fallback_type.lower()}
            if not stack_types:
                fallback_stack = selected_meta.get("stack_type")
                if isinstance(fallback_stack, str) and fallback_stack:
                    stack_types = {fallback_stack.lower()}
            targets = self._collect_group_effect_targets(
                ir_object, filter_types, stack_types
            )
        elif hasattr(ir_object, "effects"):
            targets = [ir_object]
        else:
            targets = []

        for result in effect_results:
            if result.effect is None:
                continue
            for target in targets:
                if result.effect in target.effects:  # type: ignore[attr-defined]
                    continue
                target.effects.append(result.effect)  # type: ignore[attr-defined]

        policy = metadata.setdefault("policy", {})

        assets = selected_meta.get("fallback_assets")
        if isinstance(assets, list) and assets:
            media_policy = policy.setdefault("media", {})
            filter_assets = media_policy.setdefault("filter_assets", {})
            filter_assets[filter_id] = assets

        geometry_policy = policy.setdefault("geometry", {})
        if effective_fallback and "suggest_fallback" not in geometry_policy:
            geometry_policy["suggest_fallback"] = effective_fallback
        effects_policy = policy.setdefault("effects", {})
        filters_policy = effects_policy.setdefault("filters", [])
        if filter_id not in (
            entry.get("id") for entry in filters_policy if isinstance(entry, dict)
        ):
            filters_policy.append(
                {
                    "id": filter_id,
                    "strategy": chosen_strategy,
                    "mode": effective_fallback or chosen_strategy,
                }
            )

        if bbox_dict is not None:
            filter_entry.setdefault("bounds", bbox_dict)
        if descriptor_payload is not None:
            filter_entry.setdefault("descriptor", descriptor_payload)

    def _select_filter_result(
        self, results: list[FilterEffectResult]
    ) -> FilterEffectResult:
        if not results:
            return FilterEffectResult(
                effect=CustomEffect(drawingml=""),
                strategy="raster",
                metadata={},
                fallback="bitmap",
            )

        rank_map = self._STRATEGY_RANK

        def _score(index: int, result: FilterEffectResult) -> tuple[int, int, int, int]:
            meta = result.metadata if isinstance(result.metadata, dict) else {}
            no_op = bool(meta.get("no_op"))
            fallback_none = result.fallback is None
            strategy = (result.strategy or "").lower()
            rank = rank_map.get(strategy, 0)
            return (0 if no_op else 1, 1 if fallback_none else 0, rank, index)

        best_index, _ = max(
            enumerate(results), key=lambda item: _score(item[0], item[1])
        )
        return results[best_index]

    def _collect_group_effect_targets(
        self,
        group: Group,
        filter_types: set[str],
        stack_types: set[str] | None = None,
    ) -> list[Any]:
        stack_types = stack_types or set()
        supported_stack_types = {
            "diffuse_lighting_composite",
            "specular_lighting_composite",
        }
        if "gaussian_blur" not in filter_types and not (
            stack_types & supported_stack_types
        ):
            return []

        targets: list[Any] = []

        def _walk(node: Any) -> None:
            if isinstance(node, Group):
                for child in node.children:
                    _walk(child)
                return
            if hasattr(node, "effects"):
                targets.append(node)

        _walk(group)
        return targets

    def _collect_filter_inputs(self, ir_object: Any) -> dict[str, Any]:
        descriptor = self._shape_descriptor(ir_object)
        if descriptor is None:
            return {}

        graphic_meta = copy.deepcopy(descriptor)
        alpha_meta = {
            "shape_type": descriptor.get("shape_type"),
            "geometry": copy.deepcopy(descriptor.get("geometry")),
            "bbox": copy.deepcopy(descriptor.get("bbox")),
            "alpha_source": "SourceGraphic",
        }
        inputs = {
            "SourceGraphic": graphic_meta,
            "SourceAlpha": alpha_meta,
        }
        inputs.update(paint_input_descriptors(inputs))
        return inputs
