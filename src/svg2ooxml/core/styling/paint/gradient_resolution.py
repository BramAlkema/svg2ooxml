"""SVG gradient chain and coordinate resolution helpers."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.gradient_units import parse_gradient_coordinate
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.styling.style_helpers import (
    parse_offset,
    parse_stop_color,
)
from svg2ooxml.ir.paint import GradientStop


def gradient_attr(
    chain: list[etree._Element],
    attribute: str,
    *,
    default: str | None = None,
) -> str | None:
    if attribute == "__tag__":
        return local_name(chain[0].tag)
    for element in chain:
        value = element.get(attribute)
        if value is not None:
            return value
    return default


def collect_gradient_stops(
    chain: list[etree._Element],
    opacity: float,
) -> list[GradientStop]:
    for element in chain:
        stops = list(element.findall(".//{http://www.w3.org/2000/svg}stop"))
        if not stops:
            stops = list(element.findall(".//stop"))
        if stops:
            parsed = parse_stops(stops, opacity)
            if len(parsed) == 1:
                first = parsed[0]
                return [
                    GradientStop(offset=0.0, rgb=first.rgb, opacity=first.opacity),
                    GradientStop(offset=1.0, rgb=first.rgb, opacity=first.opacity),
                ]
            return parsed
    return []


def parse_stops(
    stops: list[etree._Element],
    opacity: float,
) -> list[GradientStop]:
    parsed: list[GradientStop] = []
    for stop in stops:
        offset_str = stop.get("offset", "0")
        offset = parse_offset(offset_str)
        color, stop_opacity = parse_stop_color(stop)
        total_opacity = max(0.0, min(1.0, stop_opacity * opacity))
        parsed.append(GradientStop(offset=offset, rgb=color, opacity=total_opacity))
    parsed.sort(key=lambda stop: stop.offset)
    return parsed


def resolve_gradient_point(
    chain: list[etree._Element],
    attr_x: str,
    attr_y: str,
    *,
    default: tuple[str, str] | None,
    units: str,
    conversion,
    axis_defaults: tuple[str, str],
    unit_converter,
) -> tuple[float, float]:
    x_value = gradient_attr(chain, attr_x, default=default[0] if default else None)
    y_value = gradient_attr(chain, attr_y, default=default[1] if default else None)
    return (
        resolve_gradient_length(
            chain,
            attr_x,
            x_value,
            units,
            conversion,
            axis_defaults[0],
            unit_converter=unit_converter,
        ),
        resolve_gradient_length(
            chain,
            attr_y,
            y_value,
            units,
            conversion,
            axis_defaults[1],
            unit_converter=unit_converter,
        ),
    )


def resolve_gradient_length(
    chain: list[etree._Element],
    attribute: str,
    default: str | None,
    units: str,
    conversion,
    axis: str,
    *,
    unit_converter=None,
) -> float:
    value = gradient_attr(chain, attribute, default=default)
    if value is None:
        return 0.0
    return parse_gradient_coordinate(
        value,
        units=units,
        context=conversion,
        axis=axis,
        default=default or "0",
        unit_converter=unit_converter,
    )


__all__ = [
    "collect_gradient_stops",
    "gradient_attr",
    "parse_stops",
    "resolve_gradient_length",
    "resolve_gradient_point",
]
