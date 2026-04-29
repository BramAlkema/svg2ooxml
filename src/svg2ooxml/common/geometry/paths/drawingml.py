"""Helpers for transforming IR path segments into DrawingML-ready data."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from svg2ooxml.common.geometry.paths.segments import compute_segments_bbox
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType


@dataclass(frozen=True)
class PathCommand:
    """High-level DrawingML command."""

    name: str
    points: tuple[Point, ...] = ()


def compute_path_bounds(segments: Sequence[SegmentType]) -> Rect:
    """Return a tight bounding box for the provided path segments."""

    return compute_segments_bbox(segments)


def build_path_commands(segments: Sequence[SegmentType], *, closed: bool) -> list[PathCommand]:
    """Translate segments into DrawingML path commands."""

    if not segments:
        return []

    commands: list[PathCommand] = []
    subpaths = _split_subpaths(segments)

    for index, subpath in enumerate(subpaths):
        first_segment = subpath[0]
        start_point = getattr(first_segment, "start", None)
        if start_point is None:
            continue
        commands.append(PathCommand("moveTo", (start_point,)))
        for segment in subpath:
            if isinstance(segment, LineSegment):
                commands.append(PathCommand("lnTo", (segment.end,)))
            elif isinstance(segment, BezierSegment):
                commands.append(
                    PathCommand(
                        "cubicBezTo",
                        (segment.control1, segment.control2, segment.end),
                    )
                )
            else:  # pragma: no cover - reserved for future segment types
                end_point = getattr(segment, "end", None)
                if end_point is not None:
                    commands.append(PathCommand("lnTo", (end_point,)))

        last_segment = subpath[-1]
        last_point = getattr(last_segment, "end", None)
        should_close = False
        if last_point is not None and _points_close(start_point, last_point):
            should_close = True
        elif closed and index == len(subpaths) - 1:
            should_close = True

        if should_close:
            commands.append(PathCommand("close"))

    return commands


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_subpaths(segments: Sequence[SegmentType]) -> list[list[SegmentType]]:
    subpaths: list[list[SegmentType]] = []
    current: list[SegmentType] = []
    previous_endpoint: Point | None = None

    for segment in segments:
        start = getattr(segment, "start", None)
        if start is None:
            continue
        if previous_endpoint is None or not _points_close(previous_endpoint, start):
            if current:
                subpaths.append(current)
                current = []
        current.append(segment)
        previous_endpoint = getattr(segment, "end", start)

    if current:
        subpaths.append(current)
    return subpaths


def _points_close(a: Point, b: Point, *, tolerance: float = 1e-4) -> bool:
    return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance


__all__ = ["PathCommand", "build_path_commands", "compute_path_bounds"]
