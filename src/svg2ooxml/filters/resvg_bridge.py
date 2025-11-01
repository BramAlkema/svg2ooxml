"""Lightweight adapters to expose resvg filter nodes to svg2ooxml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from lxml import etree

from svg2ooxml.core.resvg.parser.presentation import Presentation
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive, Tree


@dataclass(slots=True)
class FilterPrimitiveDescriptor:
    """Simplified representation of a resvg filter primitive."""

    tag: str
    attributes: dict[str, str]
    styles: dict[str, str]
    children: tuple["FilterPrimitiveDescriptor", ...] = ()


@dataclass(slots=True)
class ResolvedFilter:
    """Filter definition ready for svg2ooxml filter processing."""

    filter_id: str | None
    filter_units: str
    primitive_units: str
    primitives: list[FilterPrimitiveDescriptor]
    region: dict[str, float | str | None]


def resolve_filter_node(filter_node: FilterNode) -> ResolvedFilter:
    """Convert a FilterNode into a ResolvedFilter descriptor."""

    descriptors = [_descriptor_from_primitive(primitive) for primitive in filter_node.primitives]
    region = _extract_region(filter_node)
    return ResolvedFilter(
        filter_id=filter_node.id,
        filter_units=filter_node.filter_units,
        primitive_units=filter_node.primitive_units,
        primitives=descriptors,
        region=region,
    )


def resolve_filter_reference(filter_value: str | None, tree: Tree) -> Optional[ResolvedFilter]:
    """Resolve a filter attribute value (e.g., url(#shadow)) against the tree."""

    filter_id = _extract_reference_id(filter_value)
    if not filter_id:
        return None
    filter_node = tree.filters.get(filter_id)
    if filter_node is None:
        return None
    return resolve_filter_node(filter_node)


def resolve_filter_element(filter_element: etree._Element) -> ResolvedFilter:
    """Convert a legacy filter element into a ResolvedFilter descriptor."""

    filter_id = filter_element.get("id")
    filter_units = filter_element.get("filterUnits") or "objectBoundingBox"
    primitive_units = filter_element.get("primitiveUnits") or "userSpaceOnUse"
    region = {
        attr: _coerce_dimension(filter_element.get(attr))
        for attr in ("x", "y", "width", "height")
    }

    primitives: list[FilterPrimitiveDescriptor] = []
    for child in filter_element:
        descriptor = _descriptor_from_element(child)
        if descriptor is not None:
            primitives.append(descriptor)

    return ResolvedFilter(
        filter_id=filter_id,
        filter_units=filter_units,
        primitive_units=primitive_units,
        primitives=primitives,
        region=region,
    )


def build_filter_element(resolved: ResolvedFilter) -> etree._Element:
    """Materialise a ResolvedFilter descriptor into an lxml element tree."""

    element = etree.Element("filter")
    if resolved.filter_id:
        element.set("id", resolved.filter_id)
    element.set("filterUnits", resolved.filter_units)
    element.set("primitiveUnits", resolved.primitive_units)
    region = resolved.region or {}
    for attr in ("x", "y", "width", "height"):
        value = region.get(attr)
        if value is None:
            continue
        element.set(attr, str(value))

    for primitive in resolved.primitives:
        _append_primitive_element(element, primitive)

    return element


def build_filter_node(resolved: ResolvedFilter) -> FilterNode:
    presentation = Presentation(
        fill=None,
        stroke=None,
        stroke_width=None,
        fill_opacity=None,
        stroke_opacity=None,
        opacity=None,
        transform=None,
        font_family=None,
        font_size=None,
        font_style=None,
        font_weight=None,
    )
    attributes: dict[str, str] = {}
    for key, value in (resolved.region or {}).items():
        if value is None:
            continue
        attributes[key] = str(value)
    primitives = tuple(_primitive_from_descriptor(descriptor) for descriptor in resolved.primitives)
    return FilterNode(
        tag="filter",
        id=resolved.filter_id,
        presentation=presentation,
        attributes=attributes,
        styles={},
        children=[],
        primitives=primitives,
        filter_units=resolved.filter_units,
        primitive_units=resolved.primitive_units,
    )


def _descriptor_from_primitive(primitive: FilterPrimitive) -> FilterPrimitiveDescriptor:
    return FilterPrimitiveDescriptor(
        tag=primitive.tag,
        attributes=dict(primitive.attributes),
        styles=dict(primitive.styles),
        children=tuple(_descriptor_from_primitive(child) for child in primitive.children),
    )


def _descriptor_from_element(element: etree._Element) -> FilterPrimitiveDescriptor | None:
    tag = _local_name(getattr(element, "tag", ""))
    if not tag:
        return None
    attributes = {
        key: value
        for key, value in element.attrib.items()
        if key != "style"
    }
    styles: dict[str, str] = {}
    style_attr = element.get("style")
    if style_attr:
        for item in style_attr.split(";"):
            if not item or ":" not in item:
                continue
            key, value = item.split(":", 1)
            styles[key.strip()] = value.strip()
    children: list[FilterPrimitiveDescriptor] = []
    for child in element:
        descriptor = _descriptor_from_element(child)
        if descriptor is not None:
            children.append(descriptor)
    return FilterPrimitiveDescriptor(
        tag=tag,
        attributes=attributes,
        styles=styles,
        children=tuple(children),
    )


def _primitive_from_descriptor(descriptor: FilterPrimitiveDescriptor) -> FilterPrimitive:
    return FilterPrimitive(
        tag=descriptor.tag,
        attributes=dict(descriptor.attributes),
        styles=dict(descriptor.styles),
        children=tuple(_primitive_from_descriptor(child) for child in descriptor.children),
    )


def _append_primitive_element(parent: etree._Element, primitive: FilterPrimitiveDescriptor) -> None:
    child = etree.SubElement(parent, primitive.tag)
    child.attrib.update(primitive.attributes)
    if primitive.styles:
        style_value = ";".join(f"{key}:{value}" for key, value in primitive.styles.items())
        if style_value:
            child.set("style", style_value)
    for nested in primitive.children:
        _append_primitive_element(child, nested)


def _extract_reference_id(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if trimmed.startswith("url(") and trimmed.endswith(")"):
        inner = trimmed[4:-1].strip()
        if inner.startswith("#"):
            return inner[1:]
    elif trimmed.startswith("#"):
        return trimmed[1:]
    return None


def _extract_region(filter_node: FilterNode) -> dict[str, float | str | None]:
    region: dict[str, float | str | None] = {}
    attributes = getattr(filter_node, "attributes", {}) or {}
    for attr in ("x", "y", "width", "height"):
        raw_value = attributes.get(attr)
        region[attr] = _coerce_dimension(raw_value)
    return region


def _coerce_dimension(value: str | None) -> float | str | None:
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return token


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


__all__ = [
    "FilterPrimitiveDescriptor",
    "ResolvedFilter",
    "resolve_filter_node",
    "resolve_filter_reference",
    "resolve_filter_element",
    "build_filter_node",
    "build_filter_element",
]
