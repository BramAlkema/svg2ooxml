"""Adapters that expose resvg path normalization inside the svg2ooxml IR."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.geometry.path_normalizer import (
    NormalizedPath as ResvgNormalizedPath,
    normalize_path as resvg_normalize_path,
)
from svg2ooxml.core.resvg.geometry.primitives import ClosePath, LineTo, MoveTo
from svg2ooxml.core.resvg.geometry.tessellation import Tessellator as ResvgTessellator
from svg2ooxml.core.resvg.geometry.tessellation import TessellationResult
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType

from ..matrix import Matrix2D

_TESSELLATOR = ResvgTessellator()


MatrixLike = ResvgMatrix | Sequence[float] | Sequence[Sequence[float]] | Matrix2D


@dataclass(slots=True)
class NormalizedSegments:
    """Normalized resvg path plus svg2ooxml IR line segments."""

    normalized_path: ResvgNormalizedPath
    segments: list[SegmentType]
    tolerance: float


@dataclass(slots=True)
class TessellationOutput:
    """Fill or stroke tessellation expressed in svg2ooxml points."""

    contours: list[list[Point]]
    areas: list[float]
    winding_rule: str
    stroke_width: float | None
    stroke_outline: list[list[Point]] | None


@dataclass(slots=True)
class PathTessellation:
    """Fill tessellation plus optional stroke outlines."""

    fill: TessellationOutput
    stroke: TessellationOutput | None


def normalize_path_to_segments(
    path_data: str | None,
    *,
    transform: MatrixLike | None = None,
    stroke_width: float | None = None,
    tolerance: float = 0.25,
) -> NormalizedSegments:
    """Normalize SVG path data with resvg and return IR-ready line segments."""

    matrix = _coerce_matrix(transform)
    normalized = resvg_normalize_path(path_data, matrix, stroke_width)
    primitives = normalized.to_primitives(tolerance=tolerance)
    segments = _primitives_to_segments(primitives)
    return NormalizedSegments(normalized_path=normalized, segments=segments, tolerance=tolerance)


def tessellate_path(
    normalized_path: ResvgNormalizedPath,
    *,
    tolerance: float = 0.25,
    winding_rule: str = "nonzero",
    include_stroke: bool = False,
) -> PathTessellation:
    """Run the resvg tessellator and convert results into IR-friendly points."""

    fill_result = _TESSELLATOR.tessellate_fill(normalized_path, tolerance, winding_rule)
    fill_output = _convert_tessellation(fill_result)

    stroke_output: TessellationOutput | None = None
    if include_stroke:
        stroke_result = _TESSELLATOR.tessellate_stroke(normalized_path, tolerance)
        stroke_output = _convert_tessellation(stroke_result)

    return PathTessellation(fill=fill_output, stroke=stroke_output)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_matrix(transform: MatrixLike | None) -> ResvgMatrix:
    if transform is None:
        return ResvgMatrix.identity()
    if isinstance(transform, ResvgMatrix):
        return transform
    if isinstance(transform, Matrix2D):
        return ResvgMatrix(transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)

    if isinstance(transform, Sequence):
        if len(transform) == 6 and all(_is_number(value) for value in transform):
            a, b, c, d, e, f = (float(value) for value in transform)  # type: ignore[assignment]
            return ResvgMatrix(a, b, c, d, e, f)

        if len(transform) == 3 and all(isinstance(row, Sequence) and len(row) == 3 for row in transform):
            a, c, e = transform[0]  # type: ignore[index]
            b, d, f = transform[1]  # type: ignore[index]
            return ResvgMatrix(float(a), float(b), float(c), float(d), float(e), float(f))

    raise TypeError(f"Unsupported transform type for resvg normalization: {type(transform)!r}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float))


def _primitives_to_segments(primitives: Iterable[object]) -> list[SegmentType]:
    segments: list[SegmentType] = []
    current_point: Point | None = None
    subpath_start: Point | None = None

    for primitive in primitives:
        if isinstance(primitive, MoveTo):
            subpath_start = Point(primitive.x, primitive.y)
            current_point = subpath_start
        elif isinstance(primitive, LineTo):
            next_point = Point(primitive.x, primitive.y)
            if current_point is not None and not _points_close(current_point, next_point):
                segments.append(LineSegment(start=current_point, end=next_point))
            current_point = next_point
        elif isinstance(primitive, ClosePath):
            if current_point and subpath_start and not _points_close(current_point, subpath_start):
                segments.append(LineSegment(start=current_point, end=subpath_start))
            current_point = subpath_start

    return segments


def _points_close(p1: Point, p2: Point, *, eps: float = 1e-9) -> bool:
    return math.isclose(p1.x, p2.x, abs_tol=eps) and math.isclose(p1.y, p2.y, abs_tol=eps)


def _convert_tessellation(result: TessellationResult) -> TessellationOutput:
    contours = [[Point(x, y) for (x, y) in contour] for contour in result.contours]
    stroke_outline = (
        [[Point(x, y) for (x, y) in contour] for contour in result.stroke_outline] if result.stroke_outline else None
    )
    return TessellationOutput(
        contours=contours,
        areas=list(result.areas),
        winding_rule=result.winding_rule,
        stroke_width=result.stroke_width,
        stroke_outline=stroke_outline,
    )


__all__ = [
    "NormalizedSegments",
    "PathTessellation",
    "TessellationOutput",
    "normalize_path_to_segments",
    "tessellate_path",
]
