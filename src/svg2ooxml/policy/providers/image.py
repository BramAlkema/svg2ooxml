"""Image policy provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.policy.engine import PolicyProvider
from svg2ooxml.policy.targets import PolicyTarget


class ImagePolicyProvider(PolicyProvider):
    """Return image optimisation preferences derived from policy profiles."""

    _FALLBACKS: dict[str, Mapping[str, Any]] = {
        "high": {
            "colorspace_normalization": "perceptual",
            "prefer_vector": True,
            "max_downscale": 0.75,
            "max_inline_size_kib": 8192,
            "max_external_size_kib": 12288,
            "raster_resize_threshold": 4096,
            "max_pixels": 16_000_000,
            "preprocess_svg": True,
            "embed_external": True,
            "allow_svg_image": True,
        },
        "balanced": {
            "colorspace_normalization": "rgb",
            "prefer_vector": True,
            "max_downscale": 0.5,
            "max_inline_size_kib": 4096,
            "max_external_size_kib": 8192,
            "raster_resize_threshold": 3072,
            "max_pixels": 9_000_000,
            "preprocess_svg": True,
            "embed_external": True,
            "allow_svg_image": True,
        },
        "low": {
            "colorspace_normalization": "skip",
            "prefer_vector": False,
            "max_downscale": 0.3,
            "max_inline_size_kib": 2048,
            "max_external_size_kib": 4096,
            "raster_resize_threshold": 2048,
            "max_pixels": 5_000_000,
            "preprocess_svg": True,
            "embed_external": False,
            "allow_svg_image": True,
        },
        "compatibility": {
            "colorspace_normalization": "skip",
            "prefer_vector": False,
            "max_downscale": 0.2,
            "max_inline_size_kib": 1536,
            "max_external_size_kib": 3072,
            "raster_resize_threshold": 1536,
            "max_pixels": 4_000_000,
            "preprocess_svg": True,
            "embed_external": False,
            "allow_svg_image": False,
        },
    }

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "image"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = self._normalise_quality(options.get("quality"))
        base = self._extract_target_defaults(options, quality)

        payload = {
            "quality": quality,
            **base,
        }
        payload.update(self._collect_overrides(options))
        return payload


    def _extract_target_defaults(self, options: Mapping[str, Any], quality: str) -> dict[str, Any]:
        targets = options.get("targets")
        if isinstance(targets, Mapping):
            candidate = targets.get("image")
            if isinstance(candidate, Mapping):
                return dict(candidate)
        return dict(self._FALLBACKS.get(quality, self._FALLBACKS["balanced"]))

    @staticmethod
    def _normalise_quality(value: Any) -> str:
        if isinstance(value, str) and value:
            token = value.strip().lower()
            if token in ImagePolicyProvider._FALLBACKS:
                return token
        return "balanced"

    def _collect_overrides(self, options: Mapping[str, Any]) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for key, raw in options.items():
            if not isinstance(key, str) or "." not in key:
                continue
            prefix, field = key.split(".", 1)
            if prefix != "image" or not field:
                continue
            overrides[field] = self._coerce(field, raw)
        return overrides

    def _coerce(self, field: str, value: Any) -> Any:
        if field in {
            "prefer_vector",
            "preprocess_svg",
            "embed_external",
            "allow_svg_image",
        }:
            return bool(value)
        if field in {
            "max_inline_size_kib",
            "max_external_size_kib",
            "raster_resize_threshold",
        }:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if field in {"max_pixels"}:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if field == "max_downscale":
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.5
        if field == "colorspace_normalization":
            if isinstance(value, str) and value:
                return value.strip().lower()
        return value


__all__ = ["ImagePolicyProvider"]
