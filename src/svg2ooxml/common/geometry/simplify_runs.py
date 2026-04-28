"""Line-run and subpath helpers for path simplification."""

from __future__ import annotations

from collections.abc import Callable

from svg2ooxml.common.geometry.points import point_distance
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType

SUBPATH_EPSILON = 1e-4


def map_line_runs(
    segments: list[SegmentType],
    epsilon: float,
    transform: Callable[[list[LineSegment]], list[SegmentType]],
) -> list[SegmentType]:
    """Apply *transform* to each maximal connected run of line segments."""

    result: list[SegmentType] = []
    run: list[LineSegment] = []

    def flush() -> None:
        if run:
            result.extend(transform(run))
            run.clear()

    for segment in segments:
        if isinstance(segment, LineSegment):
            if run and point_distance(run[-1].end, segment.start) > epsilon:
                flush()
            run.append(segment)
        else:
            flush()
            result.append(segment)

    flush()
    return result


def run_to_points(run: list[LineSegment]) -> list[Point]:
    return [run[0].start] + [segment.end for segment in run]


def split_subpaths(
    segments: list[SegmentType],
    *,
    epsilon: float = SUBPATH_EPSILON,
) -> list[list[SegmentType]]:
    """Split a segment list into subpaths at discontinuities."""

    subpaths: list[list[SegmentType]] = []
    current: list[SegmentType] = []
    previous_end: Point | None = None

    for segment in segments:
        if (
            previous_end is not None
            and point_distance(previous_end, segment.start) > epsilon
        ):
            if current:
                subpaths.append(current)
                current = []
        current.append(segment)
        previous_end = segment.end

    if current:
        subpaths.append(current)
    return subpaths


__all__ = ["SUBPATH_EPSILON", "map_line_runs", "run_to_points", "split_subpaths"]
