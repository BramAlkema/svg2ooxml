"""Helpers to convert resvg paint servers into descriptor objects and legacy DOM."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field

from lxml import etree

from svg2ooxml.color.parsers import parse_color
from svg2ooxml.color.utils import rgb_object_to_hex
from svg2ooxml.common.conversions.colors import color_to_hex
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.gradient_units import (
    normalize_gradient_units,
    parse_gradient_coordinate,
    parse_gradient_offset,
)
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name as _local_name
from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop,
    LinearGradient,
    RadialGradient,
)
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.core.resvg.usvg_tree import PatternNode, UseNode

# ---------------------------------------------------------------------------
# Descriptor dataclasses
# ---------------------------------------------------------------------------


MatrixTuple = tuple[float, float, float, float, float, float]


@dataclass(slots=True)
class GradientStopDescriptor:
    offset: float
    color: str
    opacity: float


@dataclass(slots=True)
class LinearGradientDescriptor:
    gradient_id: str | None
    x1: float
    y1: float
    x2: float
    y2: float
    units: str
    spread_method: str
    transform: MatrixTuple
    stops: tuple[GradientStopDescriptor, ...]
    href: str | None = None
    specified: tuple[str, ...] = ("x1", "y1", "x2", "y2")
    raw_attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RadialGradientDescriptor:
    gradient_id: str | None
    cx: float
    cy: float
    r: float
    fx: float
    fy: float
    units: str
    spread_method: str
    transform: MatrixTuple
    stops: tuple[GradientStopDescriptor, ...]
    href: str | None = None
    specified: tuple[str, ...] = ("cx", "cy", "r", "fx", "fy")
    raw_attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MeshGradientDescriptor:
    gradient_id: str | None
    rows: int
    columns: int
    patch_count: int
    stop_count: int
    colors: tuple[str, ...]
    attributes: dict[str, str]
    element: etree._Element
    href: str | None = None


GradientDescriptor = LinearGradientDescriptor | RadialGradientDescriptor | MeshGradientDescriptor


@dataclass(slots=True)
class PatternDescriptor:
    pattern_id: str | None
    x: float
    y: float
    width: float
    height: float
    units: str
    content_units: str
    transform: MatrixTuple
    href: str | None
    attributes: dict[str, str]
    children: tuple[etree._Element, ...]


# ---------------------------------------------------------------------------
# Descriptor builders (resvg)
# ---------------------------------------------------------------------------


def describe_linear_gradient(gradient_id: str, gradient: LinearGradient) -> LinearGradientDescriptor:
    return LinearGradientDescriptor(
        gradient_id=gradient_id or None,
        x1=gradient.x1,
        y1=gradient.y1,
        x2=gradient.x2,
        y2=gradient.y2,
        units=gradient.units or "objectBoundingBox",
        spread_method=gradient.spread_method or "pad",
        transform=_matrix_to_tuple(gradient.transform),
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
        transform=_matrix_to_tuple(gradient.transform),
        stops=_describe_stops(gradient.stops),
        href=gradient.href,
        specified=gradient.specified,
        raw_attributes=dict(gradient.raw_attributes),
    )


def describe_pattern(pattern_id: str, node: PatternNode) -> PatternDescriptor:
    pattern = node.pattern
    attributes = {}
    for name, value in (node.attributes or {}).items():
        if value is not None:
            attributes[name] = value

    x = pattern.x if pattern is not None else 0.0
    y = pattern.y if pattern is not None else 0.0
    width = pattern.width if pattern is not None else 0.0
    height = pattern.height if pattern is not None else 0.0
    units = (pattern.units if pattern is not None and pattern.units else "objectBoundingBox")
    content_units = (
        pattern.content_units if pattern is not None and pattern.content_units else "userSpaceOnUse"
    )
    transform = _matrix_to_tuple(pattern.transform if pattern is not None else Matrix.identity())
    href = pattern.href if pattern is not None else None

    children: list[etree._Element] = []
    for child in node.children:
        child_source = getattr(child, "source", None)
        if isinstance(child_source, etree._Element):
            children.append(_clone_element(child_source))
        if isinstance(child, UseNode):
            resolved = getattr(child, "use_source", None)
            if isinstance(resolved, etree._Element):
                resolved_clone = _clone_element(resolved)
                resolved_clone.attrib.pop("id", None)
                _copy_presentation_attributes(child_source, resolved_clone)
                transform_matrix = getattr(child, "transform", Matrix.identity())
                transform_value = _matrix_to_string(transform_matrix)
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


# ---------------------------------------------------------------------------
# Descriptor builders (legacy XML)
# ---------------------------------------------------------------------------


def describe_gradient_element(element: etree._Element) -> GradientDescriptor:
    tag = _local_name(element.tag)
    if tag == "linearGradient":
        return _linear_descriptor_from_element(element)
    if tag == "radialGradient":
        return _radial_descriptor_from_element(element)
    if tag == "meshgradient":
        return _mesh_descriptor_from_element(element)
    raise ValueError(f"Unsupported gradient element: {tag}")


def describe_pattern_element(element: etree._Element) -> PatternDescriptor:
    attributes = {name: value for name, value in element.attrib.items() if value is not None}
    matrix = _parse_matrix(element.get("patternTransform"))
    child_clones = tuple(_clone_element(child) for child in element)
    return PatternDescriptor(
        pattern_id=element.get("id"),
        x=_parse_float(element.get("x"), 0.0),
        y=_parse_float(element.get("y"), 0.0),
        width=_parse_float(element.get("width"), 0.0),
        height=_parse_float(element.get("height"), 0.0),
        units=element.get("patternUnits") or "objectBoundingBox",
        content_units=element.get("patternContentUnits") or "userSpaceOnUse",
        transform=matrix,
        href=_extract_href(element),
        attributes=attributes,
        children=child_clones,
    )


# ---------------------------------------------------------------------------
# Materialisers
# ---------------------------------------------------------------------------


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
    return _clone_element(descriptor.element)


def build_pattern_element(descriptor: PatternDescriptor) -> etree._Element:
    element = etree.Element("pattern")
    if descriptor.pattern_id:
        element.set("id", descriptor.pattern_id)

    for name, value in descriptor.attributes.items():
        element.set(name, value)

    element.set("x", _format_number(descriptor.x))
    element.set("y", _format_number(descriptor.y))
    element.set("width", _format_number(descriptor.width))
    element.set("height", _format_number(descriptor.height))

    if descriptor.units and descriptor.units != "objectBoundingBox":
        element.set("patternUnits", descriptor.units)
    if descriptor.content_units and descriptor.content_units != "userSpaceOnUse":
        element.set("patternContentUnits", descriptor.content_units)
    transform = _matrix_tuple_to_string(descriptor.transform)
    if transform:
        element.set("patternTransform", transform)
    if descriptor.href:
        element.set("{http://www.w3.org/1999/xlink}href", descriptor.href)

    for child in descriptor.children:
        element.append(_clone_element(child))

    return element


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _describe_stops(stops: Sequence[GradientStop]) -> tuple[GradientStopDescriptor, ...]:
    descriptors: list[GradientStopDescriptor] = []
    for stop in stops:
        descriptors.append(
            GradientStopDescriptor(
                offset=max(0.0, min(1.0, stop.offset)),
                color=_color_to_hex(stop.color),
                opacity=max(0.0, min(1.0, stop.color.a)),
            )
        )
    return tuple(descriptors)


def _assign_common_gradient_attrs(
    element: etree._Element,
    units: str,
    spread_method: str,
    transform: MatrixTuple,
    href: str | None,
) -> None:
    if units and units != "objectBoundingBox":
        element.set("gradientUnits", units)
    if spread_method and spread_method != "pad":
        element.set("spreadMethod", spread_method)
    transform_value = _matrix_tuple_to_string(transform)
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
    if name not in descriptor.specified:
        return
    element.set(name, descriptor.raw_attributes.get(name) or _format_number(value))


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
        stop_el.set("offset", _format_number(stop.offset))
        stop_el.set("stop-color", stop.color)
        if stop.opacity < 0.999:
            stop_el.set("stop-opacity", _format_number(stop.opacity))


def _linear_descriptor_from_element(element: etree._Element) -> LinearGradientDescriptor:
    transform = _parse_matrix(element.get("gradientTransform"))
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
        href=_extract_href(element),
        specified=tuple(
            key
            for key in ("x1", "y1", "x2", "y2", "gradientUnits", "spreadMethod", "gradientTransform")
            if key in element.attrib
        ),
        raw_attributes={name: value for name, value in element.attrib.items() if value is not None},
    )


def _radial_descriptor_from_element(element: etree._Element) -> RadialGradientDescriptor:
    transform = _parse_matrix(element.get("gradientTransform"))
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
        href=_extract_href(element),
        specified=tuple(
            key
            for key in ("cx", "cy", "r", "fx", "fy", "gradientUnits", "spreadMethod", "gradientTransform")
            if key in element.attrib
        ),
        raw_attributes={name: value for name, value in element.attrib.items() if value is not None},
    )


def _mesh_descriptor_from_element(element: etree._Element) -> MeshGradientDescriptor:
    attributes = {name: value for name, value in element.attrib.items() if value is not None}
    rows, cols, patch_count, stop_count, colors = _analyze_mesh_structure(element)
    href = _extract_href(element)
    element_clone = _clone_element(element)
    return MeshGradientDescriptor(
        gradient_id=element.get("id"),
        rows=rows,
        columns=cols,
        patch_count=patch_count,
        stop_count=stop_count,
        colors=tuple(sorted(colors)),
        attributes=attributes,
        element=element_clone,
        href=href,
    )


def _parse_stops(element: etree._Element) -> tuple[GradientStopDescriptor, ...]:
    stops: list[GradientStopDescriptor] = []
    for stop_el in element.findall(".//{http://www.w3.org/2000/svg}stop") + element.findall(".//stop"):
        color_attr = stop_el.get("stop-color") or _parse_style(stop_el.get("style")).get("stop-color") or "#000000"
        parsed_color = parse_color(color_attr)
        color_hex = f"#{color_to_hex(color_attr, default='000000')}"
        opacity_attr = stop_el.get("stop-opacity") or _parse_style(stop_el.get("style")).get("stop-opacity")
        color_alpha = float(getattr(parsed_color, "a", 1.0)) if parsed_color is not None else 1.0
        opacity = color_alpha * parse_opacity(opacity_attr, default=1.0)
        offset_str = stop_el.get("offset", "0")
        offset = parse_gradient_offset(offset_str)
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
        if _local_name(getattr(row, "tag", "")) != "meshrow":
            continue
        rows += 1
        row_cols = 0
        for patch in row:
            if _local_name(getattr(patch, "tag", "")) != "meshpatch":
                continue
            row_cols += 1
            patch_count += 1
            for stop_el in patch.iter():
                if _local_name(getattr(stop_el, "tag", "")) != "stop":
                    continue
                style_map = _parse_style(stop_el.get("style"))
                color_attr = stop_el.get("stop-color") or style_map.get("stop-color")
                color_hex = f"#{color_to_hex(color_attr, default='000000')}"
                colors.add(color_hex.lstrip("#").upper())
                stop_count += 1
        cols = max(cols, row_cols)

    return rows, cols, patch_count, stop_count, colors


def _parse_style(style: str | None) -> dict[str, str]:
    return parse_style_declarations(style)[0]


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        return float(token.strip("%")) / 100.0 if token.endswith("%") else float(token)
    except ValueError:
        return default


def _parse_matrix(value: str | None) -> MatrixTuple:
    if not value:
        return _matrix_to_tuple(Matrix.identity())
    token = value.strip()
    if token.startswith("matrix(") and token.endswith(")"):
        numbers = token[7:-1].replace(",", " ").split()
        if len(numbers) == 6:
            try:
                return tuple(float(n) for n in numbers)  # type: ignore[return-value]
            except ValueError:
                pass
    return _matrix_to_tuple(Matrix.identity())


def _matrix_to_tuple(matrix: Matrix) -> MatrixTuple:
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)


def _matrix_tuple_to_string(values: MatrixTuple) -> str | None:
    if values == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0):
        return None
    return f"matrix({_format_number(values[0])} {_format_number(values[1])} {_format_number(values[2])} {_format_number(values[3])} {_format_number(values[4])} {_format_number(values[5])})"


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _color_to_hex(color: Color) -> str:
    return rgb_object_to_hex(color, prefix="#", scale="unit") or "#000000"


def _normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) in {3, 6}:
        try:
            int(token, 16)
            if len(token) == 3:
                token = "".join(ch * 2 for ch in token)
            return f"#{token.upper()}"
        except ValueError:
            return None
    return None


def _matrix_to_string(matrix: Matrix) -> str | None:
    return _matrix_tuple_to_string(_matrix_to_tuple(matrix))


def _extract_href(element: etree._Element) -> str | None:
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
    return href if href else None


def _clone_element(node: etree._Element) -> etree._Element:
    return deepcopy(node)


def _copy_presentation_attributes(source: etree._Element | None, target: etree._Element) -> None:
    if source is None:
        return
    for name, value in source.attrib.items():
        if value is None:
            continue
        local = _local_name(name)
        if local in {"href", "width", "height", "x", "y"}:
            continue
        if local == "style":
            existing = target.get("style")
            target.set("style", f"{existing};{value}" if existing else value)
            continue
        if name not in target.attrib:
            target.set(name, value)


__all__ = [
    "GradientDescriptor",
    "GradientStopDescriptor",
    "LinearGradientDescriptor",
    "RadialGradientDescriptor",
    "MeshGradientDescriptor",
    "PatternDescriptor",
    "describe_linear_gradient",
    "describe_radial_gradient",
    "describe_pattern",
    "describe_gradient_element",
    "describe_pattern_element",
    "build_linear_gradient_element",
    "build_radial_gradient_element",
    "build_mesh_gradient_element",
    "build_pattern_element",
]
