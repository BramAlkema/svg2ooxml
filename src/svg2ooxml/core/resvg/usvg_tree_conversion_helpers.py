"""Shared helper operations for parser-to-usvg conversion."""

from __future__ import annotations

from svg2ooxml.common.units.conversion import ConversionContext

from .parser.options import Options
from .parser.tree import SvgNode
from .usvg_nodes import BaseNode
from .usvg_tree_conversion_types import NodeConverter
from .viewport_units import parse_length_px


def convert_children(
    node: SvgNode,
    parent: BaseNode,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> list[BaseNode]:
    return [convert_child(child, parent, options, context) for child in node.children]


def parse_positioned_size(
    attributes: dict[str, str],
    context: ConversionContext,
) -> dict[str, float | None]:
    return {
        "x": parse_length_px(attributes.get("x"), context, axis="x"),
        "y": parse_length_px(attributes.get("y"), context, axis="y"),
        "width": _parse_optional_length(attributes, "width", context, axis="x"),
        "height": _parse_optional_length(attributes, "height", context, axis="y"),
    }


def _parse_optional_length(
    attributes: dict[str, str],
    name: str,
    context: ConversionContext,
    *,
    axis: str,
) -> float | None:
    if attributes.get(name) is None:
        return None
    return parse_length_px(attributes.get(name), context, axis=axis)
