"""Presentation attribute normalization helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import resolve_length_px
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
_DEFAULT_FONT_SIZE_PT = 12.0
_DEFAULT_FONT_SIZE_PX = _DEFAULT_FONT_SIZE_PT / _DEFAULT_UNITLESS_FONT_SCALE
_UNIT_CONVERTER = UnitConverter()


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
    font_size_scale: float | None = None


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


def _default_length_context():
    return _UNIT_CONVERTER.create_context(
        width=0.0,
        height=0.0,
        font_size=_DEFAULT_FONT_SIZE_PX,
        root_font_size=_DEFAULT_FONT_SIZE_PX,
    )


def _parse_length(value: str | None) -> float | None:
    if value is None:
        return None
    token = value.strip().lower()
    if not token or token in {"inherit", "initial", "unset"}:
        return None
    if token.endswith("%"):
        return _parse_float(token.rstrip("%"))
    resolved = resolve_length_px(
        token,
        _default_length_context(),
        axis="font-size",
        default=float("nan"),
        unit_converter=_UNIT_CONVERTER,
    )
    if resolved != resolved:
        return None
    return resolved


def _parse_positive_length(value: str | None) -> float | None:
    length = _parse_length(value)
    if length is None or length < 0:
        return None
    return length


def _parse_font_size(value: str | None) -> float | None:
    if value is None:
        return None
    token = value.strip().lower()
    if not token or token in {"inherit", "initial", "unset", "medium"}:
        return None
    if token.endswith("%"):
        try:
            return _DEFAULT_FONT_SIZE_PT * max(0.0, float(token[:-1])) / 100.0
        except ValueError:
            return None
    px = resolve_length_px(
        token,
        _default_length_context(),
        axis="font-size",
        default=float("nan"),
        unit_converter=_UNIT_CONVERTER,
    )
    if px != px:
        return None
    if px < 0:
        return None
    return px * _DEFAULT_UNITLESS_FONT_SCALE


def _parse_font_size_scale(value: str | None) -> float | None:
    if value is None:
        return None
    token = value.strip().lower()
    if not token.endswith("%"):
        return None
    try:
        return max(0.0, float(token[:-1])) / 100.0
    except ValueError:
        return None


def _parse_opacity(value: str | None) -> float | None:
    if value is None:
        return None
    return parse_opacity(value, default=1.0)


def _parse_letter_spacing(value: str | None) -> float | None:
    """Parse letter-spacing value to px. Handles 'normal', '0', '3px', '-1'."""
    if value is None:
        return None
    value = value.strip().lower()
    if value in {"normal", "inherit", "initial"}:
        return None
    resolved = resolve_length_px(
        value,
        _default_length_context(),
        axis="font-size",
        default=float("nan"),
        unit_converter=_UNIT_CONVERTER,
    )
    if resolved != resolved:
        return None
    return resolved


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
        args = parse_numeric_list(raw_args)
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
        stroke_width=_parse_positive_length(attrs.get("stroke-width")),
        stroke_dasharray=attrs.get("stroke-dasharray"),
        stroke_dashoffset=_parse_length(attrs.get("stroke-dashoffset")),
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
        font_size_scale=_parse_font_size_scale(attrs.get("font-size")),
    )
