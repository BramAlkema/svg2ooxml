"""Adapter that converts IR path segments into EMF blobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Sequence, Tuple
from svg2ooxml.io.emf import DashPattern, EMFBlob
from svg2ooxml.io.emf.path import flatten_segments
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, SegmentType
from svg2ooxml.ir.paint import SolidPaint, Stroke, StrokeCap, StrokeJoin
from svg2ooxml.units.conversion import ConversionContext, UnitConverter

_EPSILON = 1e-6
_FILL_MODE_ALTERNATE = 1  # even-odd
_FILL_MODE_WINDING = 2    # non-zero

_LINE_CAP_TO_PEN: dict[StrokeCap, int] = {
    StrokeCap.BUTT: 0x00000200,    # PS_ENDCAP_FLAT
    StrokeCap.ROUND: 0x00000000,   # PS_ENDCAP_ROUND
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
    origin: Tuple[float, float]
    size: Tuple[float, float]


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
            stroke_width_emu = max(1, int(round(unit_converter.to_emu(style.stroke.width, conversion_context, axis="x"))))
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

        polygons: list[list[Tuple[int, int]]] = []
        polylines: list[list[Tuple[int, int]]] = []
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

    def _group_segments(self, segments: Sequence[SegmentType]) -> Iterator[List[SegmentType]]:
        current: list[SegmentType] = []
        last_end = None
        for segment in segments:
            if isinstance(segment, (LineSegment, BezierSegment)):
                start = segment.start
                if last_end is not None and _points_far(last_end, start):
                    if current:
                        yield current
                        current = []
                current.append(segment)
                last_end = segment.end
            else:
                current.append(segment)
        if current:
            yield current


def _extents(polylines: Sequence[Sequence[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for polyline in polylines:
        xs.extend(pt[0] for pt in polyline)
        ys.extend(pt[1] for pt in polyline)
    if not xs or not ys:
        return 0.0, 1.0, 0.0, 1.0
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x - min_x < _EPSILON:
        max_x = min_x + 1.0
    if max_y - min_y < _EPSILON:
        max_y = min_y + 1.0
    return min_x, max_x, min_y, max_y


def _convert_points(
    points: Sequence[Tuple[float, float]],
    origin: Tuple[float, float],
    unit_converter: UnitConverter,
    context: ConversionContext | None,
) -> List[Tuple[int, int]]:
    ox, oy = origin
    converted: list[Tuple[int, int]] = []
    for x, y in points:
        local_x = x - ox
        local_y = y - oy
        ex = unit_converter.to_emu(local_x, context, axis="x")
        ey = unit_converter.to_emu(local_y, context, axis="y")
        converted.append((int(round(ex)), int(round(ey))))
    return converted


def _dash_pattern(stroke: Stroke, unit_converter: UnitConverter, context: ConversionContext | None) -> DashPattern | None:
    values = stroke.dash_array
    if not values:
        return None

    converted = [abs(unit_converter.to_emu(value, context, axis="x")) for value in values if value > 0]
    if not converted:
        return None

    if len(converted) % 2 == 1:
        converted *= 2

    offset = stroke.dash_offset if stroke.dash_offset else 0.0
    offset_emu = unit_converter.to_emu(offset, context, axis="x") if offset else 0.0
    return DashPattern(tuple(converted), float(offset_emu))


def _fill_mode(fill_rule: str) -> int:
    rule = (fill_rule or "nonzero").strip().lower()
    if rule in {"evenodd", "even-odd"}:
        return _FILL_MODE_ALTERNATE
    return _FILL_MODE_WINDING


def _is_closed(points: Sequence[Tuple[float, float]]) -> bool:
    if len(points) < 3:
        return False
    first = points[0]
    last = points[-1]
    return (abs(first[0] - last[0]) <= _EPSILON) and (abs(first[1] - last[1]) <= _EPSILON)


def _points_far(a, b) -> bool:
    return abs(a.x - b.x) > _EPSILON or abs(a.y - b.y) > _EPSILON


def _colorref(rgb: str) -> int:
    value = rgb.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"expected 6 hex digits, got {rgb!r}")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return (b << 16) | (g << 8) | r


__all__ = ["EMFPathAdapter", "EMFPathResult", "PathStyle"]
