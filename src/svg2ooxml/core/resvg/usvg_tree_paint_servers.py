"""Paint server node conversion for parser-to-usvg conversion."""

from __future__ import annotations

from svg2ooxml.common.units.conversion import ConversionContext

from .gradient_resolution import parse_linear_gradient, parse_radial_gradient
from .parser.options import Options
from .parser.tree import SvgNode
from .usvg_nodes import LinearGradientNode, PatternNode, RadialGradientNode
from .usvg_tree_conversion_helpers import convert_children
from .usvg_tree_conversion_types import BaseKwargs, NodeConverter
from .usvg_tree_utils import parse_pattern


def convert_linear_gradient(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> LinearGradientNode:
    node_obj = LinearGradientNode(
        gradient=parse_linear_gradient(node, context),
        **_paint_server_base_kwargs(base_kwargs),
    )
    node_obj.children = convert_children(
        node, node_obj, options, context, convert_child
    )
    return node_obj


def convert_radial_gradient(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> RadialGradientNode:
    node_obj = RadialGradientNode(
        gradient=parse_radial_gradient(node, context),
        **_paint_server_base_kwargs(base_kwargs),
    )
    node_obj.children = convert_children(
        node, node_obj, options, context, convert_child
    )
    return node_obj


def convert_pattern(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> PatternNode:
    node_obj = PatternNode(
        pattern=parse_pattern(node), **_paint_server_base_kwargs(base_kwargs)
    )
    node_obj.children = convert_children(
        node, node_obj, options, context, convert_child
    )
    return node_obj


def _paint_server_base_kwargs(base_kwargs: BaseKwargs) -> BaseKwargs:
    clean_kwargs = dict(base_kwargs)
    clean_kwargs["fill"] = None
    clean_kwargs["stroke"] = None
    clean_kwargs["text_style"] = None
    return clean_kwargs
