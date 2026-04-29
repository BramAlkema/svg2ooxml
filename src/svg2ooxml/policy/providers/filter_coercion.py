"""Filter policy payload coercion helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.math_utils import (
    coerce_bool,
    coerce_int,
    finite_float,
)


class FilterPolicyCoercionMixin:
    """Coerce filter policy payload values into runtime policy types."""

    def _coerce_payload(
        self, payload: Mapping[str, Any], quality: str
    ) -> dict[str, Any]:
        strategy = str(payload.get("strategy", "auto")).strip().lower()
        result: dict[str, Any] = {"quality": quality, "strategy": strategy}
        result["allow_anisotropic_native"] = self._coerce_bool(
            payload.get("allow_anisotropic_native")
        )
        result["max_bitmap_stddev"] = self._coerce_float(
            payload.get("max_bitmap_stddev")
        )
        result["max_shadow_distance"] = self._coerce_float(
            payload.get("max_shadow_distance")
        )
        result["prefer_emf_blend_modes"] = self._coerce_bool(
            payload.get("prefer_emf_blend_modes")
        )
        result["max_convolve_kernel"] = self._coerce_int(
            payload.get("max_convolve_kernel")
        )
        result["max_glow_radius"] = self._coerce_float(payload.get("max_glow_radius"))
        result["max_glow_alpha"] = self._coerce_float(payload.get("max_glow_alpha"))
        result["preferred_glow_strategy"] = self._coerce_glow_strategy(
            payload.get("preferred_glow_strategy")
        )
        result["blur_strategy"] = self._coerce_blur_strategy(
            payload.get("blur_strategy")
        )
        result["max_filter_primitives"] = self._coerce_int(
            payload.get("max_filter_primitives")
        )
        result["max_filter_complexity"] = self._coerce_int(
            payload.get("max_filter_complexity")
        )
        result["native_blur"] = self._coerce_bool(payload.get("native_blur"))
        result["native_shadow"] = self._coerce_bool(payload.get("native_shadow"))
        result["approximation_allowed"] = self._coerce_bool(
            payload.get("approximation_allowed")
        )
        result["prefer_rasterization"] = self._coerce_bool(
            payload.get("prefer_rasterization")
        )
        result["enable_effect_dag"] = self._coerce_bool(
            payload.get("enable_effect_dag")
        )
        result["enable_native_color_transforms"] = self._coerce_bool(
            payload.get("enable_native_color_transforms")
        )
        result["enable_blip_effect_enrichment"] = self._coerce_bool(
            payload.get("enable_blip_effect_enrichment")
        )
        result["enable_telemetry"] = self._coerce_bool(payload.get("enable_telemetry"))
        result["telemetry_level"] = self._coerce_telemetry_level(
            payload.get("telemetry_level")
        )
        primitives = self._coerce_primitives(payload.get("primitives"))
        if primitives:
            result["primitives"] = primitives
        return result

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        return coerce_bool(value)

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        return finite_float(value)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        return coerce_int(value)

    @staticmethod
    def _coerce_glow_strategy(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"inherit", "source", "flood", "style"}:
                return token
        return "inherit"

    @staticmethod
    def _coerce_blur_strategy(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower().replace("-", "_")
            if token in {"soft_edge", "softedge"}:
                return "soft_edge"
            if token in {"blur"}:
                return "blur"
            if token in {"outer_shadow", "outershdw", "shadow", "drop_shadow"}:
                return "outer_shadow"
            if token in {"inner_shadow", "innershdw", "inner"}:
                return "inner_shadow"
        return "soft_edge"

    @staticmethod
    def _coerce_telemetry_level(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"off", "summary", "detailed"}:
                return token
        return "summary"

    @staticmethod
    def _normalise_primitive_map(value: Any) -> dict[str, Mapping[str, Any]]:
        if not isinstance(value, Mapping):
            return {}
        normalized: dict[str, Mapping[str, Any]] = {}
        for key, config in value.items():
            if not isinstance(config, Mapping):
                continue
            name = str(key).strip().lower()
            if not name:
                continue
            normalized[name] = dict(config)
        return normalized

    @staticmethod
    def _merge_primitive_overrides(
        *mappings: Mapping[str, Mapping[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for mapping in mappings:
            if not mapping:
                continue
            for name, config in mapping.items():
                if not isinstance(config, Mapping):
                    continue
                key = str(name).strip().lower()
                if not key:
                    continue
                target = merged.setdefault(key, {})
                for attr, value in config.items():
                    attr_name = str(attr).replace("-", "_").strip().lower()
                    if not attr_name:
                        continue
                    target[attr_name] = value
        return merged

    @staticmethod
    def _extract_direct_primitive_overrides(
        options: Mapping[str, Any],
    ) -> dict[str, Mapping[str, Any]]:
        candidate = options.get("filter_primitives")
        if not isinstance(candidate, Mapping):
            return {}
        return FilterPolicyCoercionMixin._normalise_primitive_map(candidate)

    def _coerce_primitives(self, value: Any) -> dict[str, dict[str, Any]]:
        mapping = self._normalise_primitive_map(value)
        coerced: dict[str, dict[str, Any]] = {}
        for name, config in mapping.items():
            entry: dict[str, Any] = {}
            if "allow_resvg" in config:
                entry["allow_resvg"] = self._coerce_bool(config.get("allow_resvg"))
            if "allow_promotion" in config:
                entry["allow_promotion"] = self._coerce_bool(
                    config.get("allow_promotion")
                )
            if "allow_group_mimic" in config:
                entry["allow_group_mimic"] = self._coerce_bool(
                    config.get("allow_group_mimic")
                )
            if "max_pixels" in config:
                max_pixels = self._coerce_int(config.get("max_pixels"))
                if max_pixels is not None and max_pixels > 0:
                    entry["max_pixels"] = max_pixels
            if "max_arithmetic_coeff" in config:
                coeff = self._coerce_float(config.get("max_arithmetic_coeff"))
                if coeff is not None and coeff >= 0:
                    entry["max_arithmetic_coeff"] = coeff
            if "group_blur_strategy" in config:
                entry["group_blur_strategy"] = self._coerce_blur_strategy(
                    config.get("group_blur_strategy")
                )
            if "radius_scale" in config:
                scale = self._coerce_float(config.get("radius_scale"))
                if scale is not None and scale > 0:
                    entry["radius_scale"] = scale
            if "group_radius_scale" in config:
                group_scale = self._coerce_float(config.get("group_radius_scale"))
                if group_scale is not None and group_scale > 0:
                    entry["group_radius_scale"] = group_scale
            if "max_offset_distance" in config:
                distance = self._coerce_float(config.get("max_offset_distance"))
                if distance is not None and distance >= 0:
                    entry["max_offset_distance"] = distance
            if "max_merge_inputs" in config:
                merge_inputs = self._coerce_int(config.get("max_merge_inputs"))
                if merge_inputs is not None and merge_inputs >= 0:
                    entry["max_merge_inputs"] = merge_inputs
            if "max_component_functions" in config:
                func_limit = self._coerce_int(config.get("max_component_functions"))
                if func_limit is not None and func_limit >= 0:
                    entry["max_component_functions"] = func_limit
            if "max_component_table_values" in config:
                table_limit = self._coerce_int(config.get("max_component_table_values"))
                if table_limit is not None and table_limit >= 0:
                    entry["max_component_table_values"] = table_limit
            if "max_convolve_kernel" in config:
                kernel_limit = self._coerce_int(config.get("max_convolve_kernel"))
                if kernel_limit is not None and kernel_limit >= 0:
                    entry["max_convolve_kernel"] = kernel_limit
            if "max_convolve_order" in config:
                order_limit = self._coerce_int(config.get("max_convolve_order"))
                if order_limit is not None and order_limit >= 0:
                    entry["max_convolve_order"] = order_limit
            if entry:
                coerced[name] = entry
        return coerced


__all__ = ["FilterPolicyCoercionMixin"]
