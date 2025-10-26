"""Traversal-related hooks for the IR converter."""

from __future__ import annotations

from typing import Any, Iterable

from lxml import etree

from svg2ooxml.css.resolver import StyleContext as CSSStyleContext
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.scene import ClipRef, Group, MaskInstance, MaskRef
from svg2ooxml.services.filter_types import FilterEffectResult
from svg2ooxml.parser.geometry import Matrix2D

from . import clipping, styles_runtime, use_runtime
from .constants import DEFAULT_TOLERANCE
from .coordinate_space import CoordinateSpace
from .geometry_utils import is_axis_aligned


class TraversalHooksMixin:
    """Mixin exposing traversal callbacks consumed by :class:`ElementTraversal`."""

    _css_context: CSSStyleContext | None = None

    def convert_group(self, element: etree._Element, children: list, matrix) -> Group | None:
        if not children:
            return None
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        group = Group(
            children=children,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            transform=None if matrix.is_identity() else matrix,
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", group.metadata)
        return group

    def convert_element(
        self,
        *,
        tag: str,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ):
        if not tag:
            return None

        if tag == "foreignObject":
            return self._convert_foreign_object(
                element=element,
                coord_space=coord_space,
                traverse_callback=traverse_callback,
                current_navigation=current_navigation,
            )

        dispatch = {
            "rect": self._convert_rect,
            "circle": self._convert_circle,
            "ellipse": self._convert_ellipse,
            "line": self._convert_line,
            "path": self._convert_path,
            "polygon": self._convert_polygon,
            "polyline": self._convert_polyline,
            "image": self._convert_image,
            "text": self._text_converter.convert,
        }

        handler = dispatch.get(tag)
        if handler is None:
            return None
        try:
            return handler(element=element, coord_space=coord_space)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.error("Failed to convert <%s>: %s", tag, exc)
            return None

    def attach_metadata(self, ir_object, element: etree._Element, navigation_spec) -> None:
        if ir_object is None or not hasattr(ir_object, "metadata"):
            return
        metadata: dict[str, Any] = ir_object.metadata  # type: ignore[attr-defined]

        element_id = element.get("id")
        if element_id:
            metadata.setdefault("element_ids", []).append(element_id)

        class_attr = element.get("class")
        if class_attr:
            metadata["class"] = class_attr

        title = element.get("title")
        if title:
            metadata.setdefault("attributes", {})["title"] = title

        if navigation_spec is not None:
            try:
                metadata["navigation"] = navigation_spec.as_dict()
            except Exception:  # pragma: no cover - defensive
                metadata["navigation"] = navigation_spec

        self._apply_filter_metadata(ir_object, element, metadata)

    def _apply_filter_metadata(
        self,
        ir_object,
        element: etree._Element,
        metadata: dict[str, Any],
    ) -> None:
        filter_attr = element.get("filter")
        filter_id = self._normalize_href_reference(filter_attr)
        if not filter_id:
            return

        filters_meta = metadata.setdefault("filters", [])
        filter_entry = next(
            (entry for entry in filters_meta if isinstance(entry, dict) and entry.get("id") == filter_id),
            None,
        )
        if filter_entry is None:
            filter_entry = {"id": filter_id}
            filters_meta.append(filter_entry)

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
                descriptor = descriptor_map.get(filter_id) if isinstance(descriptor_map, dict) else None
                if descriptor is not None:
                    descriptor_payload = {
                        "filter_units": descriptor.filter_units,
                        "primitive_units": descriptor.primitive_units,
                        "primitive_count": len(descriptor.primitives),
                        "primitive_tags": [primitive.tag for primitive in descriptor.primitives],
                        "filter_region": dict(descriptor.region or {}),
                    }

                filter_context_payload = {"element": element, "policy": filter_policy}
                if bbox_dict is not None:
                    filter_context_payload["ir_bbox"] = bbox_dict
                if descriptor_payload is not None:
                    filter_context_payload["resvg_descriptor"] = descriptor_payload

                effect_results = filter_service.resolve_effects(
                    filter_id,
                    context=filter_context_payload,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.debug("Failed to resolve effects for filter %s: %s", filter_id, exc)

        if not effect_results:
            effect_results = [
                FilterEffectResult(
                    effect=CustomEffect(drawingml=f"FILTER:{filter_id}"),
                    strategy="raster",
                    metadata={},
                    fallback="bitmap",
                )
            ]

        tracer = getattr(self, "_tracer", None)
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

        if hasattr(ir_object, "effects"):
            for result in effect_results:
                if result.effect is not None:
                    ir_object.effects.append(result.effect)  # type: ignore[attr-defined]

        selected_result = effect_results[-1]
        chosen_strategy = selected_result.strategy
        fallback_mode = selected_result.fallback

        filter_entry["strategy"] = chosen_strategy

        if fallback_mode:
            filter_entry["fallback"] = fallback_mode

        detailed = metadata.setdefault("filter_metadata", {})
        selected_meta = dict(selected_result.metadata or {})
        if "descriptor" not in selected_meta and descriptor_payload is not None:
            selected_meta["descriptor"] = descriptor_payload
        if "bounds" not in selected_meta and bbox_dict is not None:
            selected_meta["bounds"] = bbox_dict
        selected_meta["strategy"] = chosen_strategy

        if len(effect_results) > 1:
            assets = selected_meta.setdefault("fallback_assets", [])
            if isinstance(assets, list):
                for prior in effect_results[:-1]:
                    prior_assets = (
                        prior.metadata.get("fallback_assets") if isinstance(prior.metadata, dict) else None
                    )
                    if isinstance(prior_assets, list):
                        assets.extend(prior_assets)
        detailed[filter_id] = selected_meta

        policy = metadata.setdefault("policy", {})

        assets = selected_meta.get("fallback_assets")
        if isinstance(assets, list) and assets:
            media_policy = policy.setdefault("media", {})
            filter_assets = media_policy.setdefault("filter_assets", {})
            filter_assets[filter_id] = assets

        geometry_policy = policy.setdefault("geometry", {})
        if fallback_mode and "suggest_fallback" not in geometry_policy:
            geometry_policy["suggest_fallback"] = fallback_mode
        effects_policy = policy.setdefault("effects", {})
        filters_policy = effects_policy.setdefault("filters", [])
        if filter_id not in (entry.get("id") for entry in filters_policy if isinstance(entry, dict)):
            filters_policy.append(
                {
                    "id": filter_id,
                    "strategy": chosen_strategy,
                    "mode": fallback_mode or chosen_strategy,
                }
            )

        if bbox_dict is not None:
            filter_entry.setdefault("bounds", bbox_dict)
        if descriptor_payload is not None:
            filter_entry.setdefault("descriptor", descriptor_payload)

    def expand_use(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ) -> list:
        href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get("href")
        reference_id = self._normalize_href_reference(href_attr)
        if reference_id is None:
            return []

        target = self._symbol_definitions.get(reference_id)
        if target is None:
            target = self._element_index.get(reference_id)
        if target is None:
            return []

        if reference_id in self._use_expansion_stack:
            self._logger.debug("Detected recursive <use> expansion for %s", reference_id)
            return []

        self._symbol_usage.add(reference_id)
        target_tag = self._local_name(getattr(target, "tag", "")) if isinstance(target, etree._Element) else None
        self._trace_stage(
            "symbol_expand",
            stage="symbol",
            subject=reference_id,
            metadata={"target_tag": target_tag},
        )
        self._use_expansion_stack.add(reference_id)
        try:
            nodes = use_runtime.instantiate_use_target(self, target, element)
            transform_matrix = use_runtime.compute_use_transform(
                self,
                element,
                target,
                tolerance=DEFAULT_TOLERANCE,
            )
            dx, dy = use_runtime.resolve_use_offsets(self, element)
            use_runtime.apply_use_transform(
                self,
                nodes,
                transform_matrix or Matrix2D.identity(),
                dx,
                dy,
                tolerance=DEFAULT_TOLERANCE,
            )
            results: list = []
            for node in nodes:
                results.extend(traverse_callback(node, current_navigation))
            return results
        finally:
            self._use_expansion_stack.discard(reference_id)

    def _prepare_context(self, result) -> None:
        resvg_clip_defs = getattr(self, "_resvg_clip_definitions", {})
        self._clip_definitions = dict(resvg_clip_defs or {})

        resvg_masks = getattr(self, "_resvg_mask_info", {})
        self._mask_info = dict(resvg_masks or {})
        style_context = result.style_context
        if style_context is not None:
            conversion = style_context.conversion
            viewport_width = style_context.viewport_width
            viewport_height = style_context.viewport_height
        else:
            viewport_width = result.width_px or 0.0
            viewport_height = result.height_px or 0.0
            conversion = self._unit_converter.create_context(
                width=viewport_width,
                height=viewport_height,
                font_size=12.0,
                parent_width=viewport_width,
                parent_height=viewport_height,
            )
        self._css_context = CSSStyleContext(
            conversion=conversion,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        self._conversion_context = conversion
        if result.svg_root is not None:
            self._element_index = self._build_element_index(result.svg_root)
        else:
            self._element_index = {}
        self._symbol_definitions = dict(result.symbols or {})
        if self._symbol_definitions:
            self._trace_stage(
                "symbol_definitions",
                stage="symbol",
                metadata={"count": len(self._symbol_definitions)},
            )
        marker_defs = getattr(result, "markers", None)
        if marker_defs:
            self._marker_definitions = dict(marker_defs)
            self._trace_stage(
                "marker_definitions",
                stage="marker",
                metadata={"count": len(marker_defs)},
            )
        else:
            self._marker_definitions = {}
        self._use_expansion_stack.clear()

    def _resolve_clip_ref(self, element: etree._Element) -> ClipRef | None:
        clip_ref = clipping.resolve_clip_ref(
            element,
            clip_definitions=self._clip_definitions,
            services=self._services,
            logger=self._logger,
            tolerance=DEFAULT_TOLERANCE,
            is_axis_aligned=is_axis_aligned,
        )
        if clip_ref is not None:
            decision = "emf" if getattr(clip_ref.strategy, "value", clip_ref.strategy) == "emf" else "native"
            metadata = {
                "clip_id": clip_ref.clip_id,
                "strategy": getattr(clip_ref.strategy, "value", clip_ref.strategy),
                "custom_geometry": bool(clip_ref.custom_geometry_xml),
            }
            if clip_ref.clip_id:
                self._clip_usage.add(clip_ref.clip_id)
                self._trace_stage(
                    "clip_applied",
                    stage="clip",
                    subject=clip_ref.clip_id,
                    metadata={"strategy": metadata["strategy"], "custom_geometry": metadata["custom_geometry"]},
                )
            self._trace_geometry_decision(element, decision, metadata)
        return clip_ref

    def _resolve_mask_ref(self, element: etree._Element) -> tuple[MaskRef | None, MaskInstance | None]:
        # TODO(ADR-geometry-ir): Surface mask primitives to downstream mappers so native rect/circle masks avoid raster fallbacks.
        mask_ref, mask_instance = clipping.resolve_mask_ref(element, mask_info=self._mask_info)
        if mask_ref is not None and mask_ref.mask_id:
            self._mask_usage.add(mask_ref.mask_id)
            self._trace_stage(
                "mask_applied",
                stage="mask",
                subject=mask_ref.mask_id,
                metadata={"has_definition": mask_ref.definition is not None},
            )
        return mask_ref, mask_instance

    @staticmethod
    def _normalize_href_reference(href: str | None) -> str | None:
        if not href:
            return None
        token = href.strip()
        if token.startswith("url(") and token.endswith(")"):
            token = token[4:-1].strip().strip("\"'")
        if token.startswith("#"):
            return token[1:]
        return None

    @staticmethod
    def _local_name(tag: Any) -> str:
        if not isinstance(tag, str):
            return ""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def _make_namespaced_tag(reference: etree._Element, local: str) -> str:
        tag = reference.tag
        if isinstance(tag, str) and "}" in tag:
            namespace = tag.split("}", 1)[0][1:]
            return f"{{{namespace}}}{local}"
        return local

    @staticmethod
    def _build_element_index(root: etree._Element) -> dict[str, etree._Element]:
        index: dict[str, etree._Element] = {}
        for node in root.iter():
            node_id = node.get("id")
            if node_id:
                index[node_id] = node
        return index


__all__ = ["TraversalHooksMixin"]
