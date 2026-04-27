"""Simplified usvg::Tree representation with typed nodes."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.units.conversion import ConversionContext
from svg2ooxml.common.units.lengths import parse_number_or_percent

from .geometry.matrix import Matrix, matrix_from_commands
from .gradient_resolution import (
    parse_linear_gradient as _parse_linear_gradient,
)
from .gradient_resolution import (
    parse_radial_gradient as _parse_radial_gradient,
)
from .painting.gradients import PatternPaint
from .painting.paint import (
    FillStyle,
    StrokeStyle,
    TextStyle,
    resolve_fill,
    resolve_stroke,
    resolve_text_style,
)
from .parser.options import Options
from .parser.presentation import collect_presentation, parse_transform
from .parser.tree import SvgDocument, SvgNode
from .usvg_nodes import (
    BaseNode,
    CircleNode,
    ClipPathNode,
    EllipseNode,
    FilterNode,
    FilterPrimitive,
    GenericNode,
    GroupNode,
    ImageNode,
    LinearGradientNode,
    LineNode,
    MarkerNode,
    MaskNode,
    PaintServer,
    PaintServerNode,
    PathNode,
    PatternNode,
    PolyNode,
    RadialGradientNode,
    RectNode,
    TextNode,
    TextSpan,
    Tree,
    UseNode,
)
from .usvg_nodes import (
    propagate_use_source as _propagate_use_source,
)
from .viewport_units import (
    derive_svg_viewport_context,
    initial_viewport_context,
    parse_length_px,
)

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_DEFAULT_TEXT_FONT_SIZE_PT = 12.0

__all__ = [
    "BaseNode",
    "CircleNode",
    "ClipPathNode",
    "EllipseNode",
    "FilterNode",
    "FilterPrimitive",
    "GenericNode",
    "GroupNode",
    "ImageNode",
    "LineNode",
    "LinearGradientNode",
    "MarkerNode",
    "MaskNode",
    "PaintServer",
    "PaintServerNode",
    "PathNode",
    "PatternNode",
    "PolyNode",
    "RadialGradientNode",
    "RectNode",
    "SVG_NAMESPACE",
    "TextNode",
    "TextSpan",
    "Tree",
    "UseNode",
    "build_tree",
]


def _strip_namespace(tag: Any) -> str:
    tag_str = str(tag)
    if tag_str.startswith("{" + SVG_NAMESPACE + "}"):
        return tag_str[len(SVG_NAMESPACE) + 2 :]
    return tag_str


def _gather_text(node: SvgNode) -> str | None:
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


def _extract_href(attributes: dict[str, str]) -> str | None:
    for key in ("href", "{http://www.w3.org/1999/xlink}href"):
        if key in attributes:
            return attributes[key]
    return None


def _parse_number(value: str | None, default: float = 0.0) -> float:
    return parse_number_or_percent(value, default)


def _parse_points(raw: str) -> tuple[float, ...]:
    if not raw:
        return ()
    return tuple(parse_numeric_list(raw))


def _parse_view_box(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    numbers = _parse_points(raw)
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _parse_pattern(node: SvgNode) -> PatternPaint:
    attributes = node.attributes
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("patternTransform")))
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("x", "y", "width", "height", "patternUnits", "patternContentUnits", "patternTransform")
        if key in attributes
    )
    return PatternPaint(
        x=_parse_number(attributes.get("x"), 0.0),
        y=_parse_number(attributes.get("y"), 0.0),
        width=_parse_number(attributes.get("width"), 0.0),
        height=_parse_number(attributes.get("height"), 0.0),
        units=attributes.get("patternUnits") or "objectBoundingBox",
        content_units=attributes.get("patternContentUnits") or "userSpaceOnUse",
        transform=transform_matrix,
        href=href,
        specified=specified,
    )


def _convert_node(
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
    tag_local = _strip_namespace(node.tag)
    node_id = attributes.get("id")

    transform_matrix = matrix_from_commands(presentation.transform)
    raw_fill = styles.get("fill") if "fill" in styles else attributes.get("fill")
    explicit_no_fill = bool(raw_fill) and raw_fill.strip().lower() in {"none", "transparent"}
    fill_style = resolve_fill(
        presentation.fill,
        presentation.fill_opacity,
        presentation.opacity,
    )
    if fill_style.color is None and fill_style.reference is None and not explicit_no_fill:
        fill_style = None

    raw_stroke = styles.get("stroke") if "stroke" in styles else attributes.get("stroke")
    explicit_no_stroke = bool(raw_stroke) and raw_stroke.strip().lower() in {"none", "transparent"}
    stroke_style = resolve_stroke(
        presentation.stroke,
        presentation.stroke_width,
        presentation.stroke_opacity,
        presentation.opacity,
        dasharray=presentation.stroke_dasharray,
        dashoffset=presentation.stroke_dashoffset,
        linecap=presentation.stroke_linecap,
        linejoin=presentation.stroke_linejoin,
        miterlimit=presentation.stroke_miterlimit,
    )
    if (
        stroke_style.color is None
        and stroke_style.reference is None
        and stroke_style.width is None
        and not explicit_no_stroke
    ):
        stroke_style = None
    presentation_font_size = presentation.font_size
    if presentation.font_size_scale is not None:
        parent_font_size = (
            parent.text_style.font_size
            if parent is not None
            and parent.text_style is not None
            and parent.text_style.font_size is not None
            else _DEFAULT_TEXT_FONT_SIZE_PT
        )
        presentation_font_size = parent_font_size * presentation.font_size_scale

    resolved_text_style = resolve_text_style(
        presentation.font_family,
        presentation_font_size,
        presentation.font_style,
        presentation.font_weight,
        text_decoration=getattr(presentation, "text_decoration", None),
        letter_spacing=getattr(presentation, "letter_spacing", None),
    )
    if (
        not resolved_text_style.font_families
        and resolved_text_style.font_size is None
        and resolved_text_style.font_style is None
        and resolved_text_style.font_weight is None
    ):
        text_style = None
    else:
        text_style = resolved_text_style

    view_box = _parse_view_box(attributes.get("viewBox"))

    base_kwargs = {
        "tag": tag_local,
        "id": node_id,
        "presentation": presentation,
        "attributes": attributes,
        "styles": styles,
        "transform": transform_matrix,
        "fill": _inherit_fill(fill_style, parent),
        "stroke": _inherit_stroke(stroke_style, parent),
        "text_style": _inherit_text(text_style, parent),
        "view_box": view_box,
        "source": getattr(node, "source", None),
    }

    if tag_local in {"g", "svg"}:
        child_context = (
            derive_svg_viewport_context(attributes, context, options)
            if tag_local == "svg"
            else context
        )
        group = GroupNode(**base_kwargs)
        group.children = [
            _convert_node(child, group, options, child_context) for child in node.children
        ]
        return group
    if tag_local == "path":
        path_node = PathNode(d=attributes.get("d"), **base_kwargs)
        path_node.children = [
            _convert_node(child, path_node, options, context) for child in node.children
        ]
        from .geometry.path_normalizer import (
            normalize_path,  # local import to avoid cycle
        )

        stroke_width = path_node.stroke.width if path_node.stroke else None
        path_node.geometry = normalize_path(path_node.d, path_node.transform, stroke_width)
        return path_node
    if tag_local == "rect":
        rect = RectNode(
            x=parse_length_px(attributes.get("x"), context, axis="x"),
            y=parse_length_px(attributes.get("y"), context, axis="y"),
            width=parse_length_px(attributes.get("width"), context, axis="x"),
            height=parse_length_px(attributes.get("height"), context, axis="y"),
            rx=parse_length_px(attributes.get("rx"), context, axis="x"),
            ry=parse_length_px(attributes.get("ry"), context, axis="y"),
            **base_kwargs,
        )
        rect.children = [_convert_node(child, rect, options, context) for child in node.children]
        return rect
    if tag_local == "circle":
        circle = CircleNode(
            cx=parse_length_px(attributes.get("cx"), context, axis="x"),
            cy=parse_length_px(attributes.get("cy"), context, axis="y"),
            r=parse_length_px(attributes.get("r"), context, axis="x"),
            **base_kwargs,
        )
        circle.children = [_convert_node(child, circle, options, context) for child in node.children]
        return circle
    if tag_local == "ellipse":
        ellipse = EllipseNode(
            cx=parse_length_px(attributes.get("cx"), context, axis="x"),
            cy=parse_length_px(attributes.get("cy"), context, axis="y"),
            rx=parse_length_px(attributes.get("rx"), context, axis="x"),
            ry=parse_length_px(attributes.get("ry"), context, axis="y"),
            **base_kwargs,
        )
        ellipse.children = [_convert_node(child, ellipse, options, context) for child in node.children]
        return ellipse
    if tag_local == "line":
        line = LineNode(
            x1=parse_length_px(attributes.get("x1"), context, axis="x"),
            y1=parse_length_px(attributes.get("y1"), context, axis="y"),
            x2=parse_length_px(attributes.get("x2"), context, axis="x"),
            y2=parse_length_px(attributes.get("y2"), context, axis="y"),
            **base_kwargs,
        )
        line.children = [_convert_node(child, line, options, context) for child in node.children]
        return line
    if tag_local in {"polyline", "polygon"}:
        points = _parse_points(attributes.get("points", ""))
        poly = PolyNode(points=points, **base_kwargs)
        poly.children = [_convert_node(child, poly, options, context) for child in node.children]
        return poly
    if tag_local == "linearGradient":
        gradient = _parse_linear_gradient(node, context)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = LinearGradientNode(gradient=gradient, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options, context) for child in node.children]
        return node_obj
    if tag_local == "radialGradient":
        gradient = _parse_radial_gradient(node, context)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = RadialGradientNode(gradient=gradient, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options, context) for child in node.children]
        return node_obj
    if tag_local == "pattern":
        pattern = _parse_pattern(node)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = PatternNode(pattern=pattern, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options, context) for child in node.children]
        return node_obj
    if tag_local == "image":
        href = _extract_href(attributes)
        image_data = None
        if href and options:
            image_data = options.image_href_resolver.resolve_data(href)
            if image_data is None:
                path = options.image_href_resolver.resolve_file(href)
                if path:
                    try:
                        image_data = path.read_bytes()
                    except Exception:
                        pass

        image = ImageNode(
            href=href,
            x=parse_length_px(attributes.get("x"), context, axis="x"),
            y=parse_length_px(attributes.get("y"), context, axis="y"),
            width=parse_length_px(attributes.get("width"), context, axis="x")
            if attributes.get("width") is not None
            else None,
            height=parse_length_px(attributes.get("height"), context, axis="y")
            if attributes.get("height") is not None
            else None,
            data=image_data,
            **base_kwargs,
        )
        image.children = [_convert_node(child, image, options, context) for child in node.children]
        return image
    if tag_local == "text":
        text_node = TextNode(text_content=_gather_text(node), **base_kwargs)
        text_node.children = [_convert_node(child, text_node, options, context) for child in node.children]
        return text_node
    if tag_local == "mask":
        mask = MaskNode(
            mask_units=attributes.get("maskUnits", "objectBoundingBox"),
            mask_content_units=attributes.get("maskContentUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
        mask.children = [_convert_node(child, mask, options, context) for child in node.children]
        return mask
    if tag_local == "clipPath":
        clip = ClipPathNode(
            clip_path_units=attributes.get("clipPathUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
        clip.children = [_convert_node(child, clip, options, context) for child in node.children]
        return clip
    if tag_local == "marker":
        marker = MarkerNode(
            ref_x=parse_length_px(attributes.get("refX"), context, axis="x"),
            ref_y=parse_length_px(attributes.get("refY"), context, axis="y"),
            marker_units=attributes.get("markerUnits", "strokeWidth"),
            orient=attributes.get("orient", "auto"),
            **base_kwargs,
        )
        marker.children = [_convert_node(child, marker, options, context) for child in node.children]
        return marker
    if tag_local == "filter":
        primitives_list = [_build_filter_primitive(child) for child in node.children]
        return FilterNode(
            primitives=tuple(primitives_list),
            filter_units=attributes.get("filterUnits", "objectBoundingBox"),
            primitive_units=attributes.get("primitiveUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
    if tag_local == "use":
        use_node = UseNode(
            href=_extract_href(attributes),
            x=parse_length_px(attributes.get("x"), context, axis="x"),
            y=parse_length_px(attributes.get("y"), context, axis="y"),
            width=parse_length_px(attributes.get("width"), context, axis="x")
            if attributes.get("width") is not None
            else None,
            height=parse_length_px(attributes.get("height"), context, axis="y")
            if attributes.get("height") is not None
            else None,
            **base_kwargs,
        )
        use_node.children = [_convert_node(child, use_node, options, context) for child in node.children]
        return use_node

    generic = GenericNode(**base_kwargs)
    generic.children = [_convert_node(child, generic, options, context) for child in node.children]
    return generic


def _build_filter_primitive(node) -> FilterPrimitive:
    child_tag = _strip_namespace(getattr(node, "tag", "") or "")
    children = tuple(_build_filter_primitive(child) for child in getattr(node, "children", []) or [])
    return FilterPrimitive(
        tag=child_tag,
        attributes=dict(getattr(node, "attributes", {}) or {}),
        styles=dict(getattr(node, "styles", {}) or {}),
        children=children,
    )


def _collect_ids(node: BaseNode, ids: dict[str, BaseNode]) -> None:
    if node.id:
        ids[node.id] = node
    for child in node.children:
        _collect_ids(child, ids)


def _clear_ids(node: BaseNode) -> None:
    node.id = None
    for child in node.children:
        _clear_ids(child)


def _expand_use_nodes(root: BaseNode, ids: dict[str, BaseNode]) -> None:
    stack: list[tuple[BaseNode, tuple[str, ...]]] = [(root, ())]
    while stack:
        current, active_refs = stack.pop()
        for index, child in enumerate(list(current.children)):
            if isinstance(child, UseNode) and child.href:
                ref_id = child.href.lstrip("#")
                if not ref_id:
                    continue
                if ref_id in active_refs:
                    # Prevent infinite expansion for recursive <use> chains.
                    continue
                referenced = ids.get(ref_id)
                if referenced is None:
                    continue
                clone = copy.deepcopy(referenced)
                _clear_ids(clone)
                use_transform = child.transform if child.transform is not None else Matrix.identity()
                translation = Matrix(1.0, 0.0, 0.0, 1.0, child.x, child.y)
                clone.transform = use_transform.multiply(translation).multiply(clone.transform)
                _propagate_use_source(clone, getattr(child, "source", None))

                # Apply <use> element's presentation attributes to cloned content
                # Per SVG spec, <use> element attributes override referenced element

                # Update presentation attributes first
                presentation_updated = False
                if hasattr(child, 'presentation') and child.presentation and hasattr(clone, 'presentation') and clone.presentation:
                    from dataclasses import replace
                    new_presentation = clone.presentation
                    if child.presentation.stroke is not None:
                        new_presentation = replace(new_presentation, stroke=child.presentation.stroke)
                        presentation_updated = True
                    if child.presentation.stroke_width is not None:
                        new_presentation = replace(new_presentation, stroke_width=child.presentation.stroke_width)
                        presentation_updated = True
                    if child.presentation.stroke_opacity is not None:
                        new_presentation = replace(new_presentation, stroke_opacity=child.presentation.stroke_opacity)
                        presentation_updated = True
                    if presentation_updated:
                        clone.presentation = new_presentation

                # Re-resolve stroke/fill from updated presentation
                if presentation_updated and hasattr(clone, 'presentation') and clone.presentation:
                    stroke_style = resolve_stroke(
                        clone.presentation.stroke,
                        clone.presentation.stroke_width,
                        clone.presentation.stroke_opacity,
                        clone.presentation.opacity,
                        dasharray=clone.presentation.stroke_dasharray,
                        dashoffset=clone.presentation.stroke_dashoffset,
                        linecap=clone.presentation.stroke_linecap,
                        linejoin=clone.presentation.stroke_linejoin,
                        miterlimit=clone.presentation.stroke_miterlimit,
                    )
                    if not (
                        stroke_style.color is None
                        and stroke_style.reference is None
                        and stroke_style.width is None
                    ):
                        clone.stroke = stroke_style

                # Also apply direct attributes
                if child.fill is not None and clone.fill is None:
                    clone.fill = child.fill
                if child.text_style is not None and clone.text_style is None:
                    clone.text_style = child.text_style

                current.children[index] = clone
                if child.id:
                    ids[child.id] = clone
                stack.append((clone, (*active_refs, ref_id)))
            else:
                stack.append((child, active_refs))


def build_tree(document: SvgDocument, options: Options | None = None) -> Tree:
    root = _convert_node(document.root, None, options)
    ids: dict[str, BaseNode] = {}
    _collect_ids(root, ids)
    _expand_use_nodes(root, ids)
    paint_servers: dict[str, PaintServerNode] = {}
    masks: dict[str, MaskNode] = {}
    clip_paths: dict[str, ClipPathNode] = {}
    markers: dict[str, MarkerNode] = {}
    filters: dict[str, FilterNode] = {}
    text_nodes: list[TextNode] = []
    for node_id, node in ids.items():
        if isinstance(node, PaintServerNode):
            paint_servers[node_id] = node
        elif isinstance(node, MaskNode):
            masks[node_id] = node
        elif isinstance(node, ClipPathNode):
            clip_paths[node_id] = node
        elif isinstance(node, MarkerNode):
            markers[node_id] = node
        elif isinstance(node, FilterNode):
            filters[node_id] = node
        if isinstance(node, TextNode):
            text_nodes.append(node)
    tree = Tree(
        root=root,
        ids=ids,
        paint_servers=paint_servers,
        masks=masks,
        clip_paths=clip_paths,
        markers=markers,
        filters=filters,
        text_nodes=text_nodes,
    )
    from .text.layout import build_text_layout
    build_text_layout(tree)
    return tree


def _inherit_fill(fill: FillStyle | None, parent: BaseNode | None) -> FillStyle | None:
    if fill is not None:
        return fill
    if parent and parent.fill is not None:
        return replace(parent.fill)
    return None


def _inherit_stroke(stroke: StrokeStyle | None, parent: BaseNode | None) -> StrokeStyle | None:
    if stroke is not None:
        return stroke
    if parent and parent.stroke is not None:
        return replace(parent.stroke)
    return None


def _inherit_text(text_style: TextStyle | None, parent: BaseNode | None) -> TextStyle | None:
    parent_style = parent.text_style if parent and parent.text_style is not None else None
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
        letter_spacing=text_style.letter_spacing if text_style.letter_spacing is not None else parent_style.letter_spacing,
    )
