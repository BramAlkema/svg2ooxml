"""Stateless helpers for :mod:`shape_renderer`."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.color.utils import rgb_channels_to_hex
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import RadialGradientPaint, SolidPaint
from svg2ooxml.ir.scene import Image
from svg2ooxml.ir.shapes import Rectangle


def is_stroke_first(metadata: dict[str, object]) -> bool:
    """Return True when paint-order puts stroke before fill."""
    po = metadata.get("paint_order")
    if not isinstance(po, str):
        return False
    tokens = po.lower().split()
    try:
        si = tokens.index("stroke")
        fi = tokens.index("fill")
        return si < fi
    except ValueError:
        return tokens[0] == "stroke" if tokens else False


def has_fill_and_stroke(element) -> bool:
    return (
        getattr(element, "fill", None) is not None
        and getattr(element, "stroke", None) is not None
    )


def intersect_rects(a: Rect, b: Rect) -> Rect | None:
    """Return the intersection of two Rects, or None if they don't overlap."""
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.width, b.x + b.width)
    y2 = min(a.y + a.height, b.y + b.height)
    if x2 <= x1 or y2 <= y1:
        return None
    return Rect(x1, y1, x2 - x1, y2 - y1)


def apply_clip_bounds(element, metadata: dict[str, object]):
    """Intersect element bounds with clip bounds for xfrm approximation."""
    if not isinstance(metadata, dict):
        return element
    clip = metadata.pop("_clip_bounds", None)
    if not isinstance(clip, Rect):
        return element

    bbox = getattr(element, "bbox", None)
    if not isinstance(bbox, Rect):
        return element

    clipped = intersect_rects(bbox, clip)
    if clipped is None or clipped == bbox:
        return element

    if isinstance(element, Rectangle):
        return replace(element, bounds=clipped)

    if isinstance(element, Image):
        w = max(bbox.width, 1e-9)
        h = max(bbox.height, 1e-9)
        l_pct = int(max(0.0, (clipped.x - bbox.x) / w) * 100_000)
        t_pct = int(max(0.0, (clipped.y - bbox.y) / h) * 100_000)
        r_pct = int(
            max(0.0, ((bbox.x + bbox.width) - (clipped.x + clipped.width)) / w)
            * 100_000
        )
        b_pct = int(
            max(0.0, ((bbox.y + bbox.height) - (clipped.y + clipped.height)) / h)
            * 100_000
        )
        new_elem = replace(
            element,
            origin=Point(clipped.x, clipped.y),
            size=Rect(0.0, 0.0, clipped.width, clipped.height),
        )
        if any((l_pct, t_pct, r_pct, b_pct)):
            new_elem.metadata["_src_rect"] = (l_pct, t_pct, r_pct, b_pct)
        return new_elem

    return element


def average_gradient_paint(paint: RadialGradientPaint) -> SolidPaint:
    if not paint.stops:
        return SolidPaint(rgb="000000", opacity=1.0)
    total_r = total_g = total_b = total_a = 0.0
    for stop in paint.stops:
        token = (stop.rgb or "000000").strip().lstrip("#")
        if len(token) != 6:
            token = "000000"
        try:
            total_r += int(token[0:2], 16)
            total_g += int(token[2:4], 16)
            total_b += int(token[4:6], 16)
        except ValueError:
            total_r += 0.0
            total_g += 0.0
            total_b += 0.0
        total_a += float(stop.opacity)
    count = max(len(paint.stops), 1)
    avg_r = int(round(total_r / count))
    avg_g = int(round(total_g / count))
    avg_b = int(round(total_b / count))
    avg_opacity = total_a / count
    return SolidPaint(
        rgb=rgb_channels_to_hex(avg_r, avg_g, avg_b, scale="byte"),
        opacity=avg_opacity,
    )


def is_invalid_custom_effect_xml(
    xml: str,
    *,
    invalid_substrings: tuple[str, ...],
) -> bool:
    lowered = xml.lower()
    stripped = lowered.lstrip()
    if stripped.startswith("<a:solidfill") or stripped.startswith("<solidfill"):
        return True
    return any(marker in lowered for marker in invalid_substrings)


__all__ = [
    "apply_clip_bounds",
    "average_gradient_paint",
    "has_fill_and_stroke",
    "intersect_rects",
    "is_invalid_custom_effect_xml",
    "is_stroke_first",
]
