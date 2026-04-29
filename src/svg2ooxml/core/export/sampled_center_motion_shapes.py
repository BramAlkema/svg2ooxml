"""Shape-specific sampled center-motion builders."""

from __future__ import annotations

from dataclasses import replace as _replace

from svg2ooxml.core.export.animation_predicates import (
    _is_simple_linear_numeric_animation,
    _is_simple_linear_two_value_animation,
    _single_matching_member,
)
from svg2ooxml.core.export.motion_geometry import (
    _image_local_layout,
    _inverse_project_affine_point,
    _inverse_project_affine_rect,
    _lerp,
    _project_affine_point,
    _resolve_affine_matrix,
    _sample_progress_values,
)
from svg2ooxml.core.export.motion_path_sampling import (
    _build_sampled_motion_replacement,
)
from svg2ooxml.core.export.sampled_center_motion_parse import (
    _numeric_bounds,
    _parse_scale_bounds,
)
from svg2ooxml.core.export.sampled_center_motion_types import (
    AnimationMember,
    _SampledCenterMotionComposition,
)
from svg2ooxml.ir.animation import (
    AnimationType,
    TransformType,
)


def _build_circle_scale_center_motion(
    *,
    current_center: tuple[float, float],
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
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

    numeric_members = _linear_numeric_members(members, {"x", "y", "cx", "cy"})
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

    x0, x1 = _numeric_bounds(numeric_members.get("x"), axis="x", default=0.0)
    y0, y1 = _numeric_bounds(numeric_members.get("y"), axis="y", default=0.0)
    cx0, cx1 = _numeric_bounds(
        numeric_members.get("cx"),
        axis="x",
        default=local_center_x,
    )
    cy0, cy1 = _numeric_bounds(
        numeric_members.get("cy"),
        axis="y",
        default=local_center_y,
    )

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
    return _SampledCenterMotionComposition(
        replacement_index=replacement_index,
        consumed_indices=consumed_indices,
        replacement_animation=_build_sampled_motion_replacement(
            template=motion_template,
            points=center_points,
            key_times=samples,
        ),
        updated_indices={scale_member[0]: updated_scale},
        start_center=center_points[0],
        element_id=motion_template.element_id,
    )


def _build_image_scale_center_motion(
    *,
    element: object,
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
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

    numeric_members = _linear_numeric_members(members, {"x", "y"})
    if not numeric_members:
        return None

    matrix = _resolve_affine_matrix(
        [scale_member[1], *(anim for _, anim in numeric_members.values())]
    )
    local_bbox = _inverse_project_affine_rect(element.bbox, matrix)
    viewport_rect, content_rect = _image_local_layout(element, local_bbox)
    (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

    x0, x1 = _numeric_bounds(
        numeric_members.get("x"),
        axis="x",
        default=viewport_rect.x,
    )
    y0, y1 = _numeric_bounds(
        numeric_members.get("y"),
        axis="y",
        default=viewport_rect.y,
    )
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
    return _SampledCenterMotionComposition(
        replacement_index=replacement_index,
        consumed_indices=consumed_indices,
        replacement_animation=_build_sampled_motion_replacement(
            template=motion_template,
            points=center_points,
            key_times=samples,
        ),
        updated_indices={scale_member[0]: updated_scale},
        start_center=center_points[0],
        element_id=motion_template.element_id,
    )


def _linear_numeric_members(
    members: list[AnimationMember],
    target_attributes: set[str],
) -> dict[str, AnimationMember]:
    return {
        anim.target_attribute: (index, anim)
        for index, anim in members
        if _is_simple_linear_numeric_animation(anim)
        and anim.target_attribute in target_attributes
    }


__all__ = [
    "_build_circle_scale_center_motion",
    "_build_image_scale_center_motion",
]
