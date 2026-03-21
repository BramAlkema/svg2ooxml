"""Paint/stroke conversion helpers for DrawingML writer."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.conversions.scale import PPT_SCALE, position_to_ppt
from svg2ooxml.drawingml.generator import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    color_choice,
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


def _normalize_gradient_units(paint, shape_bbox):
    """Convert userSpaceOnUse gradient coordinates to bbox-relative [0,1].

    DrawingML gradients are always relative to the shape bounding box.
    When ``gradient_units`` is ``"userSpaceOnUse"``, the coordinates are
    in absolute SVG user units and must be normalised.

    Returns the paint unchanged if units are objectBoundingBox (default)
    or if no bbox is available.
    """
    from dataclasses import replace

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
        r = paint.radius
        kwargs: dict[str, Any] = {
            "center": ((cx - bx) / bw, (cy - by) / bh),
            "radius": r / max(bw, bh),
            "gradient_units": "objectBoundingBox",
        }
        if paint.focal_point is not None:
            fx, fy = paint.focal_point
            kwargs["focal_point"] = ((fx - bx) / bw, (fy - by) / bh)
        return replace(paint, **kwargs)

    return paint


def paint_to_fill(paint, *, opacity: float | None = None, shape_bbox=None) -> str:
    if isinstance(paint, SolidPaint):
        effective = paint.opacity
        if opacity is not None:
            effective = max(0.0, min(1.0, effective * opacity))
        alpha = opacity_to_ppt(effective)
        return to_string(solid_fill(paint.rgb, alpha=alpha, theme_color=paint.theme_color))
    if isinstance(paint, LinearGradientPaint):
        paint = _normalize_gradient_units(paint, shape_bbox)
        return linear_gradient_to_fill(paint)
    if isinstance(paint, RadialGradientPaint):
        paint = _normalize_gradient_units(paint, shape_bbox)
        return radial_gradient_to_fill(paint)
    if isinstance(paint, GradientPaintRef):
        # Create solidFill with schemeClr element
        fill = a_elem("solidFill")
        fill.append(scheme_color("phClr"))
        return to_string(fill)
    if isinstance(paint, PatternPaint):
        return pattern_to_fill(paint, opacity=opacity)
    return to_string(no_fill())


def stroke_to_xml(stroke, metadata: Mapping[str, Any] | None = None) -> str:
    markers = {}
    marker_profiles = {}
    if isinstance(metadata, Mapping):
        markers = metadata.get("markers") or {}
        marker_profiles = metadata.get("marker_profiles") or {}

    head_elem, tail_elem = marker_end_elements(markers, marker_profiles=marker_profiles)

    if stroke is None or stroke.paint is None:
        # Create ln element with noFill
        ln = a_elem("ln")
        a_sub(ln, "noFill")
        if head_elem is not None:
            ln.append(head_elem)
        if tail_elem is not None:
            ln.append(tail_elem)
        return to_string(ln)

    width_emu = max(1, px_to_emu(stroke.width))
    ln = a_elem("ln", w=width_emu)

    # Add fill based on paint type
    paint = stroke.paint
    if isinstance(paint, SolidPaint):
        color = paint.rgb.upper()
        alpha = opacity_to_ppt(paint.opacity)
        fill = solid_fill(color, alpha=alpha, theme_color=paint.theme_color)
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
        fill.append(scheme_color("phClr"))
        ln.append(fill)
    else:
        a_sub(ln, "noFill")

    # Add dash pattern
    dash_elem = _dash_elem(stroke.dash_array, stroke.width, dash_offset=stroke.dash_offset)
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

    # Add markers if present — ECMA-376 requires headEnd before tailEnd
    if head_elem is not None:
        ln.append(head_elem)
    if tail_elem is not None:
        ln.append(tail_elem)

    return to_string(ln)


def _dash_elem(
    dash_array: list[float] | None,
    stroke_width: float = 1.0,
    *,
    dash_offset: float = 0.0,
    ppt_compat: bool = False,
):
    """Create dash pattern element using custDash for precise rendering.

    Converts SVG dash-array values (in user units) to DrawingML custDash
    with ds (dash-stop) elements.

    *dash_offset* shifts the start of the dash pattern by consuming from
    the leading entries, matching SVG ``stroke-dashoffset`` semantics.

    When ``ppt_compat`` is False (default, spec-compliant): ``d`` and ``sp``
    are ST_PositivePercentage — percentage of line width (100000 = 100%).

    When ``ppt_compat`` is True: uses absolute hundredths-of-a-point values,
    matching PowerPoint's "Convert to Shape" behavior.
    """
    if not dash_array:
        return None
    values = [abs(x) for x in dash_array if x > 0]
    if not values:
        return None

    # SVG spec: odd-length arrays are doubled to make even pairs
    if len(values) % 2 == 1:
        values = values + values

    # Apply dash offset by rotating the pattern
    if dash_offset and values:
        values = _apply_dash_offset(values, dash_offset)

    width = max(stroke_width, 0.01)  # avoid division by zero

    cust = a_elem("custDash")
    for i in range(0, len(values), 2):
        dash_px = values[i]
        space_px = values[i + 1] if i + 1 < len(values) else 0
        if ppt_compat:
            # Absolute hundredths-of-a-point (px * 72/96 * 100000)
            d_val = max(0, int(round(dash_px * 75000)))
            sp_val = max(0, int(round(space_px * 75000)))
        else:
            # Spec-compliant: percentage of line width (100000 = 100%)
            d_val = max(0, int(round(dash_px / width * 100000)))
            sp_val = max(0, int(round(space_px / width * 100000)))
        if d_val == 0 and sp_val == 0:
            continue
        a_sub(cust, "ds", d=d_val, sp=sp_val)

    return cust if len(cust) > 0 else None


def _apply_dash_offset(values: list[float], offset: float) -> list[float]:
    """Rotate a dash/gap array by *offset* user units.

    Positive offset shifts the pattern start forward (consumes from the
    leading dash).  Negative offset shifts backward.  The result always
    has even length (dash, gap, dash, gap, ...).

    Algorithm: find the split point, take the remainder of the split entry
    as the new head, append the full cycle, then handle the dash/gap
    alignment at the boundary.
    """
    pattern_length = sum(values)
    if pattern_length <= 0:
        return values

    offset = offset % pattern_length
    if offset < 1e-9:
        return values

    # Find which entry the offset falls into
    consumed = 0.0
    split_idx = 0
    for i, v in enumerate(values):
        if consumed + v > offset + 1e-9:
            split_idx = i
            break
        consumed += v
    else:
        return values

    into = offset - consumed
    remainder = values[split_idx] - into

    # Rotate: [partial_split_entry, entries_after..., entries_before..., consumed_portion]
    after = list(values[split_idx + 1:])
    before = list(values[:split_idx])
    rotated = [remainder] + after + before + [into]

    # rotated[0] has the same dash/gap type as values[split_idx].
    # If split_idx is even → starts on dash (correct).
    # If split_idx is odd → starts on gap — prepend a zero-length dash.
    if split_idx % 2 == 1:
        rotated = [0.0] + rotated

    # Ensure even length (append zero-gap if needed)
    if len(rotated) % 2 == 1:
        rotated.append(0.0)

    return rotated


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


def _expand_stops_for_spread(stops, spread_method: str | None):
    """Expand gradient stops for reflect/repeat spread methods.

    DrawingML only supports 'pad' natively, so we simulate reflect/repeat
    by duplicating stops across the [0, 1] range.  The original stops are
    assumed to define one period of the gradient.

    Returns a new list of GradientStop-like objects with expanded offsets.
    """
    if not spread_method or spread_method == "pad" or len(stops) < 2:
        return stops

    from svg2ooxml.ir.paint import GradientStop

    # Determine the gradient extent from first to last stop
    start_off = stops[0].offset
    end_off = stops[-1].offset
    extent = end_off - start_off
    if extent < 1e-6:
        return stops

    # How many repetitions we need to fill [0, 1]
    reps_needed = max(1, int(math.ceil(1.0 / extent)))
    # Cap at a reasonable number to avoid huge stop lists
    reps_needed = min(reps_needed, 10)

    expanded = []
    for rep in range(reps_needed):
        if spread_method == "reflect" and rep % 2 == 1:
            # Reversed stops for reflection
            for stop in reversed(stops):
                new_offset = rep * extent + (end_off - stop.offset)
                if new_offset > 1.0 + 1e-6:
                    continue
                expanded.append(GradientStop(
                    offset=min(1.0, max(0.0, new_offset)),
                    rgb=stop.rgb,
                    opacity=stop.opacity,
                    theme_color=stop.theme_color,
                ))
        else:
            for stop in stops:
                new_offset = rep * extent + (stop.offset - start_off)
                if new_offset > 1.0 + 1e-6:
                    continue
                expanded.append(GradientStop(
                    offset=min(1.0, max(0.0, new_offset)),
                    rgb=stop.rgb,
                    opacity=stop.opacity,
                    theme_color=stop.theme_color,
                ))

    # Deduplicate stops at same offset (keep first)
    seen_offsets: set[int] = set()
    deduped = []
    for s in expanded:
        key = round(s.offset * 100000)
        if key not in seen_offsets:
            seen_offsets.add(key)
            deduped.append(s)

    return deduped if deduped else stops


def _linear_gradient_to_fill_elem(paint: LinearGradientPaint):
    """Create linear gradient fill element (internal helper)."""
    dx = paint.end[0] - paint.start[0]
    dy = paint.end[1] - paint.start[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        angle = 0.0
    else:
        radians = math.atan2(dy, dx)
        angle = (450 - math.degrees(radians)) % 360
    ang_val = degrees_to_ppt(angle)

    stops = _expand_stops_for_spread(paint.stops, paint.spread_method)

    # Build gradient fill element
    gradFill = a_elem("gradFill", rotWithShape="1")

    # Add gradient stop list
    gsLst = a_sub(gradFill, "gsLst")
    for stop in stops:
        gsLst.append(_gradient_stop_elem(stop))

    # Add linear gradient definition
    a_sub(gradFill, "lin", ang=ang_val, scaled="0")

    return gradFill


def linear_gradient_to_fill(paint: LinearGradientPaint) -> str:
    """Create linear gradient fill XML string."""
    return to_string(_linear_gradient_to_fill_elem(paint))


def _radial_gradient_to_fill_elem(paint: RadialGradientPaint):
    """Create radial gradient fill element (internal helper).

    Maps SVG radial gradient (cx, cy, r, fx, fy) to DrawingML ``fillToRect``.
    When a focal point is provided and differs from the center, the gradient
    circle is shifted towards the focal point to approximate the SVG rendering.
    """
    cx, cy = paint.center
    radius = max(paint.radius, 1e-6)

    # Apply focal point offset: shift the gradient center toward (fx, fy)
    # to approximate SVG's focal-point asymmetry.
    if paint.focal_point is not None:
        fx, fy = paint.focal_point
        # Blend center towards focal point (50% shift gives a visible
        # approximation without moving the circle edge off the shape).
        cx = cx + (fx - cx) * 0.5
        cy = cy + (fy - cy) * 0.5

    left = position_to_ppt(max(0.0, cx - radius))
    top = position_to_ppt(max(0.0, cy - radius))
    right = position_to_ppt(max(0.0, 1.0 - (cx + radius)))
    bottom = position_to_ppt(max(0.0, 1.0 - (cy + radius)))

    stops = _expand_stops_for_spread(paint.stops, paint.spread_method)

    # Build gradient fill element
    gradFill = a_elem("gradFill", rotWithShape="1")

    # Add gradient stop list
    gsLst = a_sub(gradFill, "gsLst")
    for stop in stops:
        gsLst.append(_gradient_stop_elem(stop))

    # Add radial gradient path
    path = a_sub(gradFill, "path", path="circle")
    a_sub(path, "fillToRect", l=left, t=top, r=right, b=bottom)

    return gradFill


def radial_gradient_to_fill(paint: RadialGradientPaint) -> str:
    """Create radial gradient fill XML string."""
    return to_string(_radial_gradient_to_fill_elem(paint))


_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _as_pattern_affine(transform: Any) -> tuple[float, float, float, float, float, float] | None:
    """Extract SVG affine matrix values (a,b,c,d,e,f) from a 3x3 transform."""
    if transform is None:
        return None
    try:
        return (
            float(transform[0][0]),
            float(transform[1][0]),
            float(transform[0][1]),
            float(transform[1][1]),
            float(transform[0][2]),
            float(transform[1][2]),
        )
    except (IndexError, TypeError, ValueError):
        return None


def _clamp_int32(value: int) -> int:
    return max(-(2**31), min(2**31 - 1, value))


_DEFAULT_TILE_ATTRS: dict[str, str] = {
    "tx": "0",
    "ty": "0",
    "sx": str(PPT_SCALE),
    "sy": str(PPT_SCALE),
    "flip": "none",
    "algn": "tl",
}


def _tile_attrs_from_pattern_transform(transform: Any) -> dict[str, str]:
    """Map simple pattern transforms to DrawingML tile attrs.

    Supports translate/scale/mirror matrices. Rotation/skew matrices are
    intentionally ignored to avoid applying an incomplete transform.
    """
    affine = _as_pattern_affine(transform)
    if affine is None:
        return dict(_DEFAULT_TILE_ATTRS)

    a, b, c, d, e, f = affine
    tolerance = 1e-6
    if abs(b) > tolerance or abs(c) > tolerance:
        return dict(_DEFAULT_TILE_ATTRS)

    sx = max(1, int(round(abs(a) * PPT_SCALE)))
    sy = max(1, int(round(abs(d) * PPT_SCALE)))
    tx = int(round(e * PPT_SCALE))
    ty = int(round(f * PPT_SCALE))

    flip = "none"
    if a < -tolerance and d < -tolerance:
        flip = "xy"
    elif a < -tolerance:
        flip = "x"
    elif d < -tolerance:
        flip = "y"

    return {
        "tx": str(_clamp_int32(tx)),
        "ty": str(_clamp_int32(ty)),
        "sx": str(_clamp_int32(sx)),
        "sy": str(_clamp_int32(sy)),
        "flip": flip,
        "algn": "tl",
    }


def _pattern_to_fill_elem(paint: PatternPaint, *, opacity: float | None = None):
    """Create pattern fill element (internal helper).

    When the pattern has a rasterized tile image registered as media
    (tile_relationship_id set), generates blipFill with tile mode.
    Otherwise falls back to pattFill with preset or solidFill.
    """
    # Rasterized tile path: blipFill with tile mode
    if paint.tile_relationship_id:
        blipFill = a_elem("blipFill", dpi="0", rotWithShape="1")
        blip = a_sub(blipFill, "blip")
        blip.set(f"{{{_RELS_NS}}}embed", paint.tile_relationship_id)
        if opacity is not None and opacity < 0.999:
            alphaModFix = a_sub(blip, "alphaModFix")
            alphaModFix.set("amt", str(opacity_to_ppt(opacity)))
        tile_attrs = _tile_attrs_from_pattern_transform(paint.transform)
        a_sub(blipFill, "tile", **tile_attrs)
        return blipFill

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
    fgClr.append(
        color_choice(
            foreground,
            alpha=opacity_to_ppt(opacity) if opacity is not None and opacity < 0.999 else None,
            theme_color=paint.foreground_theme_color,
        )
    )

    # Background color
    bgClr = a_sub(pattFill, "bgClr")
    bgClr.append(color_choice(background, theme_color=paint.background_theme_color))

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
    position = position_to_ppt(stop.offset)
    alpha = opacity_to_ppt(stop.opacity)

    gs = a_elem("gs", pos=position)
    gs.append(color_choice(stop.rgb, alpha=alpha, theme_color=stop.theme_color))

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
