"""Materialize resvg paint descriptors as SVG XML elements."""

from __future__ import annotations

from collections.abc import Iterable

from lxml import etree

from svg2ooxml.core.resvg.geometry.matrix_bridge import matrix_tuple_to_string
from svg2ooxml.drawingml.bridges.resvg_paint_descriptors import (
    GradientStopDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
    RadialGradientDescriptor,
)
from svg2ooxml.drawingml.bridges.resvg_paint_utils import (
    clone_element,
    format_number,
)


def build_linear_gradient_element(descriptor: LinearGradientDescriptor) -> etree._Element:
    element = etree.Element("linearGradient")
    if descriptor.gradient_id:
        element.set("id", descriptor.gradient_id)
    _assign_common_gradient_attrs(
        element,
        descriptor.units,
        descriptor.spread_method,
        descriptor.transform,
        descriptor.href,
    )
    _assign_explicit_common_gradient_attrs(element, descriptor)
    _set_descriptor_attr(element, descriptor, "x1", descriptor.x1)
    _set_descriptor_attr(element, descriptor, "y1", descriptor.y1)
    _set_descriptor_attr(element, descriptor, "x2", descriptor.x2)
    _set_descriptor_attr(element, descriptor, "y2", descriptor.y2)
    _append_stop_descriptors(element, descriptor.stops)
    return element


def build_radial_gradient_element(descriptor: RadialGradientDescriptor) -> etree._Element:
    element = etree.Element("radialGradient")
    if descriptor.gradient_id:
        element.set("id", descriptor.gradient_id)
    _assign_common_gradient_attrs(
        element,
        descriptor.units,
        descriptor.spread_method,
        descriptor.transform,
        descriptor.href,
    )
    _assign_explicit_common_gradient_attrs(element, descriptor)
    _set_descriptor_attr(element, descriptor, "cx", descriptor.cx)
    _set_descriptor_attr(element, descriptor, "cy", descriptor.cy)
    _set_descriptor_attr(element, descriptor, "r", descriptor.r)
    _set_descriptor_attr(element, descriptor, "fx", descriptor.fx)
    _set_descriptor_attr(element, descriptor, "fy", descriptor.fy)
    _append_stop_descriptors(element, descriptor.stops)
    return element


def build_mesh_gradient_element(descriptor: MeshGradientDescriptor) -> etree._Element:
    return clone_element(descriptor.element)


def build_pattern_element(descriptor: PatternDescriptor) -> etree._Element:
    element = etree.Element("pattern")
    if descriptor.pattern_id:
        element.set("id", descriptor.pattern_id)

    for name, value in descriptor.attributes.items():
        element.set(name, value)

    element.set("x", format_number(descriptor.x))
    element.set("y", format_number(descriptor.y))
    element.set("width", format_number(descriptor.width))
    element.set("height", format_number(descriptor.height))

    if descriptor.units and descriptor.units != "objectBoundingBox":
        element.set("patternUnits", descriptor.units)
    if descriptor.content_units and descriptor.content_units != "userSpaceOnUse":
        element.set("patternContentUnits", descriptor.content_units)
    transform = matrix_tuple_to_string(descriptor.transform)
    if transform:
        element.set("patternTransform", transform)
    if descriptor.href:
        element.set("{http://www.w3.org/1999/xlink}href", descriptor.href)

    for child in descriptor.children:
        element.append(clone_element(child))

    return element


def _assign_common_gradient_attrs(
    element: etree._Element,
    units: str,
    spread_method: str,
    transform: tuple[float, float, float, float, float, float],
    href: str | None,
) -> None:
    if units and units != "objectBoundingBox":
        element.set("gradientUnits", units)
    if spread_method and spread_method != "pad":
        element.set("spreadMethod", spread_method)
    transform_value = matrix_tuple_to_string(transform)
    if transform_value:
        element.set("gradientTransform", transform_value)
    if href:
        element.set("{http://www.w3.org/1999/xlink}href", href)


def _set_descriptor_attr(
    element: etree._Element,
    descriptor: LinearGradientDescriptor | RadialGradientDescriptor,
    name: str,
    value: float,
) -> None:
    if name in descriptor.specified:
        element.set(name, descriptor.raw_attributes.get(name) or format_number(value))


def _assign_explicit_common_gradient_attrs(
    element: etree._Element,
    descriptor: LinearGradientDescriptor | RadialGradientDescriptor,
) -> None:
    if "gradientUnits" in descriptor.specified:
        element.set(
            "gradientUnits",
            descriptor.raw_attributes.get("gradientUnits") or descriptor.units,
        )
    if "spreadMethod" in descriptor.specified:
        element.set(
            "spreadMethod",
            descriptor.raw_attributes.get("spreadMethod") or descriptor.spread_method,
        )
    if "gradientTransform" in descriptor.specified:
        raw_transform = descriptor.raw_attributes.get("gradientTransform")
        if raw_transform is not None:
            element.set("gradientTransform", raw_transform)


def _append_stop_descriptors(parent: etree._Element, stops: Iterable[GradientStopDescriptor]) -> None:
    for stop in stops:
        stop_el = etree.SubElement(parent, "stop")
        stop_el.set("offset", format_number(stop.offset))
        stop_el.set("stop-color", stop.color)
        if stop.opacity < 0.999:
            stop_el.set("stop-opacity", format_number(stop.opacity))


__all__ = [
    "build_linear_gradient_element",
    "build_mesh_gradient_element",
    "build_pattern_element",
    "build_radial_gradient_element",
]
