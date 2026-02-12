"""Filter policy provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..engine import PolicyProvider
from ..targets import PolicyTarget


class FilterPolicyProvider(PolicyProvider):
    """Return filter rendering preferences based on quality."""

    _KNOWN_FIELDS = {
        "strategy",
        "allow_anisotropic_native",
        "max_bitmap_stddev",
        "max_shadow_distance",
        "prefer_emf_blend_modes",
        "max_convolve_kernel",
        "max_glow_radius",
        "max_glow_alpha",
        "preferred_glow_strategy",
        "blur_strategy",
        "max_filter_primitives",
        "max_filter_complexity",
        "native_blur",
        "native_shadow",
        "approximation_allowed",
        "prefer_rasterization",
        "enable_telemetry",
        "telemetry_level",
    }

    _FALLBACKS: dict[str, Mapping[str, Any]] = {
        "high": {
            "strategy": "native",
            "allow_anisotropic_native": True,
            "max_bitmap_stddev": 96.0,
            "max_shadow_distance": 120.0,
            "prefer_emf_blend_modes": False,
            "max_convolve_kernel": 9,
            "max_glow_radius": 16.0,
            "max_glow_alpha": 0.95,
            "preferred_glow_strategy": "source",
            "blur_strategy": "soft_edge",
            "max_filter_primitives": 7,
            "max_filter_complexity": 80,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": True,
            "prefer_rasterization": False,
            "enable_telemetry": True,
            "telemetry_level": "detailed",
        },
        "balanced": {
            "strategy": "resvg",
            "allow_anisotropic_native": True,
            "max_bitmap_stddev": 64.0,
            "max_shadow_distance": 80.0,
            "prefer_emf_blend_modes": False,
            "max_convolve_kernel": 7,
            "max_glow_radius": 8.0,
            "max_glow_alpha": 0.75,
            "preferred_glow_strategy": "inherit",
            "blur_strategy": "soft_edge",
            "max_filter_primitives": 5,
            "max_filter_complexity": 50,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": True,
            "prefer_rasterization": False,
            "enable_telemetry": True,
            "telemetry_level": "summary",
        },
        "low": {
            "strategy": "raster",
            "allow_anisotropic_native": False,
            "max_bitmap_stddev": 32.0,
            "max_shadow_distance": 40.0,
            "prefer_emf_blend_modes": False,
            "max_convolve_kernel": 5,
            "max_glow_radius": 8.0,
            "max_glow_alpha": 0.7,
            "preferred_glow_strategy": "flood",
            "blur_strategy": "soft_edge",
            "max_filter_primitives": 3,
            "max_filter_complexity": 30,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": False,
            "prefer_rasterization": True,
            "enable_telemetry": False,
            "telemetry_level": "off",
        },
        "compatibility": {
            "strategy": "emf",
            "allow_anisotropic_native": False,
            "max_bitmap_stddev": 28.0,
            "max_shadow_distance": 30.0,
            "prefer_emf_blend_modes": False,
            "max_convolve_kernel": 3,
            "max_glow_radius": 6.0,
            "max_glow_alpha": 0.6,
            "preferred_glow_strategy": "flood",
            "blur_strategy": "soft_edge",
            "max_filter_primitives": 2,
            "max_filter_complexity": 20,
            "native_blur": True,
            "native_shadow": False,
            "approximation_allowed": False,
            "prefer_rasterization": True,
            "enable_telemetry": False,
            "telemetry_level": "off",
        },
    }

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "filter"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = self._normalise_quality(options.get("quality"))
        base_defaults, base_primitives = self._extract_target_defaults(options, quality)
        payload = dict(base_defaults)
        payload.update(self._copy_direct_overrides(options))
        overrides, primitive_overrides = self._collect_overrides(options)
        payload.update(overrides)
        primitive_payload = self._merge_primitive_overrides(
            base_primitives,
            self._extract_direct_primitive_overrides(options),
            primitive_overrides,
        )
        if primitive_payload:
            payload["primitives"] = primitive_payload
        fallback_defaults = self._FALLBACKS.get(quality, self._FALLBACKS["balanced"])
        default_strategy = payload.get("strategy", base_defaults.get("strategy", fallback_defaults.get("strategy", "auto")))
        payload["strategy"] = self._resolve_strategy(options, str(default_strategy))
        return self._coerce_payload(payload, quality)

    def _extract_target_defaults(
        self, options: Mapping[str, Any], quality: str
    ) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
        targets = options.get("targets")
        if isinstance(targets, Mapping):
            candidate = targets.get("filter")
            if isinstance(candidate, Mapping):
                candidate_map = dict(candidate)
                primitives = candidate_map.pop("primitives", None)
                return candidate_map, self._normalise_primitive_map(primitives)
        base = dict(self._FALLBACKS.get(quality, self._FALLBACKS["balanced"]))
        return base, {}

    @staticmethod
    def _normalise_quality(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower()
            if token in FilterPolicyProvider._FALLBACKS:
                return token
        return "balanced"

    def _collect_overrides(self, options: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        overrides: dict[str, Any] = {}
        primitive_overrides: dict[str, dict[str, Any]] = {}
        for key, raw in options.items():
            if not isinstance(key, str) or "." not in key:
                continue
            prefix, field = key.split(".", 1)
            if prefix != "filter" or not field:
                continue
            if field.startswith("primitives."):
                primitive_field = field.removeprefix("primitives.")
                primitive_name, _, attribute = primitive_field.partition(".")
                if not primitive_name or not attribute:
                    continue
                normalized_name = primitive_name.strip().lower()
                normalized_attr = attribute.replace("-", "_").strip().lower()
                if not normalized_name or not normalized_attr:
                    continue
                entry = primitive_overrides.setdefault(normalized_name, {})
                entry[normalized_attr] = raw
                continue
            overrides[field] = raw
        return overrides, primitive_overrides

    def _copy_direct_overrides(self, options: Mapping[str, Any]) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for field in self._KNOWN_FIELDS:
            if field in options:
                overrides[field] = options[field]
        return overrides

    def _resolve_strategy(self, options: Mapping[str, Any], default: str) -> str:
        explicit = options.get("filter_strategy")
        if isinstance(explicit, str):
            token = explicit.strip().lower()
            if token in {"auto", "native", "native-if-neutral", "vector", "emf", "raster", "resvg", "resvg-only"}:
                return token
        overrides = options.get("filter.strategy")
        if isinstance(overrides, str):
            token = overrides.strip().lower()
            if token in {"auto", "native", "native-if-neutral", "vector", "emf", "raster", "resvg", "resvg-only"}:
                return token
        return default or "auto"

    def _coerce_payload(self, payload: Mapping[str, Any], quality: str) -> dict[str, Any]:
        strategy = str(payload.get("strategy", "auto")).strip().lower()
        result: dict[str, Any] = {"quality": quality, "strategy": strategy}
        result["allow_anisotropic_native"] = self._coerce_bool(payload.get("allow_anisotropic_native"))
        result["max_bitmap_stddev"] = self._coerce_float(payload.get("max_bitmap_stddev"))
        result["max_shadow_distance"] = self._coerce_float(payload.get("max_shadow_distance"))
        result["prefer_emf_blend_modes"] = self._coerce_bool(payload.get("prefer_emf_blend_modes"))
        result["max_convolve_kernel"] = self._coerce_int(payload.get("max_convolve_kernel"))
        result["max_glow_radius"] = self._coerce_float(payload.get("max_glow_radius"))
        result["max_glow_alpha"] = self._coerce_float(payload.get("max_glow_alpha"))
        result["preferred_glow_strategy"] = self._coerce_glow_strategy(payload.get("preferred_glow_strategy"))
        result["blur_strategy"] = self._coerce_blur_strategy(payload.get("blur_strategy"))
        result["max_filter_primitives"] = self._coerce_int(payload.get("max_filter_primitives"))
        result["max_filter_complexity"] = self._coerce_int(payload.get("max_filter_complexity"))
        result["native_blur"] = self._coerce_bool(payload.get("native_blur"))
        result["native_shadow"] = self._coerce_bool(payload.get("native_shadow"))
        result["approximation_allowed"] = self._coerce_bool(payload.get("approximation_allowed"))
        result["prefer_rasterization"] = self._coerce_bool(payload.get("prefer_rasterization"))
        result["enable_telemetry"] = self._coerce_bool(payload.get("enable_telemetry"))
        result["telemetry_level"] = self._coerce_telemetry_level(payload.get("telemetry_level"))
        primitives = self._coerce_primitives(payload.get("primitives"))
        if primitives:
            result["primitives"] = primitives
        return result

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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
    def _extract_direct_primitive_overrides(options: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        candidate = options.get("filter_primitives")
        if not isinstance(candidate, Mapping):
            return {}
        return FilterPolicyProvider._normalise_primitive_map(candidate)

    def _coerce_primitives(self, value: Any) -> dict[str, dict[str, Any]]:
        mapping = self._normalise_primitive_map(value)
        coerced: dict[str, dict[str, Any]] = {}
        for name, config in mapping.items():
            entry: dict[str, Any] = {}
            if "allow_resvg" in config:
                entry["allow_resvg"] = self._coerce_bool(config.get("allow_resvg"))
            if "allow_promotion" in config:
                entry["allow_promotion"] = self._coerce_bool(config.get("allow_promotion"))
            if "max_pixels" in config:
                max_pixels = self._coerce_int(config.get("max_pixels"))
                if max_pixels is not None and max_pixels > 0:
                    entry["max_pixels"] = max_pixels
            if "max_arithmetic_coeff" in config:
                coeff = self._coerce_float(config.get("max_arithmetic_coeff"))
                if coeff is not None and coeff >= 0:
                    entry["max_arithmetic_coeff"] = coeff
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


__all__ = ["FilterPolicyProvider"]
