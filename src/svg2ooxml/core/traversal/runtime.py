"""Helper routines for DOM traversal during IR conversion."""

from __future__ import annotations

from typing import Callable, Iterable, List

from lxml import etree

from svg2ooxml.core.pipeline.navigation import NavigationSpec



def push_element_transform(traversal, element: etree._Element) -> bool:
    normalized = None
    if getattr(traversal, "_normalized_lookup", None):
        normalized = traversal._normalized_lookup.get(id(element))

    if normalized is not None:
        transform = normalized.local_transform
        if transform is not None and not transform.is_identity():
            traversal._coord_space.push(transform)
            return True

    transform = traversal._transform_parser.parse_to_matrix(element.get("transform"))
    if transform is not None and not transform.is_identity():
        traversal._coord_space.push(transform)
        return True
    return False


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
    expanded = traversal._converter.expand_use(
        element=element,
        coord_space=traversal._coord_space,
        current_navigation=active_navigation,
        traverse_callback=recurse,
    )
    ir_elements: list = []
    for item in expanded:
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
