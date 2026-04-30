"""Optional Skia path helpers shared by raster and clip fallbacks."""

from __future__ import annotations

from typing import Any

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType

try:  # pragma: no cover - optional dependency
    import skia  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    skia = None


def skia_available() -> bool:
    return skia is not None


def skia_path_from_segments(
    segments: list[SegmentType] | tuple[SegmentType, ...],
    *,
    closed: bool,
    fill_rule: str | None = None,
) -> Any | None:
    if skia is None or not segments:
        return None
    path = skia.Path()
    previous: Point | None = None
    subpath_open = False
    for segment in segments:
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        if start is None or end is None:
            continue
        if previous is None or not _points_close(previous, start):
            if subpath_open and closed:
                path.close()
            path.moveTo(float(start.x), float(start.y))
            subpath_open = True
        if isinstance(segment, LineSegment):
            path.lineTo(float(end.x), float(end.y))
        elif isinstance(segment, BezierSegment):
            path.cubicTo(
                float(segment.control1.x),
                float(segment.control1.y),
                float(segment.control2.x),
                float(segment.control2.y),
                float(end.x),
                float(end.y),
            )
        previous = end
    if subpath_open and closed:
        path.close()
    if _is_even_odd(fill_rule):
        path.setFillType(skia.PathFillType.kEvenOdd)
    return None if path.isEmpty() else path


def skia_path_to_segments(path: Any) -> list[SegmentType]:
    if skia is None or path is None:
        return []
    segments: list[SegmentType] = []
    try:
        iterator = skia.Path.Iter(path, False)
    except Exception:
        return []
    for verb, points in iterator:
        if verb == skia.Path.Verb.kLine_Verb and len(points) >= 2:
            segments.append(
                LineSegment(
                    start=_point(points[0]),
                    end=_point(points[1]),
                )
            )
        elif verb == skia.Path.Verb.kQuad_Verb and len(points) >= 3:
            start = _point(points[0])
            control = _point(points[1])
            end = _point(points[2])
            segments.append(_quadratic_to_cubic(start, control, end))
        elif verb == skia.Path.Verb.kConic_Verb and len(points) >= 3:
            start = _point(points[0])
            control = _point(points[1])
            end = _point(points[2])
            segments.append(_quadratic_to_cubic(start, control, end))
        elif verb == skia.Path.Verb.kCubic_Verb and len(points) >= 4:
            segments.append(
                BezierSegment(
                    start=_point(points[0]),
                    control1=_point(points[1]),
                    control2=_point(points[2]),
                    end=_point(points[3]),
                )
            )
    return segments


def skia_path_bounds(path: Any) -> Rect | None:
    if skia is None or path is None:
        return None
    try:
        bounds = path.getBounds()
    except Exception:
        return None
    left = float(bounds.left())
    top = float(bounds.top())
    right = float(bounds.right())
    bottom = float(bounds.bottom())
    if right <= left or bottom <= top:
        return None
    return Rect(left, top, right - left, bottom - top)


def _point(point: Any) -> Point:
    return Point(float(point.x()), float(point.y()))


def _quadratic_to_cubic(start: Point, control: Point, end: Point) -> BezierSegment:
    return BezierSegment(
        start=start,
        control1=Point(
            start.x + (control.x - start.x) * 2.0 / 3.0,
            start.y + (control.y - start.y) * 2.0 / 3.0,
        ),
        control2=Point(
            end.x + (control.x - end.x) * 2.0 / 3.0,
            end.y + (control.y - end.y) * 2.0 / 3.0,
        ),
        end=end,
    )


def _points_close(a: Point, b: Point, *, tolerance: float = 1e-4) -> bool:
    return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance


def _is_even_odd(fill_rule: str | None) -> bool:
    if not isinstance(fill_rule, str):
        return False
    return fill_rule.strip().lower() in {"evenodd", "even-odd"}


__all__ = [
    "skia",
    "skia_available",
    "skia_path_bounds",
    "skia_path_from_segments",
    "skia_path_to_segments",
]
