"""Parse and interpolation helpers for sampled center-motion composition."""

from __future__ import annotations

from svg2ooxml.core.export.animation_values import animation_length_bounds_or_default
from svg2ooxml.core.export.motion_geometry import _lerp, _rotate_point
from svg2ooxml.ir.animation import AnimationDefinition


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
    axis: str,
    default: float,
) -> tuple[float, float]:
    animation = member[1] if member is not None else None
    return animation_length_bounds_or_default(
        animation,
        axis=axis,
        default=default,
    )


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


__all__ = [
    "_group_transform_clone_origin",
    "_interpolate_numeric_keyframes",
    "_interpolate_pair_keyframes",
    "_numeric_bounds",
    "_parse_rotate_keyframes",
    "_parse_scale_bounds",
    "_parse_translate_pair",
    "_rotate_around_point",
]
