"""Helper routines for DOM traversal during IR conversion."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.traversal.viewbox import viewbox_matrix_from_element


def push_element_transform(traversal, element: etree._Element) -> bool:
    transform = _combined_element_transform(traversal, element)
    if transform is None or transform.is_identity():
        return False
    traversal._coord_space.push(transform)
    return True


def _combined_element_transform(traversal, element: etree._Element) -> Matrix2D | None:
    normalized = None
    if getattr(traversal, "_normalized_lookup", None):
        normalized = traversal._normalized_lookup.get(id(element))

    transform = None
    if normalized is not None:
        transform = normalized.local_transform
    else:
        transform = traversal._transform_parser.parse_to_matrix(element.get("transform"))

    nested_svg_transform = _nested_svg_viewport_transform(traversal, element)
    if transform is None:
        return nested_svg_transform
    if nested_svg_transform is None:
        return transform
    return transform.multiply(nested_svg_transform)


def _nested_svg_viewport_transform(
    traversal,
    element: etree._Element,
) -> Matrix2D | None:
    if local_name(getattr(element, "tag", None)) != "svg":
        return None
    if element is getattr(traversal, "_root_element", None):
        return None

    unit_converter = getattr(traversal._converter, "_unit_converter", None)
    if unit_converter is None:
        return None

    try:
        viewbox_matrix, _ = viewbox_matrix_from_element(element, unit_converter)
    except Exception:
        viewbox_matrix = Matrix2D.identity()

    x = _to_px(unit_converter, element.get("x"), axis="x")
    y = _to_px(unit_converter, element.get("y"), axis="y")
    translate = Matrix2D.translate(x, y)
    return translate.multiply(viewbox_matrix)


def _to_px(unit_converter, value: str | None, *, axis: str) -> float:
    if value is None:
        return 0.0
    try:
        return float(unit_converter.to_px(value, axis=axis))
    except Exception:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def process_anchor(traversal, element: etree._Element, current_navigation, recurse) -> list:
    navigation = traversal._hyperlinks.resolve_navigation(element)
    child_nav = navigation or current_navigation
    ir_elements: list = []
    for child in traversal._children(element):
        ir_elements.extend(recurse(child, child_nav))
    return ir_elements


def resolve_active_navigation(traversal, element: etree._Element, current_navigation):
    inline_navigation = None
    if local_name(getattr(element, "tag", None)) != "use":
        inline_navigation = traversal._hyperlinks.resolve_inline_navigation(element)
    group_navigation = traversal.navigation_from_attributes(element)
    return inline_navigation or group_navigation or current_navigation


def process_group(traversal, element: etree._Element, active_navigation, recurse) -> list:
    child_nodes: list = []
    for child in traversal._children(element):
        child_nodes.extend(recurse(child, active_navigation))
    group = traversal._converter.convert_group(element, child_nodes, traversal._coord_space.current)
    if group:
        traversal._converter.attach_metadata(group, element, active_navigation)
        return [group]
    return []


def process_use(traversal, element: etree._Element, active_navigation, recurse) -> list:
    # In resvg mode, <use> elements are already expanded in the resvg tree
    # Convert the <use> element directly using its mapped resvg node
    resvg_tree = getattr(traversal._converter, "_resvg_tree", None)
    if resvg_tree is not None:
        # Resvg mode: Convert <use> as a shape using the mapped resvg node
        converted = traversal._converter.convert_element(
            tag="use",
            element=element,
            coord_space=traversal._coord_space,
            current_navigation=active_navigation,
            traverse_callback=recurse,
        )
        if not converted:
            return []

        if not isinstance(converted, (list, tuple)):
            converted_items = [converted]
        else:
            converted_items = [item for item in converted if item is not None]

        ir_elements: list = []
        for item in converted_items:
            traversal._converter.attach_metadata(item, element, active_navigation)
            ir_elements.append(item)
        return ir_elements

    # Legacy mode: Expand <use> element and convert children
    expanded = traversal._converter.expand_use(
        element=element,
        coord_space=traversal._coord_space,
        current_navigation=active_navigation,
        traverse_callback=recurse,
    )
    ir_elements: list = []
    for item in expanded:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            for child in item:
                if child is None:
                    continue
                traversal._converter.attach_metadata(child, element, active_navigation)
                ir_elements.append(child)
            continue
        traversal._converter.attach_metadata(item, element, active_navigation)
        ir_elements.append(item)
    return ir_elements


def process_generic(traversal, tag: str, element: etree._Element, active_navigation, recurse) -> list:
    converted = traversal._converter.convert_element(
        tag=tag,
        element=element,
        coord_space=traversal._coord_space,
        current_navigation=active_navigation,
        traverse_callback=recurse,
    )

    if converted is None:
        ir_elements: list = []
        for child in traversal._children(element):
            ir_elements.extend(recurse(child, active_navigation))
        return ir_elements

    if not isinstance(converted, list):
        converted = [converted]

    ir_elements: list = []
    for item in converted:
        if item is None:
            continue
        traversal._converter.attach_metadata(item, element, active_navigation)
        ir_elements.append(item)
    return ir_elements


__all__ = [
    "push_element_transform",
    "local_name",
    "process_anchor",
    "resolve_active_navigation",
    "process_group",
    "process_use",
    "process_generic",
]
