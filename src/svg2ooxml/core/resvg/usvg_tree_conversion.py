"""Convert parser ``SvgNode`` objects into typed usvg tree nodes."""

from __future__ import annotations

from svg2ooxml.common.units.conversion import ConversionContext

from .geometry.matrix import matrix_from_commands
from .parser.options import Options
from .parser.presentation import collect_presentation
from .parser.tree import SvgNode
from .usvg_nodes import BaseNode, GenericNode, GroupNode
from .usvg_tree_conversion_helpers import convert_children
from .usvg_tree_conversion_types import BaseKwargs
from .usvg_tree_filters import build_filter_primitive
from .usvg_tree_filters import convert_filter as _convert_filter
from .usvg_tree_paint_servers import (
    convert_linear_gradient as _convert_linear_gradient,
)
from .usvg_tree_paint_servers import convert_pattern as _convert_pattern
from .usvg_tree_paint_servers import convert_radial_gradient as _convert_radial_gradient
from .usvg_tree_resources import convert_clip_path as _convert_clip_path
from .usvg_tree_resources import convert_image as _convert_image
from .usvg_tree_resources import convert_marker as _convert_marker
from .usvg_tree_resources import convert_mask as _convert_mask
from .usvg_tree_resources import convert_text as _convert_text
from .usvg_tree_resources import convert_use as _convert_use
from .usvg_tree_shapes import convert_circle as _convert_circle
from .usvg_tree_shapes import convert_ellipse as _convert_ellipse
from .usvg_tree_shapes import convert_line as _convert_line
from .usvg_tree_shapes import convert_path as _convert_path
from .usvg_tree_shapes import convert_poly as _convert_poly
from .usvg_tree_shapes import convert_rect as _convert_rect
from .usvg_tree_styles import resolve_node_fill as _resolve_node_fill
from .usvg_tree_styles import resolve_node_stroke as _resolve_node_stroke
from .usvg_tree_styles import resolve_node_text_style as _resolve_node_text_style
from .usvg_tree_utils import (
    inherit_fill,
    inherit_stroke,
    inherit_text,
    parse_view_box,
    strip_namespace,
)
from .viewport_units import derive_svg_viewport_context, initial_viewport_context


def convert_node(
    node: SvgNode,
    parent: BaseNode | None = None,
    options: Options | None = None,
    context: ConversionContext | None = None,
) -> BaseNode:
    if context is None:
        context = initial_viewport_context(node, options)
    presentation = collect_presentation(node)
    attributes = dict(node.attributes)
    styles = dict(node.styles)
    tag_local = strip_namespace(node.tag)
    node_id = attributes.get("id")

    transform_matrix = matrix_from_commands(presentation.transform)
    fill_style = _resolve_node_fill(presentation, attributes, styles)
    stroke_style = _resolve_node_stroke(presentation, attributes, styles)
    text_style = _resolve_node_text_style(presentation, parent)
    parent_fill = parent.fill if parent is not None else None
    parent_stroke = parent.stroke if parent is not None else None
    parent_text = parent.text_style if parent is not None else None

    base_kwargs: BaseKwargs = {
        "tag": tag_local,
        "id": node_id,
        "presentation": presentation,
        "attributes": attributes,
        "styles": styles,
        "transform": transform_matrix,
        "fill": inherit_fill(fill_style, parent_fill),
        "stroke": inherit_stroke(stroke_style, parent_stroke),
        "text_style": inherit_text(text_style, parent_text),
        "view_box": parse_view_box(attributes.get("viewBox")),
        "source": getattr(node, "source", None),
    }

    if tag_local in {"g", "svg"}:
        return _convert_group(node, base_kwargs, parent, options, context, tag_local)
    if tag_local == "path":
        return _convert_path(node, base_kwargs, options, context, convert_node)
    if tag_local == "rect":
        return _convert_rect(node, base_kwargs, options, context, convert_node)
    if tag_local == "circle":
        return _convert_circle(node, base_kwargs, options, context, convert_node)
    if tag_local == "ellipse":
        return _convert_ellipse(node, base_kwargs, options, context, convert_node)
    if tag_local == "line":
        return _convert_line(node, base_kwargs, options, context, convert_node)
    if tag_local in {"polyline", "polygon"}:
        return _convert_poly(node, base_kwargs, options, context, convert_node)
    if tag_local == "linearGradient":
        return _convert_linear_gradient(
            node, base_kwargs, options, context, convert_node
        )
    if tag_local == "radialGradient":
        return _convert_radial_gradient(
            node, base_kwargs, options, context, convert_node
        )
    if tag_local == "pattern":
        return _convert_pattern(node, base_kwargs, options, context, convert_node)
    if tag_local == "image":
        return _convert_image(node, base_kwargs, options, context, convert_node)
    if tag_local == "text":
        return _convert_text(node, base_kwargs, options, context, convert_node)
    if tag_local == "mask":
        return _convert_mask(node, base_kwargs, options, context, convert_node)
    if tag_local == "clipPath":
        return _convert_clip_path(node, base_kwargs, options, context, convert_node)
    if tag_local == "marker":
        return _convert_marker(node, base_kwargs, options, context, convert_node)
    if tag_local == "filter":
        return _convert_filter(node, base_kwargs)
    if tag_local == "use":
        return _convert_use(node, base_kwargs, options, context, convert_node)

    generic = GenericNode(**base_kwargs)
    generic.children = convert_children(node, generic, options, context, convert_node)
    return generic


def _convert_group(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    parent: BaseNode | None,
    options: Options | None,
    context: ConversionContext,
    tag_local: str,
) -> GroupNode:
    child_context = (
        derive_svg_viewport_context(base_kwargs["attributes"], context, options)
        if tag_local == "svg"
        else context
    )
    group = GroupNode(**base_kwargs)
    group.children = convert_children(node, group, options, child_context, convert_node)
    return group


__all__ = ["build_filter_primitive", "convert_node"]
