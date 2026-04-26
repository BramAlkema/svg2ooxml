"""Pure path mechanics for DrawingML motion animations."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from svg2ooxml.drawingml.animation.timing_utils import compute_paced_key_times_2d
from svg2ooxml.ir.animation import CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

PointPair = tuple[float, float]


def project_motion_points(
    points: list[PointPair],
    animation: AnimationDefinition,
) -> list[PointPair]:
    """Project SVG motion points into absolute slide-space shape positions."""

    if not points:
        return points

    matrix = animation.motion_space_matrix
    if matrix is None:
        transformed = list(points)
    else:
        a, b, c, d, e, f = matrix
        transformed = [(a * x + c * y + e, b * x + d * y + f) for x, y in points]

    offset_x = 0.0
    offset_y = 0.0
    if animation.element_motion_offset_px is not None:
        offset_x, offset_y = animation.element_motion_offset_px

    if abs(offset_x) < 1e-9 and abs(offset_y) < 1e-9:
        return transformed

    return [(x + offset_x, y + offset_y) for x, y in transformed]


def build_motion_path_string(
    points: list[PointPair],
    animation: AnimationDefinition,
) -> str:
    """Convert absolute slide-space points to a PowerPoint motion path."""

    viewport_w = 960.0
    viewport_h = 720.0
    if animation.motion_viewport_px is not None:
        viewport_w = max(animation.motion_viewport_px[0], 1.0)
        viewport_h = max(animation.motion_viewport_px[1], 1.0)
    start_x, start_y = points[0]

    segments: list[str] = []
    for index, (x_px, y_px) in enumerate(points):
        dx_px = x_px - start_x
        dy_px = y_px - start_y
        nx = dx_px / viewport_w
        ny = dy_px / viewport_h
        cmd = "M" if index == 0 else "L"
        segments.append(f"{cmd} {format_coord(nx)} {format_coord(ny)}")

    return " ".join(segments) + " E"


def format_coord(value: float) -> str:
    """Format normalized coordinate as a compact string."""

    if abs(value) < 1e-10:
        return "0"
    return f"{value:.6g}"


def retime_motion_points(
    points: list[PointPair],
    animation: AnimationDefinition,
    segment_budget: int = 96,
) -> list[PointPair]:
    """Approximate keyTimes/calcMode timing by expanding path vertices."""

    if len(points) < 2:
        return points

    calc_mode_value = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )

    if animation.key_points is not None and len(animation.key_points) >= 2:
        key_points = sample_points_at_progress(points, animation.key_points)
        if (
            animation.key_times is not None
            and len(animation.key_times) == len(animation.key_points)
        ):
            key_times = list(animation.key_times)
        else:
            key_times = uniform_key_times(len(key_points))
    elif calc_mode_value == CalcMode.PACED.value:
        if len(points) < 3 and not animation.key_times:
            return points
        key_points = list(points)
        paced_times = compute_paced_key_times_2d(key_points)
        key_times = paced_times or uniform_key_times(len(key_points))
    elif animation.key_times is not None and len(animation.key_times) >= 2:
        key_times = list(animation.key_times)
        key_points = (
            list(points)
            if len(key_times) == len(points)
            else sample_points_at_progress(points, key_times)
        )
    elif calc_mode_value in {
        CalcMode.LINEAR.value,
        CalcMode.DISCRETE.value,
    } and len(points) > 2:
        key_points = list(points)
        key_times = uniform_key_times(len(key_points))
    else:
        return points

    if len(key_points) < 2 or len(key_times) != len(key_points):
        return points

    if calc_mode_value == CalcMode.DISCRETE.value:
        return expand_discrete_points(
            points=key_points,
            key_times=key_times,
            segment_budget=segment_budget,
        )

    return retime_linear_points(
        points=key_points,
        key_times=key_times,
        segment_budget=segment_budget,
    )


def uniform_key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def sample_points_at_progress(
    points: list[PointPair],
    key_times: list[float],
) -> list[PointPair]:
    if len(points) < 2 or len(key_times) < 2:
        return points

    lengths = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        total += math.hypot(x1 - x0, y1 - y0)
        lengths.append(total)

    if total <= 1e-9:
        return [points[0] for _ in key_times]

    sampled: list[PointPair] = []
    for fraction in key_times:
        target = max(0.0, min(1.0, fraction)) * total
        sampled.append(
            sample_polyline_at_distance(
                points=points,
                cumulative_lengths=lengths,
                target_distance=target,
            )
        )
    return sampled


def sample_polyline_at_distance(
    *,
    points: list[PointPair],
    cumulative_lengths: list[float],
    target_distance: float,
) -> PointPair:
    if target_distance <= 0.0:
        return points[0]
    if target_distance >= cumulative_lengths[-1]:
        return points[-1]

    for index in range(1, len(points)):
        prev_dist = cumulative_lengths[index - 1]
        curr_dist = cumulative_lengths[index]
        if target_distance <= curr_dist:
            span = curr_dist - prev_dist
            if span <= 1e-9:
                return points[index]
            t = (target_distance - prev_dist) / span
            x0, y0 = points[index - 1]
            x1, y1 = points[index]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    return points[-1]


def retime_linear_points(
    *,
    points: list[PointPair],
    key_times: list[float],
    segment_budget: int,
) -> list[PointPair]:
    expanded: list[PointPair] = [points[0]]
    for index in range(1, len(points)):
        start = points[index - 1]
        end = points[index]
        duration = max(0.0, key_times[index] - key_times[index - 1])
        segment_count = max(1, int(round(duration * segment_budget)))

        for step in range(1, segment_count + 1):
            t = step / segment_count
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            expanded.append((x, y))

    return expanded


def expand_discrete_points(
    *,
    points: list[PointPair],
    key_times: list[float],
    segment_budget: int,
) -> list[PointPair]:
    expanded: list[PointPair] = [points[0]]
    for index in range(1, len(points)):
        prev = points[index - 1]
        curr = points[index]
        duration = max(0.0, key_times[index] - key_times[index - 1])
        slot_count = max(1, int(round(duration * segment_budget)))

        for _ in range(max(0, slot_count - 1)):
            expanded.append(prev)
        expanded.append(curr)

    return expanded


def sample_path_tangent_angles(
    points: list[PointPair],
    rotate_mode: str,
) -> list[float]:
    """Return unwrapped tangent angles for each sampled motion point."""

    if len(points) < 2:
        return []

    segment_angles = [
        estimate_segment_tangent_angle(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    valid_angles = [angle for angle in segment_angles if angle is not None]
    if not valid_angles:
        return []

    fallback_angle = valid_angles[0]
    normalized_segments: list[float] = []
    for angle in segment_angles:
        resolved_angle = fallback_angle if angle is None else angle
        fallback_angle = resolved_angle
        normalized_segments.append(resolved_angle)

    point_angles = [normalized_segments[0], *normalized_segments]
    if rotate_mode == "auto-reverse":
        point_angles = [angle + 180.0 for angle in point_angles]
    return unwrap_angles(point_angles)


def has_dynamic_rotation(point_angles: list[float]) -> bool:
    if len(point_angles) < 2:
        return False
    return any(
        abs(point_angles[index + 1] - point_angles[index]) > 1e-6
        for index in range(len(point_angles) - 1)
    )


def estimate_segment_tangent_angle(start: PointPair, end: PointPair) -> float | None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return math.degrees(math.atan2(dy, dx))


def unwrap_angles(angles: list[float]) -> list[float]:
    """Unwrap angle samples so consecutive deltas stay continuous."""

    if not angles:
        return []

    unwrapped = [angles[0]]
    for angle in angles[1:]:
        adjusted = angle
        while adjusted - unwrapped[-1] > 180.0:
            adjusted -= 360.0
        while adjusted - unwrapped[-1] < -180.0:
            adjusted += 360.0
        unwrapped.append(adjusted)
    return unwrapped


def resolve_exact_initial_tangent_angle(
    path_value: str,
    animation: AnimationDefinition,
    rotate_mode: str,
) -> float | None:
    """Resolve the exact tangent angle at the start of the SVG motion path."""

    vector = resolve_initial_tangent_vector(path_value)
    if vector is None:
        return None

    dx, dy = vector
    matrix = animation.motion_space_matrix
    if matrix is not None:
        a, b, c, d, _e, _f = matrix
        dx, dy = (a * dx + c * dy, b * dx + d * dy)

    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None

    angle = math.degrees(math.atan2(dy, dx))
    if rotate_mode == "auto-reverse":
        angle += 180.0
    heading = animation.element_heading_deg
    if heading is not None:
        angle -= heading
    return angle


def resolve_initial_tangent_vector(path_value: str) -> PointPair | None:
    """Return the first non-zero tangent vector from the SVG path data."""

    if not path_value:
        return None

    try:
        from svg2ooxml.common.geometry.paths import (
            PathParseError,
        )
        from svg2ooxml.common.geometry.paths.motion import parse_motion_path_data
        from svg2ooxml.common.geometry.paths.segments import (
            BezierSegment,
            LineSegment,
        )
    except ImportError:
        return None

    try:
        segments = parse_motion_path_data(path_value)
    except PathParseError:
        return None

    for segment in segments:
        if isinstance(segment, LineSegment):
            dx = segment.end.x - segment.start.x
            dy = segment.end.y - segment.start.y
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                return (dx, dy)
            continue

        if isinstance(segment, BezierSegment):
            candidates = (
                (
                    segment.control1.x - segment.start.x,
                    segment.control1.y - segment.start.y,
                ),
                (
                    segment.control2.x - segment.start.x,
                    segment.control2.y - segment.start.y,
                ),
                (
                    segment.end.x - segment.start.x,
                    segment.end.y - segment.start.y,
                ),
            )
            for dx, dy in candidates:
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    return (dx, dy)

    return None


def parse_motion_path(path_value: str) -> list[PointPair]:
    """Parse SVG motion path into list of (x, y) pixel tuples."""

    if not path_value:
        return []

    try:
        from svg2ooxml.common.geometry.paths import (
            PathParseError,
        )
        from svg2ooxml.common.geometry.paths.motion import parse_motion_path_data
        from svg2ooxml.common.geometry.paths.segments import (
            BezierSegment,
            LineSegment,
        )
    except ImportError:
        return simple_path_parse(path_value)

    try:
        segments = parse_motion_path_data(path_value)
    except PathParseError:
        return []

    if not segments:
        return []

    points = [segments[0].start]
    for segment in segments:
        if isinstance(segment, LineSegment):
            points.append(segment.end)
        elif isinstance(segment, BezierSegment):
            points.extend(sample_bezier(segment))

    return dedupe_points(points)


def sample_bezier(segment: Any, *, steps: int = 20) -> list[Any]:
    """Sample a cubic bezier curve into *steps* evenly-spaced points."""

    return [bezier_point(segment, index / steps) for index in range(1, steps + 1)]


def bezier_point(segment: Any, t: float) -> Any:
    """De Casteljau evaluation of a cubic bezier at parameter *t*."""

    from svg2ooxml.ir.geometry import Point

    mt = 1.0 - t
    x = (
        mt**3 * segment.start.x
        + 3 * mt**2 * t * segment.control1.x
        + 3 * mt * t**2 * segment.control2.x
        + t**3 * segment.end.x
    )
    y = (
        mt**3 * segment.start.y
        + 3 * mt**2 * t * segment.control1.y
        + 3 * mt * t**2 * segment.control2.y
        + t**3 * segment.end.y
    )
    return Point(x=x, y=y)


def dedupe_points(points: list[Any]) -> list[PointPair]:
    """Remove consecutive duplicate points."""

    deduped: list[PointPair] = []
    epsilon = 1e-6

    for point in points:
        pair = (point.x, point.y)
        if not deduped or (
            abs(deduped[-1][0] - pair[0]) > epsilon
            or abs(deduped[-1][1] - pair[1]) > epsilon
        ):
            deduped.append(pair)

    return deduped


def simple_path_parse(path_value: str) -> list[PointPair]:
    """Fallback parser for basic M/L commands."""

    points: list[PointPair] = []
    tokens = path_value.replace(",", " ").split()

    index = 0
    while index < len(tokens):
        cmd = tokens[index]
        if cmd.upper() in ("M", "L"):
            if index + 2 < len(tokens):
                try:
                    x = float(tokens[index + 1])
                    y = float(tokens[index + 2])
                    points.append((x, y))
                    index += 3
                except ValueError:
                    index += 1
            else:
                index += 1
        else:
            index += 1

    return points


__all__ = [
    "bezier_point",
    "build_motion_path_string",
    "dedupe_points",
    "estimate_segment_tangent_angle",
    "expand_discrete_points",
    "format_coord",
    "has_dynamic_rotation",
    "parse_motion_path",
    "project_motion_points",
    "resolve_exact_initial_tangent_angle",
    "resolve_initial_tangent_vector",
    "retime_linear_points",
    "retime_motion_points",
    "sample_bezier",
    "sample_path_tangent_angles",
    "sample_points_at_progress",
    "sample_polyline_at_distance",
    "simple_path_parse",
    "uniform_key_times",
    "unwrap_angles",
]
