"""Adapter that converts IR path segments into EMF blobs."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from svg2ooxml.common.units import ConversionContext, UnitConverter, emu_to_px
from svg2ooxml.io.emf import DashPattern, EMFBlob
from svg2ooxml.io.emf.path import flatten_segments
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, SegmentType
from svg2ooxml.ir.paint import SolidPaint, Stroke, StrokeCap, StrokeJoin

_EPSILON = 1e-6
_FILL_MODE_ALTERNATE = 1  # even-odd
_FILL_MODE_WINDING = 2  # non-zero

_LINE_CAP_TO_PEN: dict[StrokeCap, int] = {
    StrokeCap.BUTT: 0x00000200,  # PS_ENDCAP_FLAT
    StrokeCap.ROUND: 0x00000000,  # PS_ENDCAP_ROUND
    StrokeCap.SQUARE: 0x00000100,  # PS_ENDCAP_SQUARE
}

_LINE_JOIN_TO_PEN: dict[StrokeJoin, int] = {
    StrokeJoin.MITER: 0x00002000,  # PS_JOIN_MITER
    StrokeJoin.ROUND: 0x00000000,  # PS_JOIN_ROUND
    StrokeJoin.BEVEL: 0x00001000,  # PS_JOIN_BEVEL
}


@dataclass(slots=True)
class PathStyle:
    """Minimal style payload required for EMF rendering."""

    fill: SolidPaint | None
    fill_rule: str
    stroke: Stroke | None


@dataclass(slots=True)
class EMFPathResult:
    """Result of EMF path rendering."""

    emf_bytes: bytes
    width_emu: int
    height_emu: int
    origin: tuple[float, float]
    size: tuple[float, float]


class EMFPathAdapter:
    """Convert IR path data into EMF blobs using the svg2ooxml EMF utilities."""

    def __init__(self, *, flatten_tolerance: float = 0.5) -> None:
        self._flatten_tolerance = flatten_tolerance

    def render(
        self,
        *,
        segments: Sequence[SegmentType],
        style: PathStyle,
        unit_converter: UnitConverter,
        conversion_context: ConversionContext | None,
        dpi: int,
    ) -> EMFPathResult | None:
        if not segments:
            return None

        subpaths = list(self._group_segments(segments))
        if not subpaths:
            return None

        flattened = [flatten_segments(path, tolerance=self._flatten_tolerance) for path in subpaths]
        flattened = [points for points in flattened if len(points) >= 2]
        if not flattened:
            return None

        min_x, max_x, min_y, max_y = _extents(flattened)
        width = max(1.0, max_x - min_x)
        height = max(1.0, max_y - min_y)

        width_emu = max(1, int(round(unit_converter.to_emu(width, conversion_context, axis="x"))))
        height_emu = max(1, int(round(unit_converter.to_emu(height, conversion_context, axis="y"))))

        blob = EMFBlob(width_emu, height_emu, dpi=max(1, int(round(dpi))))

        fill_handle: int | None = None
        stroke_handle: int | None = None
        stroke_dash: DashPattern | None = None
        pen_style = 0
        pen_cap = _LINE_CAP_TO_PEN.get(style.stroke.cap, 0) if style.stroke else 0
        pen_join = _LINE_JOIN_TO_PEN.get(style.stroke.join, 0) if style.stroke else 0
        stroke_width_emu = 1

        if style.fill is not None:
            color = _colorref(style.fill.rgb)
            fill_handle = blob.get_solid_brush(color)
            fill_mode = _fill_mode(style.fill_rule)
            blob.set_poly_fill_mode(fill_mode)

        stroke_enabled = False
        if style.stroke is not None and style.stroke.paint and isinstance(style.stroke.paint, SolidPaint):
            stroke_color = _colorref(style.stroke.paint.rgb)
            stroke_width_emu = max(
                1,
                int(round(unit_converter.to_emu(style.stroke.width, conversion_context, axis="x"))),
            )
            stroke_handle = blob.get_pen(
                stroke_color,
                stroke_width_emu,
                line_cap=pen_cap,
                line_join=pen_join,
                pen_style=pen_style,
            )
            stroke_dash = _dash_pattern(style.stroke, unit_converter, conversion_context)
            stroke_enabled = True
        else:
            stroke_handle = None

        polygons: list[list[tuple[int, int]]] = []
        polylines: list[list[tuple[int, int]]] = []
        origin = (min_x, min_y)

        for points in flattened:
            emu_points = _convert_points(points, origin, unit_converter, conversion_context)
            if style.fill is not None and _is_closed(points):
                polygons.append(list(emu_points))
            if stroke_enabled:
                stroke_points = list(emu_points)
                if _is_closed(points):
                    stroke_points.append(stroke_points[0])
                polylines.append(stroke_points)

        if style.fill is not None and polygons:
            blob.fill_polypolygon(polygons, brush_handle=fill_handle)

        if stroke_enabled and polylines and stroke_handle is not None:
            for polyline in polylines:
                blob.stroke_polyline(
                    polyline,
                    pen_handle=stroke_handle,
                    dash_pattern=stroke_dash,
                    pen_width_px=stroke_width_emu,
                    line_cap=pen_cap,
                    line_join=pen_join,
                    pen_style=pen_style,
                )

        emf_bytes = blob.finalize()
        return EMFPathResult(
            emf_bytes=emf_bytes,
            width_emu=width_emu,
            height_emu=height_emu,
            origin=origin,
            size=(width, height),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _group_segments(self, segments: Sequence[SegmentType]) -> Iterator[list[SegmentType]]:
        current: list[SegmentType] = []
        last_end = None
        for segment in segments:
            start_point = _segment_start(segment)
            if current and last_end is not None and not _points_close(start_point, last_end):
                yield current
                current = []
            current.append(segment)
            last_end = _segment_end(segment)
        if current:
            yield current


def _extents(paths: Sequence[Sequence[tuple[float, float]]]) -> tuple[float, float, float, float]:
    xs = [pt[0] for path in paths for pt in path]
    ys = [pt[1] for path in paths for pt in path]
    return min(xs), max(xs), min(ys), max(ys)


def _convert_points(
    points: Sequence[tuple[float, float]],
    origin: tuple[float, float],
    unit_converter: UnitConverter,
    conversion_context: ConversionContext | None,
) -> Iterator[tuple[int, int]]:
    ox, oy = origin
    for x, y in points:
        emu_x = unit_converter.to_emu(x - ox, conversion_context, axis="x")
        emu_y = unit_converter.to_emu(y - oy, conversion_context, axis="y")
        yield int(round(emu_x)), int(round(emu_y))


def _segment_start(segment: SegmentType) -> tuple[float, float]:
    if isinstance(segment, LineSegment):
        return segment.start.x, segment.start.y
    if isinstance(segment, BezierSegment):
        return segment.start.x, segment.start.y
    return getattr(segment, "start", (0.0, 0.0))


def _segment_end(segment: SegmentType) -> tuple[float, float]:
    if isinstance(segment, LineSegment):
        return segment.end.x, segment.end.y
    if isinstance(segment, BezierSegment):
        return segment.end.x, segment.end.y
    return getattr(segment, "end", (0.0, 0.0))


def _points_close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < _EPSILON and abs(a[1] - b[1]) < _EPSILON


def _colorref(hex_color: str) -> int:
    token = hex_color.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    r = int(token[0:2], 16)
    g = int(token[2:4], 16)
    b = int(token[4:6], 16)
    return b << 16 | g << 8 | r


def _fill_mode(rule: str) -> int:
    token = (rule or "").strip().lower()
    return _FILL_MODE_ALTERNATE if token in {"evenodd", "even-odd"} else _FILL_MODE_WINDING


def _is_closed(points: Sequence[tuple[float, float]]) -> bool:
    return len(points) >= 3 and _points_close(points[0], points[-1])


def _dash_pattern(
    stroke: Stroke,
    unit_converter: UnitConverter,
    conversion_context: ConversionContext | None,
) -> DashPattern | None:
    if not stroke.dash_array:
        return None
    converted = [
        max(1, int(round(emu_to_px(unit_converter.to_emu(length, conversion_context, axis="x")))))
        for length in stroke.dash_array
    ]
    phase = int(round(emu_to_px(unit_converter.to_emu(stroke.dash_offset or 0.0, conversion_context, axis="x"))))
    return DashPattern(pattern=tuple(converted), offset=phase)


__all__ = ["EMFPathAdapter", "EMFPathResult", "PathStyle"]
