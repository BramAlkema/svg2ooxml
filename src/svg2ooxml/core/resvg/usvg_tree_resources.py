"""Resource-like node conversion for parser-to-usvg conversion."""

from __future__ import annotations

from svg2ooxml.common.units.conversion import ConversionContext

from .parser.options import Options
from .parser.tree import SvgNode
from .usvg_nodes import ClipPathNode, ImageNode, MarkerNode, MaskNode, TextNode, UseNode
from .usvg_tree_conversion_helpers import convert_children, parse_positioned_size
from .usvg_tree_conversion_types import BaseKwargs, NodeConverter
from .usvg_tree_utils import extract_href, gather_text
from .viewport_units import parse_length_px


def convert_image(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> ImageNode:
    attributes = base_kwargs["attributes"]
    href = extract_href(attributes)
    image_data = resolve_image_data(href, options)
    image = ImageNode(
        href=href,
        **parse_positioned_size(attributes, context),
        data=image_data,
        **base_kwargs,
    )
    image.children = convert_children(node, image, options, context, convert_child)
    return image


def resolve_image_data(href: str | None, options: Options | None) -> bytes | None:
    if not href or options is None:
        return None
    image_data = options.image_href_resolver.resolve_data(href)
    if image_data is not None:
        return image_data
    path = options.image_href_resolver.resolve_file(href)
    if not path:
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def convert_text(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> TextNode:
    text_node = TextNode(text_content=gather_text(node), **base_kwargs)
    text_node.children = convert_children(
        node, text_node, options, context, convert_child
    )
    return text_node


def convert_mask(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> MaskNode:
    attributes = base_kwargs["attributes"]
    mask = MaskNode(
        mask_units=attributes.get("maskUnits", "objectBoundingBox"),
        mask_content_units=attributes.get("maskContentUnits", "userSpaceOnUse"),
        **base_kwargs,
    )
    mask.children = convert_children(node, mask, options, context, convert_child)
    return mask


def convert_clip_path(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> ClipPathNode:
    clip = ClipPathNode(
        clip_path_units=base_kwargs["attributes"].get(
            "clipPathUnits", "userSpaceOnUse"
        ),
        **base_kwargs,
    )
    clip.children = convert_children(node, clip, options, context, convert_child)
    return clip


def convert_marker(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> MarkerNode:
    attributes = base_kwargs["attributes"]
    marker = MarkerNode(
        ref_x=parse_length_px(attributes.get("refX"), context, axis="x"),
        ref_y=parse_length_px(attributes.get("refY"), context, axis="y"),
        marker_units=attributes.get("markerUnits", "strokeWidth"),
        orient=attributes.get("orient", "auto"),
        **base_kwargs,
    )
    marker.children = convert_children(node, marker, options, context, convert_child)
    return marker


def convert_use(
    node: SvgNode,
    base_kwargs: BaseKwargs,
    options: Options | None,
    context: ConversionContext,
    convert_child: NodeConverter,
) -> UseNode:
    attributes = base_kwargs["attributes"]
    use_node = UseNode(
        href=extract_href(attributes),
        **parse_positioned_size(attributes, context),
        **base_kwargs,
    )
    use_node.children = convert_children(
        node, use_node, options, context, convert_child
    )
    return use_node
