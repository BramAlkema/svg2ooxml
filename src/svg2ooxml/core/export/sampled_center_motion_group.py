"""Group/path sampled center-motion builders."""

from __future__ import annotations

from dataclasses import replace as _replace

from svg2ooxml.core.export.animation_predicates import (
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
    _single_matching_member,
)
from svg2ooxml.core.export.motion_geometry import (
    _inverse_project_affine_point,
    _lerp,
    _project_affine_point,
    _resolve_affine_matrix,
    _rotate_point,
    _sample_progress_values,
)
from svg2ooxml.core.export.motion_path_sampling import (
    _build_sampled_motion_replacement,
    _parse_sampled_motion_points,
    _sample_polyline_at_fractions,
)
from svg2ooxml.core.export.sampled_center_motion_parse import (
    _group_transform_clone_origin,
    _interpolate_numeric_keyframes,
    _interpolate_pair_keyframes,
    _parse_rotate_keyframes,
    _parse_translate_pair,
    _rotate_around_point,
)
from svg2ooxml.core.export.sampled_center_motion_types import (
    AnimationMember,
    _SampledCenterMotionComposition,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    CalcMode,
    TransformType,
)


def _build_group_like_center_motion(
    *,
    current_center: tuple[float, float],
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
    translate_rotate = _build_translate_rotate_center_motion(
        current_center=current_center,
        members=members,
    )
    if translate_rotate is not None:
        return translate_rotate
    return _build_motion_rotate_center_motion(
        current_center=current_center,
        members=members,
    )


def _build_translate_rotate_center_motion(
    *,
    current_center: tuple[float, float],
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
    translate_member = _single_matching_member(
        members,
        _is_sampled_translate_animation,
    )
    if translate_member is None:
        return None

    rotate_transform_member = _matching_group_rotate_member(
        members,
        split_origin=_group_transform_clone_origin(translate_member[1]),
    )
    if rotate_transform_member is None:
        return None

    matrix = _resolve_affine_matrix([translate_member[1], rotate_transform_member[1]])
    local_center = _inverse_project_affine_point(current_center, matrix)
    translation_pairs = [
        _parse_translate_pair(value) for value in translate_member[1].values
    ]
    angles, rotation_center = _parse_rotate_keyframes(rotate_transform_member[1])
    if rotation_center is None:
        return None

    ordered_samples = _translate_rotate_samples(
        translate_member[1],
        rotate_transform_member[1],
    )
    center_points: list[tuple[float, float]] = []
    for progress in ordered_samples:
        tx, ty = _interpolate_pair_keyframes(
            translation_pairs,
            translate_member[1].key_times,
            progress,
        )
        angle = _interpolate_numeric_keyframes(
            angles,
            rotate_transform_member[1].key_times,
            progress,
        )
        rotated_center = _rotate_around_point(
            local_center,
            rotation_center,
            angle,
        )
        moved_center = (rotated_center[0] + tx, rotated_center[1] + ty)
        center_points.append(_project_affine_point(moved_center, matrix))

    updated_rotate = _replace(
        rotate_transform_member[1],
        values=[str(angle) for angle in angles],
        element_center_px=None,
    )
    return _SampledCenterMotionComposition(
        replacement_index=translate_member[0],
        consumed_indices={translate_member[0]},
        replacement_animation=_build_sampled_motion_replacement(
            template=translate_member[1],
            points=center_points,
            key_times=ordered_samples,
        ),
        updated_indices={rotate_transform_member[0]: updated_rotate},
        start_center=center_points[0],
        element_id=translate_member[1].element_id,
    )


def _build_motion_rotate_center_motion(
    *,
    current_center: tuple[float, float],
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
    motion_member = _single_matching_member(
        members,
        lambda anim: (
            anim.animation_type == AnimationType.ANIMATE_MOTION
            and _is_simple_motion_sampling_candidate(anim)
        ),
    )
    rotate_member = _single_matching_member(
        members,
        lambda anim: (
            anim.animation_type == AnimationType.ANIMATE_TRANSFORM
            and anim.transform_type == TransformType.ROTATE
            and _is_simple_origin_rotate_animation(anim)
        ),
    )
    if motion_member is None or rotate_member is None:
        return None

    matrix = _resolve_affine_matrix([motion_member[1], rotate_member[1]])
    local_center = _inverse_project_affine_point(current_center, matrix)
    motion_points = _parse_sampled_motion_points(motion_member[1].values[0])
    if len(motion_points) < 2:
        return None

    start_angle, end_angle = _parse_rotate_bounds(rotate_member[1])
    samples = _sample_progress_values()
    motion_samples = _sample_polyline_at_fractions(motion_points, samples)
    center_points = []
    for progress, motion_point in zip(samples, motion_samples, strict=True):
        angle = _lerp(start_angle, end_angle, progress)
        rotated = _rotate_point(
            (local_center[0] + motion_point[0], local_center[1] + motion_point[1]),
            angle,
        )
        center_points.append(_project_affine_point(rotated, matrix))

    return _SampledCenterMotionComposition(
        replacement_index=motion_member[0],
        consumed_indices={motion_member[0]},
        replacement_animation=_build_sampled_motion_replacement(
            template=motion_member[1],
            points=center_points,
            key_times=samples,
        ),
        updated_indices={},
        start_center=center_points[0],
        element_id=motion_member[1].element_id,
    )


def _is_sampled_translate_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE_TRANSFORM
        and animation.transform_type == TransformType.TRANSLATE
        and len(animation.values) >= 2
        and not animation.key_splines
        and _calc_mode_value(animation.calc_mode)
        in {CalcMode.LINEAR.value, CalcMode.PACED.value}
    )


def _matching_group_rotate_member(
    members: list[AnimationMember],
    *,
    split_origin: str | None,
) -> AnimationMember | None:
    rotate_candidates = [
        (index, anim)
        for index, anim in members
        if anim.animation_type == AnimationType.ANIMATE_TRANSFORM
        and anim.transform_type == TransformType.ROTATE
        and len(anim.values) >= 2
        and (
            (
                split_origin is not None
                and _group_transform_clone_origin(anim) == split_origin
            )
            or (
                split_origin is None
                and _group_transform_clone_origin(anim) is None
            )
        )
    ]
    if len(rotate_candidates) == 1:
        return rotate_candidates[0]
    return None


def _translate_rotate_samples(
    translate_animation: AnimationDefinition,
    rotate_animation: AnimationDefinition,
) -> list[float]:
    sample_points = {
        0.0,
        1.0,
        *(_sample_progress_values(24)),
        *(translate_animation.key_times or []),
        *(rotate_animation.key_times or []),
    }
    return sorted(sample_points)


def _calc_mode_value(calc_mode: CalcMode | str) -> str:
    if isinstance(calc_mode, CalcMode):
        return calc_mode.value
    return str(calc_mode).lower()


__all__ = ["_build_group_like_center_motion"]
