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

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    to_string,
    solid_fill,
    no_fill,
)


def paint_to_fill(paint, *, opacity: float | None = None) -> str:
    if isinstance(paint, SolidPaint):
        effective = paint.opacity
        if opacity is not None:
            effective = max(0.0, min(1.0, effective * opacity))
        alpha = int(round(max(0.0, min(1.0, effective)) * 100000))
        return to_string(solid_fill(paint.rgb, alpha=alpha))
    if isinstance(paint, LinearGradientPaint):
        return linear_gradient_to_fill(paint)
    if isinstance(paint, RadialGradientPaint):
        return radial_gradient_to_fill(paint)
    if isinstance(paint, GradientPaintRef):
        # Create solidFill with schemeClr element
        fill = a_elem("solidFill")
        a_sub(fill, "schemeClr", val="phClr")
        return to_string(fill)
    if isinstance(paint, PatternPaint):
        return pattern_to_fill(paint, opacity=opacity)
    return to_string(no_fill())


def stroke_to_xml(stroke, metadata: Mapping[str, Any] | None = None) -> str:
    markers = {}
    if isinstance(metadata, Mapping):
        markers = metadata.get("markers") or {}

    head_xml, tail_xml = marker_end_elements(markers)

    if stroke is None or stroke.paint is None:
        # Create ln element with noFill
        ln = a_elem("ln")
        a_sub(ln, "noFill")
        # Add markers if present (parse XML strings to elements)
        from lxml import etree
        if tail_xml:
            # Add namespace declaration for parsing
            wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{tail_xml}</root>'
            temp = etree.fromstring(wrapped.encode('utf-8'))
            tail_elem = temp[0]
            ln.append(tail_elem)
        if head_xml:
            # Add namespace declaration for parsing
            wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{head_xml}</root>'
            temp = etree.fromstring(wrapped.encode('utf-8'))
            head_elem = temp[0]
            ln.append(head_elem)
        return to_string(ln)

    width_emu = max(1, px_to_emu(stroke.width))
    ln = a_elem("ln", w=width_emu)

    # Add fill based on paint type
    paint = stroke.paint
    if isinstance(paint, SolidPaint):
        color = paint.rgb.upper()
        alpha = int(round(max(0.0, min(1.0, paint.opacity)) * 100000))
        fill = solid_fill(color, alpha=alpha)
        ln.append(fill)
    elif isinstance(paint, PatternPaint):
        ln.append(_pattern_to_fill_elem(paint, opacity=stroke.opacity if hasattr(stroke, 'opacity') else None))
    elif isinstance(paint, LinearGradientPaint):
        ln.append(_linear_gradient_to_fill_elem(paint))
    elif isinstance(paint, RadialGradientPaint):
        ln.append(_radial_gradient_to_fill_elem(paint))
    elif isinstance(paint, GradientPaintRef):
        # Create solidFill with schemeClr element
        fill = a_elem("solidFill")
        a_sub(fill, "schemeClr", val="phClr")
        ln.append(fill)
    else:
        a_sub(ln, "noFill")

    # Add dash pattern
    dash_elem = _dash_elem(stroke.dash_array)
    if dash_elem is not None:
        ln.append(dash_elem)

    # Add cap style
    cap_map = {
        StrokeCap.ROUND: "rnd",
        StrokeCap.SQUARE: "sq",
        StrokeCap.BUTT: "flat",
    }
    ln.set("cap", cap_map.get(stroke.cap, "flat"))

    # Add join style
    if stroke.join == StrokeJoin.ROUND:
        a_sub(ln, "round")
    elif stroke.join == StrokeJoin.BEVEL:
        a_sub(ln, "bevel")
    else:
        if stroke.miter_limit and stroke.miter_limit > 0:
            a_sub(ln, "miter", lim=int(round(stroke.miter_limit * 1000)))
        else:
            a_sub(ln, "miter")

    # Add markers (parse XML strings to elements)
    from lxml import etree
    if tail_xml:
        # Add namespace declaration for parsing
        wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{tail_xml}</root>'
        temp = etree.fromstring(wrapped.encode('utf-8'))
        tail_elem = temp[0]
        ln.append(tail_elem)
    if head_xml:
        # Add namespace declaration for parsing
        wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{head_xml}</root>'
        temp = etree.fromstring(wrapped.encode('utf-8'))
        head_elem = temp[0]
        ln.append(head_elem)

    return to_string(ln)


def _dash_elem(dash_array: list[float] | None):
    """Create dash pattern element, or None if no dash."""
    if not dash_array:
        return None
    values = [abs(x) for x in dash_array if x > 0]
    if not values:
        return None
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
    return a_elem("prstDash", val=preset)


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

    # Build clipPath element
    clipPath = a_elem("clipPath")
    path = a_sub(clipPath, "path", clipFill="1")

    # moveTo
    moveTo = a_sub(path, "moveTo")
    a_sub(moveTo, "pt", x=x, y=y)

    # lnTo points
    lnTo1 = a_sub(path, "lnTo")
    a_sub(lnTo1, "pt", x=x2, y=y)

    lnTo2 = a_sub(path, "lnTo")
    a_sub(lnTo2, "pt", x=x2, y=y2)

    lnTo3 = a_sub(path, "lnTo")
    a_sub(lnTo3, "pt", x=x, y=y2)

    # close
    a_sub(path, "close")

    return to_string(clipPath)


def _linear_gradient_to_fill_elem(paint: LinearGradientPaint):
    """Create linear gradient fill element (internal helper)."""
    dx = paint.end[0] - paint.start[0]
    dy = paint.end[1] - paint.start[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        angle = 0.0
    else:
        radians = math.atan2(dy, dx)
        angle = (450 - math.degrees(radians)) % 360
    ang_val = int(round(angle * 60000))

    # Build gradient fill element
    gradFill = a_elem("gradFill", rotWithShape="1")

    # Add gradient stop list
    gsLst = a_sub(gradFill, "gsLst")
    for stop in paint.stops:
        gsLst.append(_gradient_stop_elem(stop))

    # Add linear gradient definition
    a_sub(gradFill, "lin", ang=ang_val, scaled="0")

    return gradFill


def linear_gradient_to_fill(paint: LinearGradientPaint) -> str:
    """Create linear gradient fill XML string."""
    return to_string(_linear_gradient_to_fill_elem(paint))


def _radial_gradient_to_fill_elem(paint: RadialGradientPaint):
    """Create radial gradient fill element (internal helper)."""
    cx, cy = paint.center
    radius = max(paint.radius, 1e-6)
    left = max(0, min(100000, int(round(max(0.0, (cx - radius)) * 100000))))
    top = max(0, min(100000, int(round(max(0.0, (cy - radius)) * 100000))))
    right = max(0, min(100000, int(round(max(0.0, (1.0 - (cx + radius))) * 100000))))
    bottom = max(0, min(100000, int(round(max(0.0, (1.0 - (cy + radius))) * 100000))))

    # Build gradient fill element
    gradFill = a_elem("gradFill", rotWithShape="1")

    # Add gradient stop list
    gsLst = a_sub(gradFill, "gsLst")
    for stop in paint.stops:
        gsLst.append(_gradient_stop_elem(stop))

    # Add radial gradient path
    path = a_sub(gradFill, "path", path="circle")
    a_sub(path, "fillToRect", l=left, t=top, r=right, b=bottom)

    return gradFill


def radial_gradient_to_fill(paint: RadialGradientPaint) -> str:
    """Create radial gradient fill XML string."""
    return to_string(_radial_gradient_to_fill_elem(paint))


def _pattern_to_fill_elem(paint: PatternPaint, *, opacity: float | None = None):
    """Create pattern fill element (internal helper)."""
    preset = (paint.preset or "pct5").strip()
    foreground = (paint.foreground or "000000").lstrip("#").upper()
    background = (paint.background or "FFFFFF").lstrip("#").upper()
    if len(foreground) != 6:
        foreground = "000000"
    if len(background) != 6:
        background = "FFFFFF"

    # Build pattern fill element
    pattFill = a_elem("pattFill", prst=preset)

    # Foreground color
    fgClr = a_sub(pattFill, "fgClr")
    fg_srgbClr = a_sub(fgClr, "srgbClr", val=foreground)
    if opacity is not None and opacity < 0.999:
        alpha_val = int(round(max(0.0, min(1.0, opacity)) * 100000))
        a_sub(fg_srgbClr, "alpha", val=alpha_val)

    # Background color
    bgClr = a_sub(pattFill, "bgClr")
    a_sub(bgClr, "srgbClr", val=background)

    return pattFill


def pattern_to_fill(paint: PatternPaint, *, opacity: float | None = None) -> str:
    """Create pattern fill XML string."""
    return to_string(_pattern_to_fill_elem(paint, opacity=opacity))


def gradient_stop_xml(stop) -> str:
    """Create gradient stop XML string.

    Returns XML string for backward compatibility with existing code.
    """
    gs_elem = _gradient_stop_elem(stop)
    return to_string(gs_elem)


def _gradient_stop_elem(stop):
    """Create gradient stop element.

    Internal helper that returns lxml element for efficient composition.
    """
    position = int(max(0.0, min(1.0, stop.offset)) * 100000)
    alpha = int(max(0.0, min(1.0, stop.opacity)) * 100000)

    gs = a_elem("gs", pos=position)
    srgbClr = a_sub(gs, "srgbClr", val=stop.rgb.upper())
    a_sub(srgbClr, "alpha", val=alpha)

    return gs


__all__ = [
    "clip_rect_to_xml",
    "gradient_stop_xml",
    "linear_gradient_to_fill",
    "paint_to_fill",
    "pattern_to_fill",
    "radial_gradient_to_fill",
    "stroke_to_xml",
]
