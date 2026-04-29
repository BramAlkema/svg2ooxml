"""SVG motion path parsing and curve sampling helpers."""

from __future__ import annotations

import re
from typing import Any

from svg2ooxml.drawingml.animation.handlers.motion_path_types import PointPair

_SIMPLE_PATH_TOKEN_PATTERN = re.compile(
    r"[MLml]|[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?"
)


def resolve_initial_tangent_vector(path_value: str) -> PointPair | None:
    """Return the first non-zero tangent vector from the SVG path data."""

    if not path_value:
        return None

    try:
        from svg2ooxml.common.geometry.paths import PathParseError
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
        from svg2ooxml.common.geometry.paths import PathParseError
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
    tokens = _SIMPLE_PATH_TOKEN_PATTERN.findall(path_value)

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
    "dedupe_points",
    "parse_motion_path",
    "resolve_initial_tangent_vector",
    "sample_bezier",
    "simple_path_parse",
]
