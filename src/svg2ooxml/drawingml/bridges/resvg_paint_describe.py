"""Build paint descriptors from resvg objects and legacy SVG XML."""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from svg2ooxml.color.adapters import color_object_alpha
from svg2ooxml.color.parsers import parse_color
from svg2ooxml.common.conversions.colors import color_to_hex as css_color_to_hex
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.gradient_units import (
    normalize_gradient_units,
    parse_gradient_coordinate,
    parse_gradient_offset,
)
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_string,
    matrix_to_tuple,
    parse_matrix_transform,
)
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop,
    LinearGradient,
    RadialGradient,
)
from svg2ooxml.core.resvg.usvg_tree import PatternNode, UseNode
from svg2ooxml.drawingml.bridges.resvg_paint_descriptors import (
    GradientDescriptor,
    GradientStopDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
    RadialGradientDescriptor,
)
from svg2ooxml.drawingml.bridges.resvg_paint_utils import (
    clone_element,
    color_to_hex,
    copy_presentation_attributes,
    extract_href,
    parse_float,
    parse_style,
)


def describe_linear_gradient(gradient_id: str, gradient: LinearGradient) -> LinearGradientDescriptor:
    return LinearGradientDescriptor(
        gradient_id=gradient_id or None,
        x1=gradient.x1,
        y1=gradient.y1,
        x2=gradient.x2,
        y2=gradient.y2,
        units=gradient.units or "objectBoundingBox",
        spread_method=gradient.spread_method or "pad",
        transform=matrix_to_tuple(gradient.transform),
        stops=_describe_stops(gradient.stops),
        href=gradient.href,
        specified=gradient.specified,
        raw_attributes=dict(gradient.raw_attributes),
    )


def describe_radial_gradient(gradient_id: str, gradient: RadialGradient) -> RadialGradientDescriptor:
    return RadialGradientDescriptor(
        gradient_id=gradient_id or None,
        cx=gradient.cx,
        cy=gradient.cy,
        r=gradient.r,
        fx=gradient.fx,
        fy=gradient.fy,
        units=gradient.units or "objectBoundingBox",
        spread_method=gradient.spread_method or "pad",
        transform=matrix_to_tuple(gradient.transform),
        stops=_describe_stops(gradient.stops),
        href=gradient.href,
        specified=gradient.specified,
        raw_attributes=dict(gradient.raw_attributes),
    )


def describe_pattern(pattern_id: str, node: PatternNode) -> PatternDescriptor:
    pattern = node.pattern
    attributes = {
        name: value
        for name, value in (node.attributes or {}).items()
        if value is not None
    }

    x = pattern.x if pattern is not None else 0.0
    y = pattern.y if pattern is not None else 0.0
    width = pattern.width if pattern is not None else 0.0
    height = pattern.height if pattern is not None else 0.0
    units = pattern.units if pattern is not None and pattern.units else "objectBoundingBox"
    content_units = (
        pattern.content_units if pattern is not None and pattern.content_units else "userSpaceOnUse"
    )
    transform = matrix_to_tuple(pattern.transform if pattern is not None else None)
    href = pattern.href if pattern is not None else None

    children: list[etree._Element] = []
    for child in node.children:
        child_source = getattr(child, "source", None)
        if isinstance(child_source, etree._Element):
            children.append(clone_element(child_source))
        if isinstance(child, UseNode):
            resolved = getattr(child, "use_source", None)
            if isinstance(resolved, etree._Element):
                resolved_clone = clone_element(resolved)
                resolved_clone.attrib.pop("id", None)
                copy_presentation_attributes(child_source, resolved_clone)
                transform_value = matrix_to_string(getattr(child, "transform", None))
                if transform_value:
                    wrapper = etree.Element("g")
                    wrapper.set("transform", transform_value)
                    wrapper.append(resolved_clone)
                    children.append(wrapper)
                else:
                    children.append(resolved_clone)

    return PatternDescriptor(
        pattern_id=pattern_id or None,
        x=x,
        y=y,
        width=width,
        height=height,
        units=units,
        content_units=content_units,
        transform=transform,
        href=href,
        attributes=attributes,
        children=tuple(children),
    )


def describe_gradient_element(element: etree._Element) -> GradientDescriptor:
    tag = local_name(element.tag)
    if tag == "linearGradient":
        return _linear_descriptor_from_element(element)
    if tag == "radialGradient":
        return _radial_descriptor_from_element(element)
    if tag == "meshgradient":
        return _mesh_descriptor_from_element(element)
    raise ValueError(f"Unsupported gradient element: {tag}")


def describe_pattern_element(element: etree._Element) -> PatternDescriptor:
    attributes = {name: value for name, value in element.attrib.items() if value is not None}
    matrix = parse_matrix_transform(element.get("patternTransform"))
    child_clones = tuple(clone_element(child) for child in element)
    return PatternDescriptor(
        pattern_id=element.get("id"),
        x=parse_float(element.get("x"), 0.0),
        y=parse_float(element.get("y"), 0.0),
        width=parse_float(element.get("width"), 0.0),
        height=parse_float(element.get("height"), 0.0),
        units=element.get("patternUnits") or "objectBoundingBox",
        content_units=element.get("patternContentUnits") or "userSpaceOnUse",
        transform=matrix,
        href=extract_href(element),
        attributes=attributes,
        children=child_clones,
    )


def _describe_stops(stops: Sequence[GradientStop]) -> tuple[GradientStopDescriptor, ...]:
    return tuple(
        GradientStopDescriptor(
            offset=max(0.0, min(1.0, stop.offset)),
            color=color_to_hex(stop.color),
            opacity=color_object_alpha(stop.color),
        )
        for stop in stops
    )


def _linear_descriptor_from_element(element: etree._Element) -> LinearGradientDescriptor:
    transform = parse_matrix_transform(element.get("gradientTransform"))
    stops = _parse_stops(element)
    units = normalize_gradient_units(element.get("gradientUnits"))
    return LinearGradientDescriptor(
        gradient_id=element.get("id"),
        x1=parse_gradient_coordinate(element.get("x1"), units=units, axis="x", default="0%"),
        y1=parse_gradient_coordinate(element.get("y1"), units=units, axis="y", default="0%"),
        x2=parse_gradient_coordinate(element.get("x2"), units=units, axis="x", default="100%"),
        y2=parse_gradient_coordinate(element.get("y2"), units=units, axis="y", default="0%"),
        units=units,
        spread_method=element.get("spreadMethod") or "pad",
        transform=transform,
        stops=stops,
        href=extract_href(element),
        specified=tuple(
            key
            for key in (
                "x1",
                "y1",
                "x2",
                "y2",
                "gradientUnits",
                "spreadMethod",
                "gradientTransform",
            )
            if key in element.attrib
        ),
        raw_attributes={name: value for name, value in element.attrib.items() if value is not None},
    )


def _radial_descriptor_from_element(element: etree._Element) -> RadialGradientDescriptor:
    transform = parse_matrix_transform(element.get("gradientTransform"))
    stops = _parse_stops(element)
    units = normalize_gradient_units(element.get("gradientUnits"))
    cx = parse_gradient_coordinate(element.get("cx"), units=units, axis="x", default="50%")
    cy = parse_gradient_coordinate(element.get("cy"), units=units, axis="y", default="50%")
    return RadialGradientDescriptor(
        gradient_id=element.get("id"),
        cx=cx,
        cy=cy,
        r=parse_gradient_coordinate(element.get("r"), units=units, axis="x", default="50%"),
        fx=parse_gradient_coordinate(element.get("fx"), units=units, axis="x", default=str(cx)),
        fy=parse_gradient_coordinate(element.get("fy"), units=units, axis="y", default=str(cy)),
        units=units,
        spread_method=element.get("spreadMethod") or "pad",
        transform=transform,
        stops=stops,
        href=extract_href(element),
        specified=tuple(
            key
            for key in (
                "cx",
                "cy",
                "r",
                "fx",
                "fy",
                "gradientUnits",
                "spreadMethod",
                "gradientTransform",
            )
            if key in element.attrib
        ),
        raw_attributes={name: value for name, value in element.attrib.items() if value is not None},
    )


def _mesh_descriptor_from_element(element: etree._Element) -> MeshGradientDescriptor:
    attributes = {name: value for name, value in element.attrib.items() if value is not None}
    rows, cols, patch_count, stop_count, colors = _analyze_mesh_structure(element)
    return MeshGradientDescriptor(
        gradient_id=element.get("id"),
        rows=rows,
        columns=cols,
        patch_count=patch_count,
        stop_count=stop_count,
        colors=tuple(sorted(colors)),
        attributes=attributes,
        element=clone_element(element),
        href=extract_href(element),
    )


def _parse_stops(element: etree._Element) -> tuple[GradientStopDescriptor, ...]:
    stops: list[GradientStopDescriptor] = []
    stop_elements = element.findall(".//{http://www.w3.org/2000/svg}stop") + element.findall(".//stop")
    for stop_el in stop_elements:
        style_map = parse_style(stop_el.get("style"))
        color_attr = stop_el.get("stop-color") or style_map.get("stop-color") or "#000000"
        parsed_color = parse_color(color_attr)
        color_hex = f"#{css_color_to_hex(color_attr, default='000000')}"
        opacity_attr = stop_el.get("stop-opacity") or style_map.get("stop-opacity")
        color_alpha = (
            color_object_alpha(parsed_color) if parsed_color is not None else 1.0
        )
        opacity = color_alpha * parse_opacity(opacity_attr, default=1.0)
        offset = parse_gradient_offset(stop_el.get("offset", "0"))
        stops.append(
            GradientStopDescriptor(
                offset=max(0.0, min(1.0, offset)),
                color=color_hex,
                opacity=opacity,
            )
        )
    return tuple(stops)


def _analyze_mesh_structure(element: etree._Element) -> tuple[int, int, int, int, set[str]]:
    rows = 0
    cols = 0
    patch_count = 0
    stop_count = 0
    colors: set[str] = set()

    for row in element:
        if local_name(getattr(row, "tag", "")) != "meshrow":
            continue
        rows += 1
        row_cols = 0
        for patch in row:
            if local_name(getattr(patch, "tag", "")) != "meshpatch":
                continue
            row_cols += 1
            patch_count += 1
            for stop_el in patch.iter():
                if local_name(getattr(stop_el, "tag", "")) != "stop":
                    continue
                style_map = parse_style(stop_el.get("style"))
                color_attr = stop_el.get("stop-color") or style_map.get("stop-color")
                color_hex = f"#{css_color_to_hex(color_attr, default='000000')}"
                colors.add(color_hex.lstrip("#").upper())
                stop_count += 1
        cols = max(cols, row_cols)

    return rows, cols, patch_count, stop_count, colors


__all__ = [
    "describe_gradient_element",
    "describe_linear_gradient",
    "describe_pattern",
    "describe_pattern_element",
    "describe_radial_gradient",
]
