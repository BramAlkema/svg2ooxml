"""Paint/stroke conversion helpers for DrawingML writer."""

from __future__ import annotations

import math
from typing import Any, Mapping

from svg2ooxml.drawingml.generator import px_to_emu
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


def paint_to_fill(paint, *, opacity: float | None = None) -> str:
    if isinstance(paint, SolidPaint):
        effective = paint.opacity
        if opacity is not None:
            effective = max(0.0, min(1.0, effective * opacity))
        alpha = int(round(max(0.0, min(1.0, effective)) * 100000))
        return (
            "<a:solidFill>"
            f'<a:srgbClr val="{paint.rgb.upper()}">'
            f'<a:alpha val="{alpha}"/>'
            "</a:srgbClr>"
            "</a:solidFill>"
        )
    if isinstance(paint, LinearGradientPaint):
        return linear_gradient_to_fill(paint)
    if isinstance(paint, RadialGradientPaint):
        return radial_gradient_to_fill(paint)
    if isinstance(paint, GradientPaintRef):
        return "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
    if isinstance(paint, PatternPaint):
        return pattern_to_fill(paint, opacity=opacity)
    return "<a:noFill/>"


def stroke_to_xml(stroke, metadata: Mapping[str, Any] | None = None) -> str:
    markers = {}
    if isinstance(metadata, Mapping):
        markers = metadata.get("markers") or {}

    if stroke is None or stroke.paint is None:
        if not markers:
            return "<a:ln><a:noFill/></a:ln>"
        parts = ["<a:ln>", "<a:noFill/>"]
        head_xml, tail_xml = marker_end_elements(markers)
        if tail_xml:
            parts.append(tail_xml)
        if head_xml:
            parts.append(head_xml)
        parts.append("</a:ln>")
        return "".join(parts)

    width_emu = max(1, px_to_emu(stroke.width))
    parts = [f'<a:ln w="{width_emu}">']

    paint = stroke.paint
    if isinstance(paint, SolidPaint):
        color = paint.rgb.upper()
        alpha = int(round(max(0.0, min(1.0, paint.opacity)) * 100000))
        parts.append(
            "<a:solidFill>"
            f'<a:srgbClr val="{color}"><a:alpha val="{alpha}"/></a:srgbClr>'
            "</a:solidFill>"
        )
    elif isinstance(paint, PatternPaint):
        parts.append(paint_to_fill(paint, opacity=stroke.opacity))
    elif isinstance(paint, (LinearGradientPaint, RadialGradientPaint, GradientPaintRef)):
        parts.append(paint_to_fill(paint, opacity=stroke.opacity))
    else:
        parts.append("<a:noFill/>")

    dash_xml = _dash_xml(stroke.dash_array)
    if dash_xml:
        parts.append(dash_xml)

    cap_map = {
        StrokeCap.ROUND: "rnd",
        StrokeCap.SQUARE: "sq",
        StrokeCap.BUTT: "flat",
    }
    parts.append(f'<a:cap val="{cap_map.get(stroke.cap, "flat")}"/>')

    if stroke.join == StrokeJoin.ROUND:
        parts.append("<a:round/>")
    elif stroke.join == StrokeJoin.BEVEL:
        parts.append("<a:bevel/>")
    else:
        if stroke.miter_limit and stroke.miter_limit > 0:
            parts.append(f'<a:miter lim="{int(round(stroke.miter_limit * 1000))}"/>')
        else:
            parts.append("<a:miter/>")

    head_xml, tail_xml = marker_end_elements(markers)
    if tail_xml:
        parts.append(tail_xml)
    if head_xml:
        parts.append(head_xml)

    parts.append("</a:ln>")
    return "".join(parts)


def _dash_xml(dash_array: list[float] | None) -> str:
    if not dash_array:
        return ""
    values = [abs(x) for x in dash_array if x > 0]
    if not values:
        return ""
    preset = "sysDash"
    if len(values) == 2:
        on, off = values[0], values[1]
        if off == 0:
            preset = "solid"
        elif on <= off * 0.5:
            preset = "dot"
        elif on >= off * 1.5:
            preset = "lgDash"
        else:
            preset = "dash"
    elif len(values) >= 4:
        on1, off1, on2, off2 = values[:4]
        if on2 <= off2 * 0.5:
            preset = "dashDot"
        elif on1 >= off1 * 1.5 and on2 >= off2 * 1.5:
            preset = "lgDashDot"
        else:
            preset = "dashDot"
    return f'<a:prstDash val="{preset}"/>'


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
    return (
        "<a:clipPath>"
        "<a:path clipFill=\"1\">"
        f"<a:moveTo><a:pt x=\"{x}\" y=\"{y}\"/></a:moveTo>"
        f"<a:lnTo><a:pt x=\"{x2}\" y=\"{y}\"/></a:lnTo>"
        f"<a:lnTo><a:pt x=\"{x2}\" y=\"{y2}\"/></a:lnTo>"
        f"<a:lnTo><a:pt x=\"{x}\" y=\"{y2}\"/></a:lnTo>"
        "<a:close/>"
        "</a:path>"
        "</a:clipPath>"
    )


def linear_gradient_to_fill(paint: LinearGradientPaint) -> str:
    stops_xml = "".join(gradient_stop_xml(stop) for stop in paint.stops)
    dx = paint.end[0] - paint.start[0]
    dy = paint.end[1] - paint.start[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        angle = 0.0
    else:
        radians = math.atan2(dy, dx)
        angle = (450 - math.degrees(radians)) % 360
    ang_val = int(round(angle * 60000))
    return (
        "<a:gradFill rotWithShape=\"1\">"
        f"<a:gsLst>{stops_xml}</a:gsLst>"
        f"<a:lin ang=\"{ang_val}\" scaled=\"0\"/>"
        "</a:gradFill>"
    )


def radial_gradient_to_fill(paint: RadialGradientPaint) -> str:
    stops_xml = "".join(gradient_stop_xml(stop) for stop in paint.stops)
    cx, cy = paint.center
    radius = max(paint.radius, 1e-6)
    left = max(0, min(100000, int(round(max(0.0, (cx - radius)) * 100000))))
    top = max(0, min(100000, int(round(max(0.0, (cy - radius)) * 100000))))
    right = max(0, min(100000, int(round(max(0.0, (1.0 - (cx + radius))) * 100000))))
    bottom = max(0, min(100000, int(round(max(0.0, (1.0 - (cy + radius))) * 100000))))
    return (
        "<a:gradFill rotWithShape=\"1\">"
        f"<a:gsLst>{stops_xml}</a:gsLst>"
        "<a:path path=\"circle\">"
        f"<a:fillToRect l=\"{left}\" t=\"{top}\" r=\"{right}\" b=\"{bottom}\"/>"
        "</a:path>"
        "</a:gradFill>"
    )


def pattern_to_fill(paint: PatternPaint, *, opacity: float | None = None) -> str:
    preset = (paint.preset or "pct5").strip()
    foreground = (paint.foreground or "000000").lstrip("#").upper()
    background = (paint.background or "FFFFFF").lstrip("#").upper()
    if len(foreground) != 6:
        foreground = "000000"
    if len(background) != 6:
        background = "FFFFFF"

    fg_alpha = ""
    if opacity is not None and opacity < 0.999:
        alpha_val = int(round(max(0.0, min(1.0, opacity)) * 100000))
        fg_alpha = f'<a:alpha val="{alpha_val}"/>'

    return (
        f"<a:pattFill prst=\"{preset}\">"
        f"<a:fgClr><a:srgbClr val=\"{foreground}\">{fg_alpha}</a:srgbClr></a:fgClr>"
        f"<a:bgClr><a:srgbClr val=\"{background}\"/></a:bgClr>"
        "</a:pattFill>"
    )


def gradient_stop_xml(stop) -> str:
    position = int(max(0.0, min(1.0, stop.offset)) * 100000)
    alpha = int(max(0.0, min(1.0, stop.opacity)) * 100000)
    return (
        f'<a:gs pos="{position}">'
        f'<a:srgbClr val="{stop.rgb.upper()}"><a:alpha val="{alpha}"/></a:srgbClr>'
        "</a:gs>"
    )


__all__ = [
    "clip_rect_to_xml",
    "gradient_stop_xml",
    "linear_gradient_to_fill",
    "paint_to_fill",
    "pattern_to_fill",
    "radial_gradient_to_fill",
    "stroke_to_xml",
]
