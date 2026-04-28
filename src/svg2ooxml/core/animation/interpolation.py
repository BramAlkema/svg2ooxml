"""Interpolation input normalization for SMIL animation parsing."""

from __future__ import annotations

from collections.abc import Callable

from svg2ooxml.ir.animation import AnimationSummary, AnimationType, CalcMode


def sanitize_interpolation_inputs(
    *,
    animation_type: AnimationType,
    values: list[str],
    calc_mode: CalcMode,
    key_times: list[float] | None,
    key_points: list[float] | None,
    key_splines: list[list[float]] | None,
    animation_summary: AnimationSummary,
    record_degradation: Callable[[str], None],
) -> tuple[list[float] | None, list[float] | None, list[list[float]] | None]:
    """Normalize keyTimes/keySplines combinations to avoid hard parse drops."""
    is_motion_with_path = animation_type == AnimationType.ANIMATE_MOTION and len(values) == 1
    if key_times is not None:
        if is_motion_with_path:
            if len(key_times) < 2:
                animation_summary.add_warning(
                    "Ignoring keyTimes for animateMotion: expected at least 2 entries"
                )
                record_degradation("motion_key_times_too_short")
                key_times = None
        elif len(key_times) != len(values):
            animation_summary.add_warning(
                f"keyTimes length mismatch: expected {len(values)}, got {len(key_times)}"
            )
            record_degradation("key_times_length_mismatch")
            key_times = None

    if key_points is not None:
        if animation_type != AnimationType.ANIMATE_MOTION:
            animation_summary.add_warning(
                "Ignoring keyPoints because animation is not animateMotion"
            )
            record_degradation("key_points_non_motion")
            key_points = None
        elif key_times is not None and len(key_points) != len(key_times):
            animation_summary.add_warning(
                f"keyPoints length mismatch: expected {len(key_times)}, got {len(key_points)}"
            )
            record_degradation("key_points_length_mismatch")
            key_points = None

    if key_splines is not None and calc_mode != CalcMode.SPLINE:
        animation_summary.add_warning("Ignoring keySplines because calcMode is not spline")
        record_degradation("key_splines_non_spline_mode")
        key_splines = None

    if (
        is_motion_with_path
        and key_splines is not None
        and key_times is None
        and len(key_splines) > 0
    ):
        # SVG stores animateMotion values as one path in this IR. For spline timing,
        # synthesize the SMIL segment clock so path keySplines are still retained.
        key_times = [index / len(key_splines) for index in range(len(key_splines) + 1)]

    if key_splines is not None:
        if is_motion_with_path and key_times is not None:
            expected_splines = max(len(key_times) - 1, 0)
        else:
            expected_splines = max(len(values) - 1, 0)
        if len(key_splines) != expected_splines:
            animation_summary.add_warning(
                f"keySplines length mismatch: expected {expected_splines}, got {len(key_splines)}"
            )
            record_degradation("key_splines_length_mismatch")
            key_splines = None

    if (
        calc_mode == CalcMode.SPLINE
        and key_splines
        and key_times is None
        and len(values) > 1
        and not is_motion_with_path
    ):
        # SMIL expects keyTimes with spline timing; synthesize even spacing for robustness.
        key_times = [index / (len(values) - 1) for index in range(len(values))]

    return key_times, key_points, key_splines


__all__ = ["sanitize_interpolation_inputs"]
