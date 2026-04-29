"""Geometry policy provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.math_utils import coerce_int, finite_float
from svg2ooxml.policy.engine import PolicyProvider
from svg2ooxml.policy.providers.common import (
    dotted_overrides,
    normalise_quality,
    target_defaults,
)
from svg2ooxml.policy.targets import PolicyTarget


class PathPolicyProvider(PolicyProvider):
    """Return geometry simplification and fallback thresholds."""

    _FALLBACKS: dict[str, Mapping[str, Any]] = {
        "high": {
            "max_segments": 2000,
            "max_complexity_score": 200,
            "max_complexity_ratio": 0.95,
            "max_complexity": 0.95,
            "simplify_paths": False,
            "max_bitmap_area": 2_800_000,
            "max_bitmap_side": 3072,
            "max_dash_segments": 16,
            "max_stroke_width": 100.0,
            "max_miter_limit": 10.0,
            "prefer_dash_presets": True,
            "allow_custom_dash": True,
            "respect_dashoffset": True,
            "min_dash_segment_pct": 0.01,
            "force_emf": False,
            "force_bitmap": False,
            "allow_emf_fallback": True,
            "allow_bitmap_fallback": True,
            "conservative_clipping": False,
        },
        "balanced": {
            "max_segments": 1000,
            "max_complexity_score": 100,
            "max_complexity_ratio": 0.8,
            "max_complexity": 0.8,
            "simplify_paths": True,
            "max_bitmap_area": 1_500_000,
            "max_bitmap_side": 2048,
            "max_dash_segments": 16,
            "max_stroke_width": 100.0,
            "max_miter_limit": 10.0,
            "prefer_dash_presets": True,
            "allow_custom_dash": True,
            "respect_dashoffset": True,
            "min_dash_segment_pct": 0.01,
            "force_emf": False,
            "force_bitmap": False,
            "allow_emf_fallback": True,
            "allow_bitmap_fallback": True,
            "conservative_clipping": False,
        },
        "low": {
            "max_segments": 500,
            "max_complexity_score": 50,
            "max_complexity_ratio": 0.55,
            "max_complexity": 0.55,
            "simplify_paths": True,
            "max_bitmap_area": 600_000,
            "max_bitmap_side": 1536,
            "max_dash_segments": 12,
            "max_stroke_width": 80.0,
            "max_miter_limit": 8.0,
            "prefer_dash_presets": True,
            "allow_custom_dash": True,
            "respect_dashoffset": True,
            "min_dash_segment_pct": 0.015,
            "force_emf": False,
            "force_bitmap": False,
            "allow_emf_fallback": True,
            "allow_bitmap_fallback": True,
            "conservative_clipping": True,
        },
        "compatibility": {
            "max_segments": 300,
            "max_complexity_score": 30,
            "max_complexity_ratio": 0.45,
            "max_complexity": 0.45,
            "simplify_paths": True,
            "max_bitmap_area": 450_000,
            "max_bitmap_side": 1280,
            "max_dash_segments": 10,
            "max_stroke_width": 50.0,
            "max_miter_limit": 4.0,
            "prefer_dash_presets": False,
            "allow_custom_dash": False,
            "respect_dashoffset": True,
            "min_dash_segment_pct": 0.02,
            "force_emf": False,
            "force_bitmap": False,
            "allow_emf_fallback": True,
            "allow_bitmap_fallback": True,
            "conservative_clipping": True,
        },
    }

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "geometry"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = self._normalise_quality(options.get("quality"))
        base = self._extract_target_defaults(options, quality)
        base.update(self._collect_overrides(options))
        return self._coerce_payload(base, quality)

    def _extract_target_defaults(self, options: Mapping[str, Any], quality: str) -> dict[str, Any]:
        payload = target_defaults(
            options,
            target_name="geometry",
            quality=quality,
            fallbacks=self._FALLBACKS,
        )
        if "max_complexity" not in payload and "max_complexity_ratio" in payload:
            payload["max_complexity"] = payload["max_complexity_ratio"]
        return payload

    @staticmethod
    def _normalise_quality(value: Any) -> str:
        return normalise_quality(value, PathPolicyProvider._FALLBACKS)

    def _collect_overrides(self, options: Mapping[str, Any]) -> dict[str, Any]:
        return dotted_overrides(options, prefix="geometry")

    def _coerce_payload(self, payload: Mapping[str, Any], quality: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "quality": quality,
        }
        for key, value in payload.items():
            if key in {"simplify_paths", "force_emf", "force_bitmap", "allow_emf_fallback", "allow_bitmap_fallback", "conservative_clipping", "prefer_dash_presets", "allow_custom_dash", "respect_dashoffset"}:
                result[key] = bool(value)
            elif key in {"max_segments", "max_dash_segments", "max_bitmap_side"}:
                result[key] = self._coerce_int(value)
            elif key in {"max_complexity", "max_complexity_ratio", "min_dash_segment_pct"}:
                result[key] = self._coerce_float(value)
            elif key in {"max_bitmap_area"}:
                result[key] = self._coerce_int(value)
            elif key in {"max_stroke_width", "max_miter_limit"}:
                result[key] = self._coerce_float(value)
            elif key == "max_complexity_score":
                result[key] = self._coerce_int(value)
            else:
                result[key] = value
        # keep legacy key for downstream helpers
        if "max_complexity_ratio" in result and "max_complexity" not in result:
            result["max_complexity"] = result["max_complexity_ratio"]
        return result

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        return coerce_int(value)

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        return finite_float(value)


__all__ = ["PathPolicyProvider"]
