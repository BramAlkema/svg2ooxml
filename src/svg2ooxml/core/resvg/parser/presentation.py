"""Presentation attribute normalization helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .tree import SvgNode


PRESENTATION_KEYS = {
    "fill",
    "stroke",
    "stroke-width",
    "fill-opacity",
    "stroke-opacity",
    "opacity",
    "transform",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
}


_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")


@dataclass(frozen=True)
class TransformCommand:
    name: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class Presentation:
    fill: Optional[str]
    stroke: Optional[str]
    stroke_width: Optional[float]
    fill_opacity: Optional[float]
    stroke_opacity: Optional[float]
    opacity: Optional[float]
    transform: tuple[TransformCommand, ...] | None
    font_family: Optional[str]
    font_size: Optional[float]
    font_style: Optional[str]
    font_weight: Optional[str]


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_positive(value: str | None) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value.strip().rstrip("%"))
    except ValueError:
        return None
    if number < 0:
        return None
    return number


def _parse_opacity(value: str | None) -> Optional[float]:
    number = _parse_optional_positive(value)
    if number is None:
        return None
    if number > 1:
        number = 1.0
    return number


def _parse_paint(value: str | None) -> Optional[str]:
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
        fill_opacity=_parse_opacity(attrs.get("fill-opacity")),
        stroke_opacity=_parse_opacity(attrs.get("stroke-opacity")),
        opacity=_parse_opacity(attrs.get("opacity")),
        transform=parse_transform(attrs.get("transform")),
        font_family=attrs.get("font-family"),
        font_size=_parse_optional_positive(attrs.get("font-size")),
        font_style=attrs.get("font-style"),
        font_weight=attrs.get("font-weight"),
    )
