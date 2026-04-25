"""Basic text layout utilities."""

from __future__ import annotations

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.core.resvg.usvg_tree import TextNode, TextSpan, Tree


def _parse_number_list(value: str | None) -> list[float]:
    if not value:
        return []
    return parse_numeric_list(value)


def _apply_text_layout(node: TextNode) -> None:
    x_values = _parse_number_list(node.attributes.get("x"))
    y_values = _parse_number_list(node.attributes.get("y"))
    dx_values = _parse_number_list(node.attributes.get("dx"))
    dy_values = _parse_number_list(node.attributes.get("dy"))

    text = node.text_content or ""
    if not text:
        node.spans = []
        return

    x = x_values[0] if x_values else 0.0
    y = y_values[0] if y_values else 0.0

    dx = dx_values[0] if dx_values else 0.0
    dy = dy_values[0] if dy_values else 0.0

    span = TextSpan(text=text, x=x + dx, y=y + dy)
    node.spans = [span]


def build_text_layout(tree: Tree) -> None:
    for node in tree.text_nodes:
        _apply_text_layout(node)
