"""Presentation attribute normalization helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from svg2ooxml.common.units.scalars import PX_PER_INCH

from .tree import SvgNode

PRESENTATION_KEYS = {
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "fill-opacity",
    "stroke-opacity",
    "opacity",
    "transform",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-decoration",
    "letter-spacing",
}


_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_DEFAULT_UNITLESS_FONT_SCALE = float(
    os.getenv("SVG2OOXML_UNITLESS_FONT_SCALE", str(72.0 / PX_PER_INCH))
)


@dataclass(frozen=True)
class TransformCommand:
    name: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class Presentation:
    fill: str | None
    stroke: str | None
    stroke_width: float | None
    stroke_dasharray: str | None
    stroke_dashoffset: float | None
    stroke_linecap: str | None
    stroke_linejoin: str | None
    stroke_miterlimit: float | None
    fill_opacity: float | None
    stroke_opacity: float | None
    opacity: float | None
    transform: tuple[TransformCommand, ...] | None
    font_family: str | None
    font_size: float | None
    font_style: str | None
    font_weight: str | None
    text_decoration: str | None = None
    letter_spacing: float | None = None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_positive(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value.strip().rstrip("%"))
    except ValueError:
        return None
    if number < 0:
        return None
    return number


def _parse_font_size(value: str | None) -> float | None:
    number = _parse_optional_positive(value)
    if number is None:
        return None
    return number * _DEFAULT_UNITLESS_FONT_SCALE


def _parse_opacity(value: str | None) -> float | None:
    number = _parse_optional_positive(value)
    if number is None:
        return None
    if number > 1:
        number = 1.0
    return number


def _parse_letter_spacing(value: str | None) -> float | None:
    """Parse letter-spacing value to px. Handles 'normal', '0', '3px', '-1'."""
    if value is None:
        return None
    value = value.strip().lower()
    if value in {"normal", "inherit", "initial"}:
        return None
    # Strip 'px' suffix if present
    if value.endswith("px"):
        value = value[:-2].strip()
    try:
        return float(value)
    except ValueError:
        return None


def _parse_paint(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value.lower() in {"none", "transparent"}:
        return None
    return value


def parse_transform(value: str | None) -> tuple[TransformCommand, ...] | None:
    if not value:
        return None
    commands: list[TransformCommand] = []
    for match in _TRANSFORM_RE.finditer(value):
        name = match.group(1)
        raw_args = match.group(2)
        args: list[float] = []
        for chunk in re.split(r"[\s,]+", raw_args.strip()):
            if not chunk:
                continue
            try:
                args.append(float(chunk))
            except ValueError:
                continue
        commands.append(TransformCommand(name=name, values=tuple(args)))
    return tuple(commands) if commands else None


def collect_presentation(node: SvgNode) -> Presentation:
    attrs = {
        key: node.attributes.get(key)
        for key in PRESENTATION_KEYS
        if key in node.attributes
    }

    for key, value in node.styles.items():
        if key in PRESENTATION_KEYS:
            attrs[key] = value

    return Presentation(
        fill=_parse_paint(attrs.get("fill")),
        stroke=_parse_paint(attrs.get("stroke")),
        stroke_width=_parse_optional_positive(attrs.get("stroke-width")),
        stroke_dasharray=attrs.get("stroke-dasharray"),
        stroke_dashoffset=_parse_float(attrs.get("stroke-dashoffset") or ""),
        stroke_linecap=attrs.get("stroke-linecap"),
        stroke_linejoin=attrs.get("stroke-linejoin"),
        stroke_miterlimit=_parse_optional_positive(attrs.get("stroke-miterlimit")),
        fill_opacity=_parse_opacity(attrs.get("fill-opacity")),
        stroke_opacity=_parse_opacity(attrs.get("stroke-opacity")),
        opacity=_parse_opacity(attrs.get("opacity")),
        transform=parse_transform(attrs.get("transform")),
        font_family=attrs.get("font-family"),
        font_size=_parse_font_size(attrs.get("font-size")),
        font_style=attrs.get("font-style"),
        font_weight=attrs.get("font-weight"),
        text_decoration=attrs.get("text-decoration"),
        letter_spacing=_parse_letter_spacing(attrs.get("letter-spacing")),
    )
