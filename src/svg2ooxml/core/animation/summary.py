"""Summary bookkeeping helpers for SMIL animation parsing."""

from __future__ import annotations

from svg2ooxml.ir.animation import AnimationDefinition, AnimationSummary


def update_summary(
    animation_summary: AnimationSummary,
    animation: AnimationDefinition,
) -> None:
    if animation.timing.duration != float("inf"):
        end_time = animation.timing.get_end_time()
        if end_time != float("inf"):
            animation_summary.duration = max(animation_summary.duration, end_time)

    if animation.is_transform_animation():
        animation_summary.has_transforms = True
    if animation.is_motion_animation():
        animation_summary.has_motion_paths = True
    if animation.is_color_animation():
        animation_summary.has_color_animations = True
    if animation.key_splines:
        animation_summary.has_easing = True
    if animation.timing.begin > 0:
        animation_summary.has_sequences = True


def finalize_summary(
    animation_summary: AnimationSummary,
    animations: list[AnimationDefinition],
) -> None:
    animation_summary.total_animations = len(animations)
    animation_summary.element_count = len({anim.element_id for anim in animations})
    animation_summary.calculate_complexity()


def record_degradation(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


__all__ = ["finalize_summary", "record_degradation", "update_summary"]
