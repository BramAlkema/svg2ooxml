"""Shared parsing and inheritance helpers for the simplified usvg tree."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.units.lengths import parse_number_or_percent

from .geometry.matrix import matrix_from_commands
from .painting.gradients import PatternPaint
from .painting.paint import FillStyle, StrokeStyle, TextStyle
from .parser.presentation import parse_transform
from .parser.tree import SvgNode

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def strip_namespace(tag: Any) -> str:
    tag_str = str(tag)
    if tag_str.startswith("{" + SVG_NAMESPACE + "}"):
        return tag_str[len(SVG_NAMESPACE) + 2 :]
    return tag_str


def gather_text(node: SvgNode) -> str | None:
    parts: list[str] = []

    def walk(current: SvgNode) -> None:
        if current.text:
            parts.append(current.text.strip())
        for child in current.children:
            walk(child)
            if child.tail:
                parts.append(child.tail.strip())

    walk(node)
    content = " ".join(filter(None, parts))
    return content or None


def extract_href(attributes: dict[str, str]) -> str | None:
    for key in ("href", "{http://www.w3.org/1999/xlink}href"):
        if key in attributes:
            return attributes[key]
    return None


def parse_number(value: str | None, default: float = 0.0) -> float:
    return parse_number_or_percent(value, default)


def parse_points(raw: str) -> tuple[float, ...]:
    if not raw:
        return ()
    return tuple(parse_numeric_list(raw))


def parse_view_box(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    numbers = parse_points(raw)
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def parse_pattern(node: SvgNode) -> PatternPaint:
    attributes = node.attributes
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("patternTransform")))
    href = extract_href(attributes)
    specified = tuple(
        key
        for key in (
            "x",
            "y",
            "width",
            "height",
            "patternUnits",
            "patternContentUnits",
            "patternTransform",
        )
        if key in attributes
    )
    return PatternPaint(
        x=parse_number(attributes.get("x"), 0.0),
        y=parse_number(attributes.get("y"), 0.0),
        width=parse_number(attributes.get("width"), 0.0),
        height=parse_number(attributes.get("height"), 0.0),
        units=attributes.get("patternUnits") or "objectBoundingBox",
        content_units=attributes.get("patternContentUnits") or "userSpaceOnUse",
        transform=transform_matrix,
        href=href,
        specified=specified,
    )


def inherit_fill(fill: FillStyle | None, parent_fill: FillStyle | None) -> FillStyle | None:
    if fill is not None:
        return fill
    return replace(parent_fill) if parent_fill is not None else None


def inherit_stroke(stroke: StrokeStyle | None, parent_stroke: StrokeStyle | None) -> StrokeStyle | None:
    if stroke is not None:
        return stroke
    return replace(parent_stroke) if parent_stroke is not None else None


def inherit_text(
    text_style: TextStyle | None,
    parent_style: TextStyle | None,
) -> TextStyle | None:
    if text_style is None:
        return replace(parent_style) if parent_style is not None else None
    if parent_style is None:
        return text_style
    return TextStyle(
        font_families=text_style.font_families or parent_style.font_families,
        font_size=text_style.font_size if text_style.font_size is not None else parent_style.font_size,
        font_style=text_style.font_style or parent_style.font_style,
        font_weight=text_style.font_weight or parent_style.font_weight,
        text_decoration=text_style.text_decoration or parent_style.text_decoration,
        letter_spacing=(
            text_style.letter_spacing
            if text_style.letter_spacing is not None
            else parent_style.letter_spacing
        ),
    )


__all__ = [
    "SVG_NAMESPACE",
    "extract_href",
    "gather_text",
    "inherit_fill",
    "inherit_stroke",
    "inherit_text",
    "parse_number",
    "parse_pattern",
    "parse_points",
    "parse_view_box",
    "strip_namespace",
]
