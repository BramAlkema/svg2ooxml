"""Filter node conversion for parser-to-usvg conversion."""

from __future__ import annotations

from .parser.tree import SvgNode
from .usvg_nodes import FilterNode, FilterPrimitive
from .usvg_tree_conversion_types import BaseKwargs
from .usvg_tree_utils import strip_namespace


def convert_filter(node: SvgNode, base_kwargs: BaseKwargs) -> FilterNode:
    attributes = base_kwargs["attributes"]
    return FilterNode(
        primitives=tuple(build_filter_primitive(child) for child in node.children),
        filter_units=attributes.get("filterUnits", "objectBoundingBox"),
        primitive_units=attributes.get("primitiveUnits", "userSpaceOnUse"),
        **base_kwargs,
    )


def build_filter_primitive(node: object) -> FilterPrimitive:
    child_tag = strip_namespace(getattr(node, "tag", "") or "")
    children = tuple(
        build_filter_primitive(child) for child in getattr(node, "children", []) or []
    )
    return FilterPrimitive(
        tag=child_tag,
        attributes=dict(getattr(node, "attributes", {}) or {}),
        styles=dict(getattr(node, "styles", {}) or {}),
        children=children,
    )
