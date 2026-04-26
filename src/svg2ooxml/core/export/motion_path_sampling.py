"""Motion-path sampling and sampled-motion replacement helpers."""

from __future__ import annotations

import math

from svg2ooxml.ir.animation import AnimationDefinition, AnimationType, CalcMode


def _format_motion_delta(value: float) -> str:
    if abs(value) < 1e-10:
        return "0"
    return f"{value:.6g}"


def _parse_sampled_motion_points(path_value: str) -> list[tuple[float, float]]:
    from svg2ooxml.common.geometry.paths import PathParseError
    from svg2ooxml.common.geometry.paths.motion import parse_motion_path_data
    from svg2ooxml.common.geometry.paths.segments import BezierSegment, LineSegment
    from svg2ooxml.ir.geometry import Point

    try:
        segments = parse_motion_path_data(path_value)
    except PathParseError:
        return []
    if not segments:
        return []

    points: list[Point] = [segments[0].start]
    for segment in segments:
        if isinstance(segment, LineSegment):
            points.append(segment.end)
        elif isinstance(segment, BezierSegment):
            for step in range(1, 21):
                t = step / 20.0
                mt = 1.0 - t
                points.append(
                    Point(
                        x=(
                            mt**3 * segment.start.x
                            + 3 * mt**2 * t * segment.control1.x
                            + 3 * mt * t**2 * segment.control2.x
                            + t**3 * segment.end.x
                        ),
                        y=(
                            mt**3 * segment.start.y
                            + 3 * mt**2 * t * segment.control1.y
                            + 3 * mt * t**2 * segment.control2.y
                            + t**3 * segment.end.y
                        ),
                    )
                )

    deduped: list[tuple[float, float]] = []
    for point in points:
        pair = (float(point.x), float(point.y))
        if (
            not deduped
            or abs(deduped[-1][0] - pair[0]) > 1e-6
            or abs(deduped[-1][1] - pair[1]) > 1e-6
        ):
            deduped.append(pair)
    return deduped


def _sample_polyline_at_fraction(
    points: list[tuple[float, float]],
    fraction: float,
) -> tuple[float, float]:
    return _sample_polyline_at_fraction_with_lengths(
        points,
        fraction,
        _polyline_cumulative_lengths(points),
    )


def _sample_polyline_at_fractions(
    points: list[tuple[float, float]],
    fractions: list[float],
) -> list[tuple[float, float]]:
    lengths = _polyline_cumulative_lengths(points)
    if _fractions_are_nondecreasing(fractions):
        return _sample_polyline_at_sorted_fractions(points, fractions, lengths)
    return [
        _sample_polyline_at_fraction_with_lengths(points, fraction, lengths)
        for fraction in fractions
    ]


def _fractions_are_nondecreasing(fractions: list[float]) -> bool:
    return all(
        fractions[index - 1] <= fractions[index]
        for index in range(1, len(fractions))
    )


def _sample_polyline_at_sorted_fractions(
    points: list[tuple[float, float]],
    fractions: list[float],
    cumulative: list[float],
) -> list[tuple[float, float]]:
    total = cumulative[-1] if cumulative else 0.0
    if total <= 1e-9:
        return [points[0] for _ in fractions]

    sampled: list[tuple[float, float]] = []
    segment_index = 1
    for fraction in fractions:
        if fraction <= 0.0:
            sampled.append(points[0])
            continue
        if fraction >= 1.0:
            sampled.append(points[-1])
            continue

        target = total * fraction
        while (
            segment_index < len(points) - 1
            and cumulative[segment_index] < target
        ):
            segment_index += 1
        sampled.append(
            _interpolate_polyline_segment(points, target, cumulative, segment_index)
        )
    return sampled


def _polyline_cumulative_lengths(points: list[tuple[float, float]]) -> list[float]:
    cumulative = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        total += math.hypot(x1 - x0, y1 - y0)
        cumulative.append(total)
    return cumulative


def _sample_polyline_at_fraction_with_lengths(
    points: list[tuple[float, float]],
    fraction: float,
    cumulative: list[float],
) -> tuple[float, float]:
    if fraction <= 0.0:
        return points[0]
    if fraction >= 1.0:
        return points[-1]

    total = cumulative[-1] if cumulative else 0.0
    if total <= 1e-9:
        return points[0]

    target = total * fraction
    for index in range(1, len(points)):
        curr_dist = cumulative[index]
        if target <= curr_dist:
            return _interpolate_polyline_segment(points, target, cumulative, index)
    return points[-1]


def _interpolate_polyline_segment(
    points: list[tuple[float, float]],
    target: float,
    cumulative: list[float],
    index: int,
) -> tuple[float, float]:
    prev_dist = cumulative[index - 1]
    curr_dist = cumulative[index]
    span = curr_dist - prev_dist
    if span <= 1e-9:
        return points[index]
    t = (target - prev_dist) / span
    x0, y0 = points[index - 1]
    x1, y1 = points[index]
    return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)


def _build_sampled_motion_replacement(
    *,
    template: AnimationDefinition,
    points: list[tuple[float, float]],
    key_times: list[float] | None = None,
) -> AnimationDefinition:
    from dataclasses import replace as _replace

    relative_points = _relative_motion_points(points)
    path = _build_motion_path_from_relative_points(relative_points)
    key_points = (
        _path_progress_key_points(relative_points)
        if key_times is not None and len(key_times) == len(relative_points)
        else None
    )
    return _replace(
        template,
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="position",
        values=[path],
        key_times=list(key_times) if key_points is not None else None,
        key_points=key_points,
        key_splines=None,
        calc_mode=CalcMode.LINEAR,
        transform_type=None,
        additive="replace",
        accumulate="none",
        motion_rotate=None,
        element_motion_offset_px=None,
        motion_space_matrix=None,
    )


def _relative_motion_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    start_x, start_y = points[0]
    for x, y in points:
        pair = (x - start_x, y - start_y)
        if (
            not deduped
            or abs(deduped[-1][0] - pair[0]) > 1e-6
            or abs(deduped[-1][1] - pair[1]) > 1e-6
        ):
            deduped.append(pair)
    if len(deduped) == 1:
        deduped.append(deduped[0])
    return deduped


def _build_motion_path_from_relative_points(
    points: list[tuple[float, float]],
) -> str:
    segments = []
    for index, (x, y) in enumerate(points):
        command = "M" if index == 0 else "L"
        segments.append(
            f"{command} {_format_motion_delta(x)} {_format_motion_delta(y)}"
        )
    return " ".join(segments) + " E"


def _path_progress_key_points(
    points: list[tuple[float, float]],
) -> list[float]:
    if len(points) <= 1:
        return [0.0]

    lengths = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        total += math.hypot(x1 - x0, y1 - y0)
        lengths.append(total)

    if total <= 1e-9:
        step = 1.0 / (len(points) - 1)
        return [index * step for index in range(len(points))]

    return [length / total for length in lengths]
