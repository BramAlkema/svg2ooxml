"""Modernised geometry path helpers shared across svg2ooxml modules."""

from .drawing import approximate_circle, approximate_ellipse, to_line_segments
from .drawingml import PathCommand, build_path_commands, compute_path_bounds
from .parser import PathParseError, parse_path_data
from .resvg_bridge import (
    NormalizedSegments,
    PathTessellation,
    TessellationOutput,
    normalize_path_to_segments,
    tessellate_path,
)
from .segments import (
    BezierSegment,
    LineSegment,
    Point,
    SegmentType,
    compute_segments_bbox,
)

__all__ = [
    "BezierSegment",
    "LineSegment",
    "Point",
    "SegmentType",
    "PathCommand",
    "PathParseError",
    "NormalizedSegments",
    "PathTessellation",
    "TessellationOutput",
    "build_path_commands",
    "compute_path_bounds",
    "compute_segments_bbox",
    "parse_path_data",
    "normalize_path_to_segments",
    "tessellate_path",
    "approximate_circle",
    "approximate_ellipse",
    "to_line_segments",
]
