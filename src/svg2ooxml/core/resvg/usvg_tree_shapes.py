"""Shape node conversion for parser-to-usvg conversion."""

from __future__ import annotations

from svg2ooxml.common.units.conversion import ConversionContext

from .geometry.path_normalizer import normalize_path
from .parser.options import Options
from .parser.tree import SvgNode
from .usvg_nodes import (
    CircleNode,
    EllipseNode,
    LineNode,
    PathNode,
    PolyNode,
    RectNode,
)
from .usvg_tree_conversion_helpers import convert_children
from .usvg_tree_conversion_types import BaseKwargs, NodeConverter
from .usvg_tree_utils import parse_points
from .viewport_units import parse_length_px


def convert_path(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> PathNode:
    path_node = PathNode(d=base_kwargs["attributes"].get("d"), **base_kwargs)
    path_node.children = convert_children(
        node, path_node, options, context, convert_child
    )
    stroke_width = path_node.stroke.width if path_node.stroke else None
    path_node.geometry = normalize_path(path_node.d, path_node.transform, stroke_width)
    return path_node


def convert_rect(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> RectNode:
    attributes = base_kwargs["attributes"]
    rect = RectNode(
        x=parse_length_px(attributes.get("x"), context, axis="x"),
        y=parse_length_px(attributes.get("y"), context, axis="y"),
        width=parse_length_px(attributes.get("width"), context, axis="x"),
        height=parse_length_px(attributes.get("height"), context, axis="y"),
        rx=parse_length_px(attributes.get("rx"), context, axis="x"),
        ry=parse_length_px(attributes.get("ry"), context, axis="y"),
        **base_kwargs,
    )
    rect.children = convert_children(node, rect, options, context, convert_child)
    return rect


def convert_circle(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> CircleNode:
    attributes = base_kwargs["attributes"]
    circle = CircleNode(
        cx=parse_length_px(attributes.get("cx"), context, axis="x"),
        cy=parse_length_px(attributes.get("cy"), context, axis="y"),
        r=parse_length_px(attributes.get("r"), context, axis="x"),
        **base_kwargs,
    )
    circle.children = convert_children(node, circle, options, context, convert_child)
    return circle


def convert_ellipse(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> EllipseNode:
    attributes = base_kwargs["attributes"]
    ellipse = EllipseNode(
        cx=parse_length_px(attributes.get("cx"), context, axis="x"),
        cy=parse_length_px(attributes.get("cy"), context, axis="y"),
        rx=parse_length_px(attributes.get("rx"), context, axis="x"),
        ry=parse_length_px(attributes.get("ry"), context, axis="y"),
        **base_kwargs,
    )
    ellipse.children = convert_children(node, ellipse, options, context, convert_child)
    return ellipse


def convert_line(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> LineNode:
    attributes = base_kwargs["attributes"]
    line = LineNode(
        x1=parse_length_px(attributes.get("x1"), context, axis="x"),
        y1=parse_length_px(attributes.get("y1"), context, axis="y"),
        x2=parse_length_px(attributes.get("x2"), context, axis="x"),
        y2=parse_length_px(attributes.get("y2"), context, axis="y"),
        **base_kwargs,
    )
    line.children = convert_children(node, line, options, context, convert_child)
    return line


def convert_poly(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> PolyNode:
    poly = PolyNode(
        points=parse_points(base_kwargs["attributes"].get("points", "")), **base_kwargs
    )
    poly.children = convert_children(node, poly, options, context, convert_child)
    return poly
