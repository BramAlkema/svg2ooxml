"""Gradient paint conversion helpers for DrawingML."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import clamp_opacity, opacity_to_ppt
from svg2ooxml.common.conversions.scale import position_to_ppt
from svg2ooxml.common.gradient_stops import remap_stops_for_radial_focal_radius
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, color_choice, to_string
from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint


def normalize_gradient_for_drawingml_bbox(paint, shape_bbox):
    """Convert resolved user-space gradient coordinates to DrawingML bbox units.

    SVG parsing resolves ``calc()`` and concrete lengths before paint reaches this
    layer. DrawingML gradient geometry is shape-relative, so only paints still
    marked ``userSpaceOnUse`` need this final bbox projection.
    """
    units = getattr(paint, "gradient_units", None)
    if units != "userSpaceOnUse" or shape_bbox is None:
        return paint

    bx, by = shape_bbox.x, shape_bbox.y
    bw = max(shape_bbox.width, 1e-6)
    bh = max(shape_bbox.height, 1e-6)

    if isinstance(paint, LinearGradientPaint):
        sx, sy = paint.start
        ex, ey = paint.end
        return replace(
            paint,
            start=((sx - bx) / bw, (sy - by) / bh),
            end=((ex - bx) / bw, (ey - by) / bh),
            gradient_units="objectBoundingBox",
        )

    if isinstance(paint, RadialGradientPaint):
        cx, cy = paint.center
        radius = paint.radius
        kwargs: dict[str, Any] = {
            "center": ((cx - bx) / bw, (cy - by) / bh),
            "radius": radius / max(bw, bh),
            "gradient_units": "objectBoundingBox",
        }
        if paint.focal_point is not None:
            fx, fy = paint.focal_point
            kwargs["focal_point"] = ((fx - bx) / bw, (fy - by) / bh)
        if paint.focal_radius is not None:
            kwargs["focal_radius"] = paint.focal_radius / max(bw, bh)
        return replace(paint, **kwargs)

    return paint


def scale_gradient_stops(paint, opacity: float | None):
    """Apply an inherited opacity multiplier to every gradient stop."""
    if opacity is None or opacity >= 0.999:
        return paint
    stops = [
        replace(stop, opacity=clamp_opacity(float(stop.opacity) * opacity))
        for stop in getattr(paint, "stops", [])
    ]
    return replace(paint, stops=stops)


def _expand_stops_for_spread(stops, spread_method: str | None):
    """Expand gradient stops for reflect/repeat spread methods."""
    if not spread_method or spread_method == "pad" or len(stops) < 2:
        return stops

    from svg2ooxml.ir.paint import GradientStop

    start_off = stops[0].offset
    end_off = stops[-1].offset
    extent = end_off - start_off
    if extent < 1e-6:
        return stops

    reps_needed = max(1, int(math.ceil(1.0 / extent)))
    reps_needed = min(reps_needed, 10)

    expanded = []
    for rep in range(reps_needed):
        if spread_method == "reflect" and rep % 2 == 1:
            for stop in reversed(stops):
                new_offset = rep * extent + (end_off - stop.offset)
                if new_offset > 1.0 + 1e-6:
                    continue
                expanded.append(
                    GradientStop(
                        offset=min(1.0, max(0.0, new_offset)),
                        rgb=stop.rgb,
                        opacity=stop.opacity,
                        theme_color=stop.theme_color,
                    )
                )
        else:
            for stop in stops:
                new_offset = rep * extent + (stop.offset - start_off)
                if new_offset > 1.0 + 1e-6:
                    continue
                expanded.append(
                    GradientStop(
                        offset=min(1.0, max(0.0, new_offset)),
                        rgb=stop.rgb,
                        opacity=stop.opacity,
                        theme_color=stop.theme_color,
                    )
                )

    seen_offsets: set[int] = set()
    deduped = []
    for stop in expanded:
        key = round(stop.offset * 100000)
        if key not in seen_offsets:
            seen_offsets.add(key)
            deduped.append(stop)

    return deduped if deduped else stops


def _apply_radial_focal_radius_to_stops(
    stops, radius: float, focal_radius: float | None
):
    return remap_stops_for_radial_focal_radius(
        stops,
        radius=radius,
        focal_radius=focal_radius,
        offset_of=lambda stop: float(stop.offset),
        with_offset=lambda stop, offset: replace(stop, offset=offset),
    )


def _linear_gradient_to_fill_elem(paint: LinearGradientPaint):
    """Create linear gradient fill element."""
    dx = paint.end[0] - paint.start[0]
    dy = paint.end[1] - paint.start[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        angle = 0.0
    else:
        radians = math.atan2(dy, dx)
        angle = (450 - math.degrees(radians)) % 360
    ang_val = degrees_to_ppt(angle)

    stops = _expand_stops_for_spread(paint.stops, paint.spread_method)

    gradFill = a_elem("gradFill", rotWithShape="1")
    gsLst = a_sub(gradFill, "gsLst")
    for stop in stops:
        gsLst.append(_gradient_stop_elem(stop))

    a_sub(gradFill, "lin", ang=ang_val, scaled="0")
    return gradFill


def linear_gradient_to_fill(paint: LinearGradientPaint) -> str:
    """Create linear gradient fill XML string."""
    return to_string(_linear_gradient_to_fill_elem(paint))


def _radial_gradient_to_fill_elem(paint: RadialGradientPaint):
    """Create radial gradient fill element."""
    cx, cy = paint.center
    radius = max(paint.radius, 1e-6)

    if paint.focal_point is not None:
        fx, fy = paint.focal_point
        cx = cx + (fx - cx) * 0.5
        cy = cy + (fy - cy) * 0.5

    left = position_to_ppt(max(0.0, cx - radius))
    top = position_to_ppt(max(0.0, cy - radius))
    right = position_to_ppt(max(0.0, 1.0 - (cx + radius)))
    bottom = position_to_ppt(max(0.0, 1.0 - (cy + radius)))

    stops = _expand_stops_for_spread(paint.stops, paint.spread_method)
    stops = _apply_radial_focal_radius_to_stops(stops, radius, paint.focal_radius)

    gradFill = a_elem("gradFill", rotWithShape="1")
    gsLst = a_sub(gradFill, "gsLst")
    for stop in stops:
        gsLst.append(_gradient_stop_elem(stop))

    path = a_sub(gradFill, "path", path="circle")
    a_sub(path, "fillToRect", l=left, t=top, r=right, b=bottom)
    return gradFill


def radial_gradient_to_fill(paint: RadialGradientPaint) -> str:
    """Create radial gradient fill XML string."""
    return to_string(_radial_gradient_to_fill_elem(paint))


def gradient_stop_xml(stop) -> str:
    """Create gradient stop XML string."""
    return to_string(_gradient_stop_elem(stop))


def _gradient_stop_elem(stop):
    """Create a DrawingML gradient stop element."""
    position = position_to_ppt(stop.offset)
    alpha = opacity_to_ppt(stop.opacity)

    gs = a_elem("gs", pos=position)
    gs.append(color_choice(stop.rgb, alpha=alpha, theme_color=stop.theme_color))
    return gs


__all__ = [
    "_expand_stops_for_spread",
    "_apply_radial_focal_radius_to_stops",
    "_gradient_stop_elem",
    "_linear_gradient_to_fill_elem",
    "_radial_gradient_to_fill_elem",
    "gradient_stop_xml",
    "linear_gradient_to_fill",
    "normalize_gradient_for_drawingml_bbox",
    "radial_gradient_to_fill",
    "scale_gradient_stops",
]
