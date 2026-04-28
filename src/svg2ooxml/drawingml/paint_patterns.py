"""Pattern paint conversion helpers for DrawingML."""

from __future__ import annotations

from typing import Any

from svg2ooxml.common.conversions.opacity import clamp_opacity, opacity_to_ppt
from svg2ooxml.common.conversions.scale import PPT_SCALE
from svg2ooxml.core.resvg.geometry.matrix_bridge import matrix_to_tuple
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, color_choice, to_string
from svg2ooxml.ir.paint import PatternPaint

_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _as_pattern_affine(
    transform: Any,
) -> tuple[float, float, float, float, float, float] | None:
    """Extract SVG affine matrix values from a transform."""
    if transform is None:
        return None
    try:
        return matrix_to_tuple(transform)
    except (TypeError, ValueError):
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
    """Map simple pattern transforms to DrawingML tile attrs."""
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
    """Create pattern fill element."""
    if paint.tile_relationship_id:
        blipFill = a_elem("blipFill", dpi="0", rotWithShape="1")
        blip = a_sub(blipFill, "blip")
        blip.set(f"{{{_RELS_NS}}}embed", paint.tile_relationship_id)
        tile_opacity = clamp_opacity(opacity) if opacity is not None else None
        if tile_opacity is not None and tile_opacity < 0.999:
            alphaModFix = a_sub(blip, "alphaModFix")
            alphaModFix.set("amt", str(opacity_to_ppt(tile_opacity)))
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

    pattFill = a_elem("pattFill", prst=preset)

    fgClr = a_sub(pattFill, "fgClr")
    fgClr.append(
        color_choice(
            foreground,
            alpha=(
                opacity_to_ppt(opacity)
                if opacity is not None and opacity < 0.999
                else None
            ),
            theme_color=paint.foreground_theme_color,
        )
    )

    background_opacity = clamp_opacity(paint.background_opacity)
    if opacity is not None:
        background_opacity = clamp_opacity(background_opacity * opacity)
    bgClr = a_sub(pattFill, "bgClr")
    bgClr.append(
        color_choice(
            background,
            alpha=(
                opacity_to_ppt(background_opacity)
                if background_opacity < 0.999
                else None
            ),
            theme_color=paint.background_theme_color,
        )
    )

    return pattFill


def pattern_to_fill(paint: PatternPaint, *, opacity: float | None = None) -> str:
    """Create pattern fill XML string."""
    return to_string(_pattern_to_fill_elem(paint, opacity=opacity))


__all__ = [
    "_as_pattern_affine",
    "_clamp_int32",
    "_pattern_to_fill_elem",
    "_tile_attrs_from_pattern_transform",
    "pattern_to_fill",
]
