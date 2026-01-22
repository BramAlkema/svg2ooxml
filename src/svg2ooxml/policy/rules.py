"""Policy presets derived from svg2pptx configuration.

The svg2pptx policy layer exposes quality-focused profiles that balance fidelity
and performance.  This module mirrors the canonical presets so other packages
can rely on consistent thresholds while the remainder of the port lands.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Policy:
    """Simple bag of policy flags."""

    name: str
    options: Mapping[str, Any]


def _merge(base: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(base)
    if overrides:
        payload.update(overrides)
    return payload


_BASE_THRESHOLDS: dict[str, Any] = {
    "max_path_segments": 1000,
    "max_path_complexity_score": 100,
    "max_bezier_control_distance": 1000.0,
    "max_text_runs": 20,
    "max_text_complexity_score": 15,
    "min_font_size_pt": 6.0,
    "enable_font_embedding": True,
    "enable_system_font_fallback": True,
    "enable_text_to_path": True,
    "min_font_match_confidence": 0.7,
    "prefer_font_embedding": True,
    "max_font_file_size_mb": 2.0,
    "max_stroke_width": 100.0,
    "max_miter_limit": 10.0,
    "max_dash_segments": 16,
    "prefer_dash_presets": True,
    "allow_custom_dash": True,
    "respect_dashoffset": True,
    "min_dash_segment_pct": 0.01,
    "max_group_elements": 500,
    "max_nesting_depth": 20,
    "max_gradient_stops": 10,
    "max_gradient_transform_complexity": 5.0,
    "enable_gradient_simplification": True,
    "max_mesh_patches": 100,
    "max_mesh_grid_size": 10,
    "prefer_linear_over_radial": False,
    "enable_color_space_conversion": True,
    "max_processing_time_ms": 100.0,
    "max_memory_usage_mb": 50.0,
    "max_skew_angle_deg": 18.0,
    "max_scale_ratio": 5.0,
    "max_rotation_deviation_deg": 5.0,
    "max_filter_primitives": 5,
    "enable_native_blur": True,
    "enable_native_shadow": True,
    "enable_filter_approximation": True,
    "max_filter_complexity_score": 50,
    "prefer_filter_rasterization": False,
    "max_single_page_size_kb": 500,
    "min_elements_per_page": 3,
    "enable_auto_page_detection": True,
    "prefer_explicit_markers": True,
    "max_pages_per_conversion": 50,
    "enable_size_based_splitting": True,
    "page_detection_heuristic": "balanced",
    "max_animation_keyframes": 20,
    "max_animation_duration_ms": 10_000.0,
    "enable_animation_conversion": True,
    "enable_video_export": False,
    "max_simultaneous_animations": 5,
    "prefer_entrance_effects": True,
    "max_clip_path_segments": 100,
    "max_clip_nesting_depth": 3,
    "enable_native_clipping": True,
    "enable_boolean_operations": False,
    "prefer_rect_clips": True,
}

_BASE_FLAGS: dict[str, Any] = {
    "enable_path_optimization": True,
    "enable_text_optimization": True,
    "enable_group_flattening": True,
    "enable_gradient_simplification": True,
    "enable_clip_boolean_ops": True,
    "enable_wordart_classification": True,
    "conservative_clipping": False,
    "conservative_gradients": False,
    "conservative_text": False,
    "enable_metrics": True,
    "log_decisions": False,
}

_BASE_CLIP_POLICY: dict[str, Any] = {
    "enable_structured_adapter": True,
    "max_segments_for_custgeom": _BASE_THRESHOLDS["max_clip_path_segments"],
    "prefer_bbox_clipping": True,
}

_BASE_GEOMETRY: dict[str, Any] = {
    "geometry_mode": "resvg",  # "legacy" | "resvg" - controls geometry/paint extraction engine
    "max_segments": _BASE_THRESHOLDS["max_path_segments"],
    "max_complexity_score": _BASE_THRESHOLDS["max_path_complexity_score"],
    "max_complexity_ratio": 0.8,
    "simplify_paths": True,
    "max_bitmap_area": 1_500_000,
    "max_bitmap_side": 2048,
    "max_dash_segments": _BASE_THRESHOLDS["max_dash_segments"],
    "max_stroke_width": _BASE_THRESHOLDS["max_stroke_width"],
    "max_miter_limit": _BASE_THRESHOLDS["max_miter_limit"],
    "prefer_dash_presets": _BASE_THRESHOLDS["prefer_dash_presets"],
    "allow_custom_dash": _BASE_THRESHOLDS["allow_custom_dash"],
    "respect_dashoffset": _BASE_THRESHOLDS["respect_dashoffset"],
    "min_dash_segment_pct": _BASE_THRESHOLDS["min_dash_segment_pct"],
    "force_emf": False,
    "force_bitmap": False,
    "allow_emf_fallback": True,
    "allow_bitmap_fallback": True,
    "conservative_clipping": False,
}

_BASE_FILTER: dict[str, Any] = {
    "strategy": "auto",
    "allow_anisotropic_native": True,
    "max_bitmap_stddev": 64.0,
    "max_shadow_distance": 80.0,
    "prefer_emf_blend_modes": False,
    "max_convolve_kernel": 7,
    "max_glow_radius": 12.0,
    "max_glow_alpha": 0.85,
    "preferred_glow_strategy": "inherit",
    "blur_strategy": "soft_edge",
    "max_filter_primitives": _BASE_THRESHOLDS["max_filter_primitives"],
    "max_filter_complexity": _BASE_THRESHOLDS["max_filter_complexity_score"],
    "native_blur": _BASE_THRESHOLDS["enable_native_blur"],
    "native_shadow": _BASE_THRESHOLDS["enable_native_shadow"],
    "approximation_allowed": _BASE_THRESHOLDS["enable_filter_approximation"],
    "prefer_rasterization": _BASE_THRESHOLDS["prefer_filter_rasterization"],
}

_BASE_IMAGE: dict[str, Any] = {
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
}


def _policy_template(
    *,
    name: str,
    quality: str,
    threshold_overrides: Mapping[str, Any] | None = None,
    flag_overrides: Mapping[str, Any] | None = None,
    clip_overrides: Mapping[str, Any] | None = None,
    geometry_overrides: Mapping[str, Any] | None = None,
    filter_overrides: Mapping[str, Any] | None = None,
    image_overrides: Mapping[str, Any] | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = _merge(_BASE_THRESHOLDS, threshold_overrides)
    flags = _merge(_BASE_FLAGS, flag_overrides)
    clip_policy = _merge(_BASE_CLIP_POLICY, clip_overrides)
    targets = {
        "geometry": _merge(_BASE_GEOMETRY, geometry_overrides),
        "filter": _merge(_BASE_FILTER, filter_overrides),
        "image": _merge(_BASE_IMAGE, image_overrides),
    }

    payload: dict[str, Any] = {
        "quality": quality,
        "profile": name,
        "thresholds": thresholds,
        "flags": flags,
        "clip_policy": clip_policy,
        "targets": targets,
    }
    if extras:
        payload.update(extras)
    return payload


_HIGH_OPTIONS = _policy_template(
    name="quality",
    quality="high",
    threshold_overrides={
        "max_path_segments": 2000,
        "max_path_complexity_score": 200,
        "max_text_runs": 50,
        "max_text_complexity_score": 30,
        "max_group_elements": 1000,
        "max_gradient_stops": 20,
    },
    geometry_overrides={
        "max_segments": 2000,
        "max_complexity_score": 200,
        "max_complexity_ratio": 0.95,
        "simplify_paths": False,
        "max_bitmap_area": 2_800_000,
        "max_bitmap_side": 3072,
    },
    filter_overrides={
        "strategy": "native",
        "max_bitmap_stddev": 96.0,
        "max_shadow_distance": 120.0,
        "max_convolve_kernel": 9,
        "max_glow_radius": 16.0,
        "max_glow_alpha": 0.95,
        "preferred_glow_strategy": "source",
        "max_filter_primitives": 7,
        "max_filter_complexity": 80,
        "allow_anisotropic_native": True,
        "approximation_allowed": True,
    },
    image_overrides={
        "colorspace_normalization": "perceptual",
        "max_downscale": 0.75,
        "max_inline_size_kib": 8192,
        "max_external_size_kib": 12288,
        "raster_resize_threshold": 4096,
        "max_pixels": 16_000_000,
    },
)

_BALANCED_OPTIONS = _policy_template(
    name="balanced",
    quality="balanced",
)

_LOW_OPTIONS = _policy_template(
    name="speed",
    quality="low",
    threshold_overrides={
        "max_path_segments": 500,
        "max_path_complexity_score": 50,
        "max_text_runs": 10,
        "max_text_complexity_score": 8,
        "max_group_elements": 200,
        "max_gradient_stops": 5,
    },
    flag_overrides={
        "conservative_clipping": True,
        "conservative_gradients": True,
        "conservative_text": True,
    },
    clip_overrides={"max_segments_for_custgeom": 60},
    geometry_overrides={
        "max_segments": 500,
        "max_complexity_score": 50,
        "max_complexity_ratio": 0.55,
        "simplify_paths": True,
        "max_bitmap_area": 600_000,
        "max_bitmap_side": 1536,
        "conservative_clipping": True,
    },
    filter_overrides={
        "strategy": "raster",
        "allow_anisotropic_native": False,
        "max_bitmap_stddev": 32.0,
        "max_shadow_distance": 40.0,
        "max_convolve_kernel": 5,
        "max_glow_radius": 8.0,
        "max_glow_alpha": 0.7,
        "preferred_glow_strategy": "flood",
        "max_filter_primitives": 3,
        "max_filter_complexity": 30,
        "approximation_allowed": False,
        "prefer_rasterization": True,
    },
    image_overrides={
        "colorspace_normalization": "skip",
        "prefer_vector": False,
        "max_downscale": 0.3,
        "max_inline_size_kib": 2048,
        "max_external_size_kib": 4096,
        "raster_resize_threshold": 2048,
        "embed_external": False,
        "max_pixels": 5_000_000,
    },
)

_COMPATIBILITY_OPTIONS = _policy_template(
    name="compatibility",
    quality="compatibility",
    threshold_overrides={
        "max_path_segments": 300,
        "max_path_complexity_score": 30,
        "max_text_runs": 5,
        "max_text_complexity_score": 5,
        "max_group_elements": 100,
        "max_gradient_stops": 3,
        "max_stroke_width": 50.0,
        "max_miter_limit": 4.0,
    },
    flag_overrides={
        "conservative_clipping": True,
        "conservative_gradients": True,
        "conservative_text": True,
        "enable_clip_boolean_ops": False,
    },
    clip_overrides={
        "max_segments_for_custgeom": 40,
        "prefer_bbox_clipping": True,
    },
    geometry_overrides={
        "max_segments": 300,
        "max_complexity_score": 30,
        "max_complexity_ratio": 0.45,
        "simplify_paths": True,
        "max_bitmap_area": 450_000,
        "max_bitmap_side": 1280,
        "conservative_clipping": True,
        "allow_custom_dash": False,
    },
    filter_overrides={
        "strategy": "emf",
        "allow_anisotropic_native": False,
        "max_bitmap_stddev": 28.0,
        "max_shadow_distance": 30.0,
        "max_convolve_kernel": 3,
        "max_glow_radius": 6.0,
        "max_glow_alpha": 0.6,
        "preferred_glow_strategy": "flood",
        "max_filter_primitives": 2,
        "max_filter_complexity": 20,
        "approximation_allowed": False,
        "prefer_rasterization": True,
    },
    image_overrides={
        "colorspace_normalization": "skip",
        "prefer_vector": False,
        "max_downscale": 0.2,
        "max_inline_size_kib": 1536,
        "max_external_size_kib": 3072,
        "raster_resize_threshold": 1536,
        "embed_external": False,
        "allow_svg_image": False,
        "max_pixels": 4_000_000,
    },
)

_HIGH_OPTIONS.update(
    {
        "animation_allow_native_splines": "true",
        "animation_fallback_mode": "native",
        "animation_max_spline_error": "0.25",
    }
)
_BALANCED_OPTIONS.update(
    {
        "animation_allow_native_splines": "true",
        "animation_fallback_mode": "native",
        "animation_max_spline_error": "0.35",
    }
)
_LOW_OPTIONS.update(
    {
        "animation_allow_native_splines": "false",
        "animation_fallback_mode": "slide",
        "animation_max_spline_error": "0.0",
    }
)
_COMPATIBILITY_OPTIONS.update(
    {
        "animation_allow_native_splines": "false",
        "animation_fallback_mode": "slide",
        "animation_max_spline_error": "0.05",
    }
)


POLICY_PRESETS: dict[str, Mapping[str, Any]] = {
    "balanced": _BALANCED_OPTIONS,
    "high": _HIGH_OPTIONS,
    "low": _LOW_OPTIONS,
    "compatibility": _COMPATIBILITY_OPTIONS,
}

_ALIASES: dict[str, str] = {
    "default": "balanced",
    "basic": "balanced",
    "balanced": "balanced",
    "quality": "high",
    "high": "high",
    "speed": "low",
    "low": "low",
    "draft": "low",
    "compatibility": "compatibility",
}

DEFAULT_POLICY = Policy(name="balanced", options=deepcopy(_BALANCED_OPTIONS))


def load_policy(name: str = "basic") -> Policy:
    """Return a policy profile by name."""
    normalized = (name or "balanced").strip().lower()
    canonical = _ALIASES.get(normalized, normalized)
    options = POLICY_PRESETS.get(canonical)

    if options is None:
        # Unknown profiles fall back to balanced settings but keep the requested name.
        return Policy(
            name=normalized,
            options=_merge(
                DEFAULT_POLICY.options,
                {"quality": normalized, "profile": normalized},
            ),
        )

    if canonical == "balanced" and normalized in {"basic", "balanced", "default"}:
        return DEFAULT_POLICY

    policy_name = normalized if normalized in POLICY_PRESETS else canonical
    return Policy(name=policy_name, options=deepcopy(options))


__all__ = ["Policy", "DEFAULT_POLICY", "POLICY_PRESETS", "load_policy"]
