"""Gradient parsing and inheritance helpers for the lightweight resvg tree."""

from __future__ import annotations

from collections.abc import Mapping

from svg2ooxml.common.gradient_units import (
    normalize_gradient_units,
    parse_gradient_coordinate,
    parse_gradient_offset,
)
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.common.units.conversion import ConversionContext
from svg2ooxml.common.units.lengths import parse_number_or_percent
from svg2ooxml.core.resvg.geometry.matrix import Matrix, matrix_from_commands
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop,
    LinearGradient,
    RadialGradient,
)
from svg2ooxml.core.resvg.painting.paint import parse_color
from svg2ooxml.core.resvg.parser.presentation import parse_transform
from svg2ooxml.core.resvg.parser.tree import SvgNode

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def parse_linear_gradient(
    node: SvgNode,
    context: ConversionContext | None,
) -> LinearGradient:
    attributes = node.attributes
    units = normalize_gradient_units(attributes.get("gradientUnits"))
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("gradientTransform")))
    stops_list = _parse_stops(node)
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("x1", "y1", "x2", "y2", "gradientUnits", "spreadMethod", "gradientTransform")
        if key in attributes
    )
    return LinearGradient(
        x1=parse_gradient_coordinate(
            attributes.get("x1"), units=units, context=context, axis="x", default="0%"
        ),
        y1=parse_gradient_coordinate(
            attributes.get("y1"), units=units, context=context, axis="y", default="0%"
        ),
        x2=parse_gradient_coordinate(
            attributes.get("x2"), units=units, context=context, axis="x", default="100%"
        ),
        y2=parse_gradient_coordinate(
            attributes.get("y2"), units=units, context=context, axis="y", default="0%"
        ),
        units=units,
        spread_method=attributes.get("spreadMethod") or "pad",
        transform=transform_matrix,
        stops=tuple(stops_list),
        href=href,
        specified=specified,
        raw_attributes=dict(attributes),
        context=context,
    )


def parse_radial_gradient(
    node: SvgNode,
    context: ConversionContext | None,
) -> RadialGradient:
    attributes = node.attributes
    units = normalize_gradient_units(attributes.get("gradientUnits"))
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("gradientTransform")))
    stops_list = _parse_stops(node)
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("cx", "cy", "r", "fx", "fy", "gradientUnits", "spreadMethod", "gradientTransform")
        if key in attributes
    )
    default_cx = parse_gradient_coordinate(
        attributes.get("cx"), units=units, context=context, axis="x", default="50%"
    )
    default_cy = parse_gradient_coordinate(
        attributes.get("cy"), units=units, context=context, axis="y", default="50%"
    )
    return RadialGradient(
        cx=default_cx,
        cy=default_cy,
        r=parse_gradient_coordinate(
            attributes.get("r"), units=units, context=context, axis="x", default="50%"
        ),
        fx=parse_gradient_coordinate(
            attributes.get("fx"),
            units=units,
            context=context,
            axis="x",
            default=str(default_cx),
        ),
        fy=parse_gradient_coordinate(
            attributes.get("fy"),
            units=units,
            context=context,
            axis="y",
            default=str(default_cy),
        ),
        units=units,
        spread_method=attributes.get("spreadMethod") or "pad",
        transform=transform_matrix,
        stops=tuple(stops_list),
        href=href,
        specified=specified,
        raw_attributes=dict(attributes),
        context=context,
    )


def resolve_linear_gradient_reference(
    node: object,
    paint_servers: Mapping[str, object],
    visited: set[str],
) -> LinearGradient:
    chain = _linear_gradient_chain(node, paint_servers, visited)
    gradient = chain[0]
    units = _resolved_gradient_units(chain)
    x1 = _resolved_gradient_coordinate(chain, "x1", units=units, axis="x", default="0%")
    y1 = _resolved_gradient_coordinate(chain, "y1", units=units, axis="y", default="0%")
    x2 = _resolved_gradient_coordinate(chain, "x2", units=units, axis="x", default="100%")
    y2 = _resolved_gradient_coordinate(chain, "y2", units=units, axis="y", default="0%")
    return LinearGradient(
        x1=_required(x1),
        y1=_required(y1),
        x2=_required(x2),
        y2=_required(y2),
        units=units,
        spread_method=_resolved_gradient_token(chain, "spreadMethod", default="pad") or "pad",
        transform=_resolved_gradient_transform(chain),
        stops=_resolved_gradient_stops(chain),
        href=None,
        specified=_merged_gradient_specified(chain),
        raw_attributes=dict(gradient.raw_attributes),
        context=gradient.context,
    )


def resolve_radial_gradient_reference(
    node: object,
    paint_servers: Mapping[str, object],
    visited: set[str],
) -> RadialGradient:
    chain = _radial_gradient_chain(node, paint_servers, visited)
    gradient = chain[0]
    units = _resolved_gradient_units(chain)
    cx = _resolved_gradient_coordinate(chain, "cx", units=units, axis="x", default="50%")
    cy = _resolved_gradient_coordinate(chain, "cy", units=units, axis="y", default="50%")
    radius = _resolved_gradient_coordinate(chain, "r", units=units, axis="x", default="50%")
    fx = _resolved_gradient_coordinate(chain, "fx", units=units, axis="x", default=None)
    fy = _resolved_gradient_coordinate(chain, "fy", units=units, axis="y", default=None)
    resolved_cx = _required(cx)
    resolved_cy = _required(cy)
    return RadialGradient(
        cx=resolved_cx,
        cy=resolved_cy,
        r=_required(radius),
        fx=resolved_cx if fx is None else fx,
        fy=resolved_cy if fy is None else fy,
        units=units,
        spread_method=_resolved_gradient_token(chain, "spreadMethod", default="pad") or "pad",
        transform=_resolved_gradient_transform(chain),
        stops=_resolved_gradient_stops(chain),
        href=None,
        specified=_merged_gradient_specified(chain),
        raw_attributes=dict(gradient.raw_attributes),
        context=gradient.context,
    )


def _parse_stops(node: SvgNode) -> list[GradientStop]:
    stops: list[GradientStop] = []
    for child in node.children:
        if _strip_namespace(child.tag) != "stop":
            continue
        stop = _parse_stop(child)
        if stop is not None:
            stops.append(stop)
    stops.sort(key=lambda s: s.offset)
    return stops


def _parse_stop(node: SvgNode) -> GradientStop | None:
    offset = parse_gradient_offset(node.attributes.get("offset"))
    color_value = node.styles.get("stop-color") or node.attributes.get("stop-color")
    opacity_value = node.styles.get("stop-opacity") or node.attributes.get("stop-opacity")
    opacity = parse_number_or_percent(opacity_value, 1.0)
    color = parse_color(color_value or "#000000", opacity)
    if color is None:
        color = parse_color("#000000", opacity)
    return GradientStop(offset=offset, color=color)


def _linear_gradient_chain(
    node: object,
    paint_servers: Mapping[str, object],
    visited: set[str],
) -> list[LinearGradient]:
    gradient = getattr(node, "gradient", None)
    assert isinstance(gradient, LinearGradient)
    chain = [gradient]
    href = gradient.href
    while ref_id := local_url_id(href):
        if ref_id in visited:
            break
        visited.add(ref_id)
        parent = paint_servers.get(ref_id)
        gradient = getattr(parent, "gradient", None)
        if not isinstance(gradient, LinearGradient):
            break
        chain.append(gradient)
        href = gradient.href
    return chain


def _radial_gradient_chain(
    node: object,
    paint_servers: Mapping[str, object],
    visited: set[str],
) -> list[RadialGradient]:
    gradient = getattr(node, "gradient", None)
    assert isinstance(gradient, RadialGradient)
    chain = [gradient]
    href = gradient.href
    while ref_id := local_url_id(href):
        if ref_id in visited:
            break
        visited.add(ref_id)
        parent = paint_servers.get(ref_id)
        gradient = getattr(parent, "gradient", None)
        if not isinstance(gradient, RadialGradient):
            break
        chain.append(gradient)
        href = gradient.href
    return chain


def _resolved_gradient_units(chain: list[LinearGradient] | list[RadialGradient]) -> str:
    return normalize_gradient_units(
        _resolved_gradient_token(chain, "gradientUnits", default="objectBoundingBox")
    )


def _resolved_gradient_token(
    chain: list[LinearGradient] | list[RadialGradient],
    attribute: str,
    *,
    default: str | None,
) -> str | None:
    for gradient in chain:
        if attribute in gradient.specified:
            return gradient.raw_attributes.get(attribute) or default
    return default


def _resolved_gradient_transform(
    chain: list[LinearGradient] | list[RadialGradient],
) -> Matrix:
    for gradient in chain:
        if "gradientTransform" in gradient.specified:
            return gradient.transform
    return Matrix.identity()


def _resolved_gradient_stops(
    chain: list[LinearGradient] | list[RadialGradient],
) -> tuple[GradientStop, ...]:
    for gradient in chain:
        if gradient.stops:
            return gradient.stops
    return ()


def _resolved_gradient_coordinate(
    chain: list[LinearGradient] | list[RadialGradient],
    attribute: str,
    *,
    units: str,
    axis: str,
    default: str | None,
) -> float | None:
    for gradient in chain:
        if attribute in gradient.specified:
            return parse_gradient_coordinate(
                gradient.raw_attributes.get(attribute),
                units=units,
                context=gradient.context,
                axis=axis,
                default=default or "0",
            )
    if default is None:
        return None
    source = chain[0]
    return parse_gradient_coordinate(
        default,
        units=units,
        context=source.context,
        axis=axis,
        default=default,
    )


def _merged_gradient_specified(
    chain: list[LinearGradient] | list[RadialGradient],
) -> tuple[str, ...]:
    merged: set[str] = set()
    for gradient in chain:
        merged.update(gradient.specified)
    return tuple(sorted(merged))


def _required(value: float | None) -> float:
    return 0.0 if value is None else value


def _extract_href(attributes: Mapping[str, str]) -> str | None:
    for key in ("href", "{http://www.w3.org/1999/xlink}href"):
        if key in attributes:
            return attributes[key]
    return None


def _strip_namespace(tag: object) -> str:
    tag_str = str(tag)
    if tag_str.startswith("{" + SVG_NAMESPACE + "}"):
        return tag_str[len(SVG_NAMESPACE) + 2 :]
    return tag_str


__all__ = [
    "parse_linear_gradient",
    "parse_radial_gradient",
    "resolve_linear_gradient_reference",
    "resolve_radial_gradient_reference",
]
