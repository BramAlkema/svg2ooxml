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
        "max_filter_primitives",
        "max_filter_complexity",
        "native_blur",
        "native_shadow",
        "approximation_allowed",
        "prefer_rasterization",
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
            "max_filter_primitives": 7,
            "max_filter_complexity": 80,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": True,
            "prefer_rasterization": False,
        },
        "balanced": {
            "strategy": "auto",
            "allow_anisotropic_native": True,
            "max_bitmap_stddev": 64.0,
            "max_shadow_distance": 80.0,
            "prefer_emf_blend_modes": False,
            "max_convolve_kernel": 7,
            "max_glow_radius": 8.0,
            "max_glow_alpha": 0.75,
            "preferred_glow_strategy": "inherit",
            "max_filter_primitives": 5,
            "max_filter_complexity": 50,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": True,
            "prefer_rasterization": False,
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
            "max_filter_primitives": 3,
            "max_filter_complexity": 30,
            "native_blur": True,
            "native_shadow": True,
            "approximation_allowed": False,
            "prefer_rasterization": True,
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
            "max_filter_primitives": 2,
            "max_filter_complexity": 20,
            "native_blur": True,
            "native_shadow": False,
            "approximation_allowed": False,
            "prefer_rasterization": True,
        },
    }

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "filter"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = self._normalise_quality(options.get("quality"))
        base = self._extract_target_defaults(options, quality)
        payload = dict(base)
        payload.update(self._copy_direct_overrides(options))
        overrides = self._collect_overrides(options)
        payload.update(overrides)
        payload["strategy"] = self._resolve_strategy(options, payload.get("strategy", base.get("strategy", "auto")))
        return self._coerce_payload(payload, quality)

    def _extract_target_defaults(self, options: Mapping[str, Any], quality: str) -> dict[str, Any]:
        targets = options.get("targets")
        if isinstance(targets, Mapping):
            candidate = targets.get("filter")
            if isinstance(candidate, Mapping):
                return dict(candidate)
        return dict(self._FALLBACKS.get(quality, self._FALLBACKS["balanced"]))

    @staticmethod
    def _normalise_quality(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower()
            if token in FilterPolicyProvider._FALLBACKS:
                return token
        return "balanced"

    def _collect_overrides(self, options: Mapping[str, Any]) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for key, raw in options.items():
            if not isinstance(key, str) or "." not in key:
                continue
            prefix, field = key.split(".", 1)
            if prefix != "filter" or not field:
                continue
            overrides[field] = raw
        return overrides

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
            if token in {"auto", "native", "vector", "emf", "raster"}:
                return token
        overrides = options.get("filter.strategy")
        if isinstance(overrides, str):
            token = overrides.strip().lower()
            if token in {"auto", "native", "vector", "emf", "raster"}:
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
        result["max_filter_primitives"] = self._coerce_int(payload.get("max_filter_primitives"))
        result["max_filter_complexity"] = self._coerce_int(payload.get("max_filter_complexity"))
        result["native_blur"] = self._coerce_bool(payload.get("native_blur"))
        result["native_shadow"] = self._coerce_bool(payload.get("native_shadow"))
        result["approximation_allowed"] = self._coerce_bool(payload.get("approximation_allowed"))
        result["prefer_rasterization"] = self._coerce_bool(payload.get("prefer_rasterization"))
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


__all__ = ["FilterPolicyProvider"]
