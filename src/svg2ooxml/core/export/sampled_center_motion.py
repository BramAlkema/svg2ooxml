"""Sampled center-motion composition and animation grouping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from svg2ooxml.core.export.animation_predicates import (
    _is_simple_linear_numeric_animation,
    _is_simple_linear_two_value_animation,
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
    _sampled_motion_group_key,
    _single_matching_member,
)
from svg2ooxml.core.export.element_translation import (
    _translate_element_to_center_target,
)
from svg2ooxml.core.export.motion_geometry import (
    _image_local_layout,
    _inverse_project_affine_point,
    _inverse_project_affine_rect,
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
from svg2ooxml.core.export.scene_index import _build_scene_element_index
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    CalcMode,
    TransformType,
)

# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_scale_bounds(
    animation: AnimationDefinition,
) -> tuple[tuple[float, float], tuple[float, float]]:
    from svg2ooxml.common.conversions.transforms import parse_scale_pair

    return (
        parse_scale_pair(animation.values[0]),
        parse_scale_pair(animation.values[-1]),
    )


def _parse_rotate_keyframes(
    animation: AnimationDefinition,
) -> tuple[list[float], tuple[float, float] | None]:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    angles: list[float] = []
    center: tuple[float, float] | None = None
    for value in animation.values:
        numbers = parse_numeric_list(value)
        if numbers:
            angles.append(numbers[0])
        else:
            angles.append(0.0)
        if len(numbers) >= 3:
            parsed_center = (numbers[1], numbers[2])
            if center is None:
                center = parsed_center
            elif (
                abs(center[0] - parsed_center[0]) > 1e-6
                or abs(center[1] - parsed_center[1]) > 1e-6
            ):
                return (angles, center)
    return (angles, center)


def _interpolate_numeric_keyframes(
    values: list[float],
    key_times: list[float] | None,
    fraction: float,
) -> float:
    if not values:
        return 0.0
    if len(values) == 1 or fraction <= 0.0:
        return values[0]
    if fraction >= 1.0:
        return values[-1]

    if key_times and len(key_times) == len(values):
        for index in range(len(key_times) - 1):
            if fraction <= key_times[index + 1]:
                span = max(1e-9, key_times[index + 1] - key_times[index])
                local_t = (fraction - key_times[index]) / span
                return _lerp(values[index], values[index + 1], local_t)
        return values[-1]

    position = fraction * (len(values) - 1)
    index = min(int(position), len(values) - 2)
    local_t = position - index
    return _lerp(values[index], values[index + 1], local_t)


def _interpolate_pair_keyframes(
    values: list[tuple[float, float]],
    key_times: list[float] | None,
    fraction: float,
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    xs = [pair[0] for pair in values]
    ys = [pair[1] for pair in values]
    return (
        _interpolate_numeric_keyframes(xs, key_times, fraction),
        _interpolate_numeric_keyframes(ys, key_times, fraction),
    )


def _rotate_around_point(
    point: tuple[float, float],
    center: tuple[float, float],
    angle_deg: float,
) -> tuple[float, float]:
    local_x = point[0] - center[0]
    local_y = point[1] - center[1]
    rotated_x, rotated_y = _rotate_point((local_x, local_y), angle_deg)
    return (center[0] + rotated_x, center[1] + rotated_y)


def _numeric_bounds(
    member: tuple[int, AnimationDefinition] | None,
    *,
    default: float,
) -> tuple[float, float]:
    if member is None:
        return (default, default)
    try:
        return (float(member[1].values[0]), float(member[1].values[-1]))
    except (TypeError, ValueError):
        return (default, default)


def _parse_translate_pair(value: str) -> tuple[float, float]:
    from svg2ooxml.common.conversions.transforms import parse_translation_pair

    return parse_translation_pair(value)


def _group_transform_clone_origin(animation: AnimationDefinition) -> str | None:
    for key in (
        "svg2ooxml_group_transform_split",
        "svg2ooxml_group_transform_expanded",
    ):
        origin = animation.raw_attributes.get(key)
        if isinstance(origin, str) and origin:
            return origin
    return None




# ---------------------------------------------------------------------------
# Sampled center motion composition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SampledCenterMotionComposition:
    replacement_index: int
    consumed_indices: set[int]
    replacement_animation: AnimationDefinition
    updated_indices: dict[int, AnimationDefinition]
    start_center: tuple[float, float]
    element_id: str


def _compose_sampled_center_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose known stacked transform/motion cases into sampled center paths.

    Some SVG stacks change the shape center in ways PowerPoint cannot infer by
    simply combining independent native effects. For those cases we:

    1. move the base IR element to the authored SVG start center
    2. replace the position-changing fragments with one sampled motion path
    3. keep the editable scale/rotate effect, but suppress its naive companion
       motion because the composed path already includes that center movement
    """
    scene_index = _build_scene_element_index(scene)
    alias_map = scene_index.alias_map
    element_map = scene_index.element_map
    center_map = scene_index.center_map

    group_map: dict[tuple[Any, ...], list[tuple[int, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        group_key = _sampled_motion_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, animation))

    compositions: list[_SampledCenterMotionComposition] = []
    for members in group_map.values():
        base_animation = min(members, key=lambda item: item[0])[1]
        element = element_map.get(base_animation.element_id)
        current_center = center_map.get(base_animation.element_id)
        if element is None or current_center is None:
            continue

        composition = _build_sampled_center_motion_composition(
            element=element,
            current_center=current_center,
            members=members,
        )
        if composition is not None:
            compositions.append(composition)

    if not compositions:
        return animations

    center_targets = {
        composition.element_id: composition.start_center
        for composition in compositions
    }
    scene.elements = [
        _translate_element_to_center_target(element, center_targets)
        for element in scene.elements
    ]

    replacements = {
        composition.replacement_index: composition
        for composition in compositions
    }
    updated_indices: dict[int, AnimationDefinition] = {}
    consumed_indices: set[int] = set()
    for composition in compositions:
        updated_indices.update(composition.updated_indices)
        consumed_indices.update(composition.consumed_indices)

    composed: list[AnimationDefinition] = []
    for index, animation in enumerate(animations):
        if index in replacements:
            composed.append(replacements[index].replacement_animation)
        if index in consumed_indices:
            continue
        composed.append(updated_indices.get(index, animation))
    return composed


def _build_sampled_center_motion_composition(
    *,
    element: object,
    current_center: tuple[float, float],
    members: list[tuple[int, AnimationDefinition]],
) -> _SampledCenterMotionComposition | None:
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Polygon, Polyline

    if isinstance(element, Circle):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y", "cx", "cy"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_center_x, local_center_y = _inverse_project_affine_point(
            current_center,
            matrix,
        )
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=0.0)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=0.0)
        cx0, cx1 = _numeric_bounds(numeric_members.get("cx"), default=local_center_x)
        cy0, cy1 = _numeric_bounds(numeric_members.get("cy"), default=local_center_y)

        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            tx = _lerp(x0, x1, progress)
            ty = _lerp(y0, y1, progress)
            cx = _lerp(cx0, cx1, progress)
            cy = _lerp(cy0, cy1, progress)
            center_points.append(
                _project_affine_point(
                    (tx + sx * cx, ty + sy * cy),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
                key_times=samples,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, Image):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_bbox = _inverse_project_affine_rect(element.bbox, matrix)
        viewport_rect, content_rect = _image_local_layout(element, local_bbox)
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=viewport_rect.x)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=viewport_rect.y)
        content_offset_x = float(content_rect.x - viewport_rect.x)
        content_offset_y = float(content_rect.y - viewport_rect.y)
        width = float(content_rect.width)
        height = float(content_rect.height)

        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            x = _lerp(x0, x1, progress)
            y = _lerp(y0, y1, progress)
            center_points.append(
                _project_affine_point(
                    (
                        sx * (x + content_offset_x + width / 2.0),
                        sy * (y + content_offset_y + height / 2.0),
                    ),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
                key_times=samples,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, (Group, IRPath, Polyline, Polygon)):
        translate_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.TRANSLATE
                and len(anim.values) >= 2
                and not anim.key_splines
                and (
                    (
                        anim.calc_mode.value
                        if isinstance(anim.calc_mode, CalcMode)
                        else str(anim.calc_mode).lower()
                    )
                    in {CalcMode.LINEAR.value, CalcMode.PACED.value}
                )
            ),
        )
        rotate_transform_member = None
        if translate_member is not None:
            split_origin = _group_transform_clone_origin(translate_member[1])
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
                rotate_transform_member = rotate_candidates[0]
        if translate_member is not None and rotate_transform_member is not None:
            matrix = _resolve_affine_matrix([translate_member[1], rotate_transform_member[1]])
            local_center = _inverse_project_affine_point(current_center, matrix)
            translation_pairs = [
                _parse_translate_pair(value) for value in translate_member[1].values
            ]
            angles, rotation_center = _parse_rotate_keyframes(rotate_transform_member[1])
            if rotation_center is not None:
                sample_points = {
                    0.0,
                    1.0,
                    *(_sample_progress_values(24)),
                    *(translate_member[1].key_times or []),
                    *(rotate_transform_member[1].key_times or []),
                }
                ordered_samples = sorted(sample_points)
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
                    center_points.append(
                        _project_affine_point(moved_center, matrix)
                    )

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

    return None
