"""Paint/stroke conversion helpers for DrawingML writer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.conversions.opacity import clamp_opacity, opacity_to_ppt
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.drawingml.paint_dash import _dash_elem
from svg2ooxml.drawingml.paint_gradients import (
    _linear_gradient_to_fill_elem,
    _radial_gradient_to_fill_elem,
    gradient_stop_xml,
    linear_gradient_to_fill,
    normalize_gradient_for_drawingml_bbox,
    radial_gradient_to_fill,
    scale_gradient_stops,
)
from svg2ooxml.drawingml.paint_patterns import _pattern_to_fill_elem, pattern_to_fill
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    no_fill,
    scheme_color,
    solid_fill,
    to_string,
)
from svg2ooxml.ir.paint import (
    GradientPaintRef,
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    StrokeCap,
    StrokeJoin,
)

from .markers import marker_end_elements


def paint_to_fill(paint, *, opacity: float | None = None, shape_bbox=None) -> str:
    if isinstance(paint, SolidPaint):
        effective = paint.opacity
        if opacity is not None:
            effective = clamp_opacity(effective * opacity)
        alpha = opacity_to_ppt(effective)
        return to_string(solid_fill(paint.rgb, alpha=alpha, theme_color=paint.theme_color))
    if isinstance(paint, LinearGradientPaint):
        paint = normalize_gradient_for_drawingml_bbox(paint, shape_bbox)
        paint = scale_gradient_stops(paint, opacity)
        return linear_gradient_to_fill(paint)
    if isinstance(paint, RadialGradientPaint):
        paint = normalize_gradient_for_drawingml_bbox(paint, shape_bbox)
        paint = scale_gradient_stops(paint, opacity)
        return radial_gradient_to_fill(paint)
    if isinstance(paint, GradientPaintRef):
        fill = a_elem("solidFill")
        fill.append(scheme_color("phClr"))
        return to_string(fill)
    if isinstance(paint, PatternPaint):
        return pattern_to_fill(paint, opacity=opacity)
    return to_string(no_fill())


def stroke_to_xml(
    stroke,
    metadata: Mapping[str, Any] | None = None,
    *,
    opacity: float | None = None,
) -> str:
    markers = {}
    marker_profiles = {}
    if isinstance(metadata, Mapping):
        markers = metadata.get("markers") or {}
        marker_profiles = metadata.get("marker_profiles") or {}

    head_elem, tail_elem = marker_end_elements(markers, marker_profiles=marker_profiles)

    if stroke is None or stroke.paint is None:
        ln = a_elem("ln")
        a_sub(ln, "noFill")
        if head_elem is not None:
            ln.append(head_elem)
        if tail_elem is not None:
            ln.append(tail_elem)
        return to_string(ln)

    width_emu = max(1, px_to_emu(stroke.width))
    ln = a_elem("ln", w=width_emu)

    paint = stroke.paint
    if isinstance(paint, SolidPaint):
        color = paint.rgb.upper()
        effective_opacity = clamp_opacity(paint.opacity * stroke.opacity)
        if opacity is not None:
            effective_opacity = clamp_opacity(effective_opacity * opacity)
        alpha = opacity_to_ppt(effective_opacity)
        fill = solid_fill(color, alpha=alpha, theme_color=paint.theme_color)
        ln.append(fill)
    elif isinstance(paint, PatternPaint):
        pattern_opacity = stroke.opacity if hasattr(stroke, "opacity") else None
        if opacity is not None:
            pattern_opacity = (
                opacity
                if pattern_opacity is None
                else clamp_opacity(pattern_opacity * opacity)
            )
        ln.append(_pattern_to_fill_elem(paint, opacity=pattern_opacity))
    elif isinstance(paint, LinearGradientPaint):
        effective_opacity = stroke.opacity
        if opacity is not None:
            effective_opacity = clamp_opacity(effective_opacity * opacity)
        paint = scale_gradient_stops(paint, effective_opacity)
        ln.append(_linear_gradient_to_fill_elem(paint))
    elif isinstance(paint, RadialGradientPaint):
        effective_opacity = stroke.opacity
        if opacity is not None:
            effective_opacity = clamp_opacity(effective_opacity * opacity)
        paint = scale_gradient_stops(paint, effective_opacity)
        ln.append(_radial_gradient_to_fill_elem(paint))
    elif isinstance(paint, GradientPaintRef):
        fill = a_elem("solidFill")
        fill.append(scheme_color("phClr"))
        ln.append(fill)
    else:
        a_sub(ln, "noFill")

    dash_elem = _dash_elem(
        stroke.dash_array, stroke.width, dash_offset=stroke.dash_offset
    )
    if dash_elem is not None:
        ln.append(dash_elem)

    cap_map = {
        StrokeCap.ROUND: "rnd",
        StrokeCap.SQUARE: "sq",
        StrokeCap.BUTT: "flat",
    }
    ln.set("cap", cap_map.get(stroke.cap, "flat"))

    if stroke.join == StrokeJoin.ROUND:
        a_sub(ln, "round")
    elif stroke.join == StrokeJoin.BEVEL:
        a_sub(ln, "bevel")
    else:
        if stroke.miter_limit and stroke.miter_limit > 0:
            a_sub(ln, "miter", lim=int(round(stroke.miter_limit * 1000)))
        else:
            a_sub(ln, "miter")

    if head_elem is not None:
        ln.append(head_elem)
    if tail_elem is not None:
        ln.append(tail_elem)

    return to_string(ln)


def clip_rect_to_xml(clip_meta: Mapping[str, Any]) -> str:
    try:
        x = px_to_emu(float(clip_meta.get("x", 0.0)))
        y = px_to_emu(float(clip_meta.get("y", 0.0)))
        width = px_to_emu(float(clip_meta.get("width", 0.0)))
        height = px_to_emu(float(clip_meta.get("height", 0.0)))
    except (TypeError, ValueError):
        return ""
    if width <= 0 or height <= 0:
        return ""
    x2 = x + width
    y2 = y + height

    clipPath = a_elem("clipPath")
    path = a_sub(clipPath, "path", clipFill="1")

    moveTo = a_sub(path, "moveTo")
    a_sub(moveTo, "pt", x=x, y=y)

    lnTo1 = a_sub(path, "lnTo")
    a_sub(lnTo1, "pt", x=x2, y=y)

    lnTo2 = a_sub(path, "lnTo")
    a_sub(lnTo2, "pt", x=x2, y=y2)

    lnTo3 = a_sub(path, "lnTo")
    a_sub(lnTo3, "pt", x=x, y=y2)

    a_sub(path, "close")
    return to_string(clipPath)


__all__ = [
    "clip_rect_to_xml",
    "gradient_stop_xml",
    "linear_gradient_to_fill",
    "paint_to_fill",
    "pattern_to_fill",
    "radial_gradient_to_fill",
    "stroke_to_xml",
]
