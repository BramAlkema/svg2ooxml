"""Animation policy provider controlling native vs fallback behaviour."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..engine import PolicyProvider
from ..targets import PolicyTarget

_FALLBACK_OPTIONS = {"native", "slide", "raster"}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "on"}:
        return True
    if value_str in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_fallback(value: Any, default: str) -> str:
    if value is None:
        return default
    candidate = str(value).strip().lower()
    if candidate in _FALLBACK_OPTIONS:
        return candidate
    return default


class AnimationPolicyProvider(PolicyProvider):
    """Provide animation policy defaults derived from quality settings."""

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "animation"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = str(options.get("quality", "balanced")).lower()

        if quality == "low":
            allow_native = False
            fallback_mode = "slide"
            max_error = 0.0
        elif quality == "high":
            allow_native = True
            fallback_mode = "native"
            max_error = 0.25
        else:
            allow_native = True
            fallback_mode = "native"
            max_error = 0.35

        allow_native = _coerce_bool(options.get("animation_allow_native_splines"), allow_native)
        fallback_mode = _normalize_fallback(options.get("animation_fallback_mode"), fallback_mode)
        max_error = max(0.0, _coerce_float(options.get("animation_max_spline_error"), max_error))

        return {
            "allow_native_splines": allow_native,
            "fallback_mode": fallback_mode,
            "max_spline_error": max_error,
        }


__all__ = ["AnimationPolicyProvider"]
