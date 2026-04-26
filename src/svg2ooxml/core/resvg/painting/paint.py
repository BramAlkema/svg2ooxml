"""Paint resolution helpers for fill/stroke styles."""

from __future__ import annotations

import re
from dataclasses import dataclass

from svg2ooxml.color.parsers import parse_color as parse_global_color
from svg2ooxml.common.units import UnitConverter

from .colors import parse_rgb

_HEX_SHORT_RE = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX_FULL_RE = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGB_RE = re.compile(r"^rgb\(([^)]+)\)$")
_URL_RE = re.compile(r"url\((#[^)]+)\)")
_UNIT_CONVERTER = UnitConverter()
_LENGTH_CONTEXT = _UNIT_CONVERTER.create_context(
    width=0.0,
    height=0.0,
    font_size=12.0,
    root_font_size=12.0,
)

_FONT_FAMILY_ALIASES = {
    "sans-serif": "Arial",
    "serif": "Times New Roman",
    "monospace": "Courier New",
    "cursive": "Comic Sans MS",
    "fantasy": "Impact",
    "svgfreesansascii": "Arial",
}


@dataclass(frozen=True)
class Color:
    r: float
    g: float
    b: float
    a: float = 1.0


@dataclass(frozen=True)
class PaintReference:
    href: str


@dataclass(frozen=True)
class FillStyle:
    color: Color | None
    opacity: float
    reference: PaintReference | None


@dataclass(frozen=True)
class StrokeStyle:
    color: Color | None
    width: float | None
    opacity: float
    reference: PaintReference | None
    dash_array: list[float] | None = None
    dash_offset: float = 0.0
    linecap: str | None = None
    linejoin: str | None = None
    miterlimit: float | None = None


@dataclass(frozen=True)
class TextStyle:
    font_families: tuple[str, ...]
    font_size: float | None
    font_style: str | None
    font_weight: str | None
    text_decoration: str | None = None  # "underline", "line-through", "underline line-through", etc.
    letter_spacing: float | None = None  # in px (SVG user units)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _parse_component(value: str) -> int | None:
    """Parse an RGB color component from a string value.

    Supports both absolute values (0-255) and percentages (0%-100%).
    Uses round() for percentage conversion to preserve fidelity.

    Args:
        value: String like "255", "128", "50%", "99.9%"

    Returns:
        Integer 0-255, or None if parsing fails
    """
    value = value.strip()
    if value.endswith("%"):
        try:
            pct = float(value[:-1])
        except ValueError:
            return None
        # Use round() instead of int() for fidelity: 99.9% → 255, not 254
        return round(_clamp(pct / 100.0) * 255)
    try:
        return int(value)
    except ValueError:
        return None


def _parse_rgb_function(value: str) -> tuple[int, int, int] | None:
    match = _RGB_RE.match(value)
    if not match:
        return None
    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) != 3:
        return None
    comps = [_parse_component(part) for part in parts]
    if any(comp is None for comp in comps):
        return None
    return tuple(int(comp) for comp in comps)


def parse_color(value: str | None, opacity: float | None) -> Color | None:
    if value is None:
        return None
    value = value.strip()
    rgb: tuple[int, int, int] | None = None
    if match := _HEX_SHORT_RE.match(value):
        hex_value = match.group(1)
        rgb = tuple(int(ch * 2, 16) for ch in hex_value)
    elif _HEX_FULL_RE.match(value):
        rgb = parse_rgb(value)
    else:
        rgb = _parse_rgb_function(value)

    if rgb is not None:
        a = _clamp(opacity if opacity is not None else 1.0)
        return Color(r=rgb[0] / 255.0, g=rgb[1] / 255.0, b=rgb[2] / 255.0, a=a)

    try:
        global_color = parse_global_color(value)
    except ValueError:
        return None
    if global_color is None:
        return None

    a = _clamp(opacity if opacity is not None else 1.0) * float(getattr(global_color, "a", 1.0))
    return Color(r=global_color.r, g=global_color.g, b=global_color.b, a=a)


def resolve_fill(fill_value: str | None, fill_opacity: float | None, opacity: float | None) -> FillStyle:
    effective_opacity = (fill_opacity if fill_opacity is not None else 1.0) * (
        opacity if opacity is not None else 1.0
    )
    reference = None
    if fill_value:
        match = _URL_RE.match(fill_value.strip())
        if match:
            reference = PaintReference(href=match.group(1))
            color = None
        else:
            color = parse_color(fill_value, effective_opacity)
    else:
        color = None
    return FillStyle(color=color, opacity=effective_opacity, reference=reference)


def _parse_dash_array(value: str | None) -> list[float] | None:
    """Parse SVG stroke-dasharray into a list of floats."""
    if not value:
        return None
    token = value.strip()
    if not token or token.lower() == "none":
        return None
    numbers: list[float] = []
    for part in token.replace(",", " ").split():
        try:
            if part.endswith("%"):
                numbers.append(float(part[:-1]))
            else:
                numbers.append(_UNIT_CONVERTER.to_px(part, _LENGTH_CONTEXT, axis="font-size"))
        except ValueError:
            return None
    return numbers or None


def resolve_stroke(
    stroke_value: str | None,
    stroke_width: float | None,
    stroke_opacity: float | None,
    opacity: float | None,
    *,
    dasharray: str | None = None,
    dashoffset: float | None = None,
    linecap: str | None = None,
    linejoin: str | None = None,
    miterlimit: float | None = None,
) -> StrokeStyle:
    effective_opacity = (stroke_opacity if stroke_opacity is not None else 1.0) * (
        opacity if opacity is not None else 1.0
    )
    reference = None
    if stroke_value:
        match = _URL_RE.match(stroke_value.strip())
        if match:
            reference = PaintReference(href=match.group(1))
            color = None
        else:
            color = parse_color(stroke_value, effective_opacity)
    else:
        color = None
    width = stroke_width
    if width is None and (color is not None or reference is not None):
        width = 1.0
    return StrokeStyle(
        color=color,
        width=width,
        opacity=effective_opacity,
        reference=reference,
        dash_array=_parse_dash_array(dasharray),
        dash_offset=dashoffset or 0.0,
        linecap=linecap,
        linejoin=linejoin,
        miterlimit=miterlimit,
    )


def resolve_text_style(
    font_family: str | None,
    font_size: float | None,
    font_style: str | None,
    font_weight: str | None,
    text_decoration: str | None = None,
    letter_spacing: float | None = None,
) -> TextStyle:
    families: tuple[str, ...]
    if font_family:
        normalized: list[str] = []
        for part in font_family.split(","):
            token = part.strip().strip("'\"")
            if not token:
                continue
            mapped = _FONT_FAMILY_ALIASES.get(token.lower(), token)
            normalized.append(mapped)
        families = tuple(normalized)
    else:
        families = ()

    return TextStyle(
        font_families=families,
        font_size=font_size,
        font_style=font_style.strip() if font_style else None,
        font_weight=font_weight.strip() if font_weight else None,
        text_decoration=text_decoration.strip() if text_decoration else None,
        letter_spacing=letter_spacing,
    )
