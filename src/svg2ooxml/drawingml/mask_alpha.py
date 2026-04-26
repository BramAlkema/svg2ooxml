"""Mask opacity shortcuts for DrawingML writer."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    RadialGradientPaint,
    SolidPaint,
)


def apply_mask_alpha(element, alpha: float):
    """Multiply mask alpha into an element's fill and stroke paint opacities."""

    def _scale_stops(stops, a: float):
        return [replace(stop, opacity=stop.opacity * a) for stop in stops]

    fill = getattr(element, "fill", None)
    new_fill = fill
    if isinstance(fill, SolidPaint):
        new_fill = replace(fill, opacity=fill.opacity * alpha)
    elif isinstance(fill, (LinearGradientPaint, RadialGradientPaint)):
        new_fill = replace(fill, stops=_scale_stops(fill.stops, alpha))

    stroke = getattr(element, "stroke", None)
    new_stroke = stroke
    if stroke is not None:
        paint = getattr(stroke, "paint", None)
        if isinstance(paint, SolidPaint):
            new_stroke = replace(stroke, paint=replace(paint, opacity=paint.opacity * alpha))
        elif isinstance(paint, (LinearGradientPaint, RadialGradientPaint)):
            new_stroke = replace(stroke, paint=replace(paint, stops=_scale_stops(paint.stops, alpha)))

    try:
        element = replace(element, fill=new_fill, stroke=new_stroke, mask=None, mask_instance=None)
    except TypeError:
        try:
            element = replace(element, fill=new_fill, stroke=new_stroke)
        except TypeError:
            pass
    return element


__all__ = ["apply_mask_alpha"]
