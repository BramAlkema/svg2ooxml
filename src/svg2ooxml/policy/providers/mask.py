"""Mask policy provider."""

from __future__ import annotations

from collections.abc import Mapping

from ..engine import PolicyProvider
from ..targets import PolicyTarget


class MaskPolicyProvider(PolicyProvider):
    """Return masking preferences driven by quality settings."""

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "mask"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, object]) -> Mapping[str, object]:
        quality = (options.get("quality") or "balanced").lower()

        if quality == "high":
            policy = {
                "allow_vector_mask": True,
                "fallback_order": ("native", "mimic", "emf", "raster"),
                "force_emf": False,
                "force_raster": False,
                "max_emf_segments": 8000,
                "max_emf_commands": 12000,
                "max_bitmap_area": 1_200_000,
                "max_bitmap_side": 2400,
                "preserve_alpha_precision": True,
            }
        elif quality == "low":
            policy = {
                "allow_vector_mask": False,
                "fallback_order": ("emf", "raster"),
                "force_emf": False,
                "force_raster": False,
                "max_emf_segments": 4000,
                "max_emf_commands": 6000,
                "max_bitmap_area": 250_000,
                "max_bitmap_side": 1024,
                "preserve_alpha_precision": False,
            }
        else:
            policy = {
                "allow_vector_mask": True,
                "fallback_order": ("native", "mimic", "emf", "raster"),
                "force_emf": False,
                "force_raster": False,
                "max_emf_segments": 6000,
                "max_emf_commands": 9000,
                "max_bitmap_area": 500_000,
                "max_bitmap_side": 1536,
                "preserve_alpha_precision": True,
            }

        override_keys = {
            "allow_vector_mask",
            "fallback_order",
            "force_emf",
            "force_raster",
            "max_emf_segments",
            "max_emf_commands",
            "max_bitmap_area",
            "max_bitmap_side",
            "preserve_alpha_precision",
        }
        for key in override_keys:
            if key in options:
                policy[key] = options[key]
        return policy


__all__ = ["MaskPolicyProvider"]
