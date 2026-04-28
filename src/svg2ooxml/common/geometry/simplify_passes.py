"""Basic path simplification passes."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.points import (
    point_distance,
    point_to_line_distance,
    points_collinear_by_angle,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, SegmentType


def remove_degenerates(
    segments: list[SegmentType],
    epsilon: float,
) -> list[SegmentType]:
    """Remove segments whose start is effectively equal to end."""

    kept: list[SegmentType] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            if point_distance(segment.start, segment.end) < epsilon:
                continue
        elif isinstance(segment, BezierSegment):
            if (
                point_distance(segment.start, segment.end) < epsilon
                and point_distance(segment.start, segment.control1) < epsilon
                and point_distance(segment.start, segment.control2) < epsilon
            ):
                continue
        kept.append(segment)

    if not kept and segments:
        kept.append(segments[-1])
    return kept


def demote_flat_beziers(
    segments: list[SegmentType],
    flatness: float,
) -> list[SegmentType]:
    """Replace Bezier segments whose controls lie close to their chord."""

    result: list[SegmentType] = []
    for segment in segments:
        if isinstance(segment, BezierSegment) and _bezier_is_flat(segment, flatness):
            result.append(LineSegment(segment.start, segment.end))
            continue
        result.append(segment)
    return result


def merge_collinear(
    segments: list[SegmentType],
    angle_deg: float,
    epsilon: float,
) -> list[SegmentType]:
    """Merge consecutive line segments with the same direction."""

    if not segments:
        return segments
    angle_rad = math.radians(angle_deg)
    result: list[SegmentType] = []
    index = 0
    while index < len(segments):
        segment = segments[index]
        if not isinstance(segment, LineSegment):
            result.append(segment)
            index += 1
            continue

        run_start = segment.start
        run_end = segment.end
        next_index = index + 1
        while next_index < len(segments):
            next_segment = segments[next_index]
            if not isinstance(next_segment, LineSegment):
                break
            if point_distance(run_end, next_segment.start) > epsilon:
                break
            if not points_collinear_by_angle(
                run_start,
                run_end,
                next_segment.end,
                angle_rad,
            ):
                break
            run_end = next_segment.end
            next_index += 1
        result.append(LineSegment(run_start, run_end))
        index = next_index
    return result


def _bezier_is_flat(segment: BezierSegment, flatness: float) -> bool:
    chord_length = point_distance(segment.start, segment.end)
    if chord_length < 1e-9:
        return (
            point_distance(segment.start, segment.control1) < flatness
            and point_distance(segment.start, segment.control2) < flatness
        )
    return (
        point_to_line_distance(segment.control1, segment.start, segment.end) < flatness
        and point_to_line_distance(segment.control2, segment.start, segment.end)
        < flatness
    )


__all__ = ["demote_flat_beziers", "merge_collinear", "remove_degenerates"]
