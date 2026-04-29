"""Filter policy provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.policy.engine import PolicyProvider
from svg2ooxml.policy.providers.common import normalise_quality
from svg2ooxml.policy.providers.filter_coercion import FilterPolicyCoercionMixin
from svg2ooxml.policy.targets import PolicyTarget


class FilterPolicyProvider(FilterPolicyCoercionMixin, PolicyProvider):
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
        "enable_effect_dag",
        "enable_native_color_transforms",
        "enable_blip_effect_enrichment",
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
            "enable_effect_dag": False,
            "enable_native_color_transforms": False,
            "enable_blip_effect_enrichment": False,
            "enable_telemetry": True,
            "telemetry_level": "detailed",
        },
        "balanced": {
            "strategy": "resvg",
            "allow_anisotropic_native": True,
            "max_bitmap_stddev": 96.0,
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
            "enable_effect_dag": False,
            "enable_native_color_transforms": False,
            "enable_blip_effect_enrichment": False,
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
            "enable_effect_dag": False,
            "enable_native_color_transforms": False,
            "enable_blip_effect_enrichment": False,
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
            "enable_effect_dag": False,
            "enable_native_color_transforms": False,
            "enable_blip_effect_enrichment": False,
            "enable_telemetry": False,
            "telemetry_level": "off",
        },
    }

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "filter"

    def evaluate(
        self, target: PolicyTarget, options: Mapping[str, Any]
    ) -> Mapping[str, Any]:
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
        default_strategy = payload.get(
            "strategy",
            base_defaults.get("strategy", fallback_defaults.get("strategy", "auto")),
        )
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
        return normalise_quality(value, FilterPolicyProvider._FALLBACKS)

    def _collect_overrides(
        self, options: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
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
            if token in {
                "auto",
                "native",
                "native-if-neutral",
                "vector",
                "emf",
                "raster",
                "resvg",
                "resvg-only",
            }:
                return token
        overrides = options.get("filter.strategy")
        if isinstance(overrides, str):
            token = overrides.strip().lower()
            if token in {
                "auto",
                "native",
                "native-if-neutral",
                "vector",
                "emf",
                "raster",
                "resvg",
                "resvg-only",
            }:
                return token
        return default or "auto"



__all__ = ["FilterPolicyProvider"]
