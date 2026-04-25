"""Parsing helpers shared across filter primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

from svg2ooxml.common.units import UnitConverter

_CHANNELS = {"R", "G", "B", "A"}


@dataclass
class DisplacementMapParameters:
    source_graphic: str
    displacement_map: str
    scale: float
    x_channel: str
    y_channel: str
    result: str | None


@dataclass
class TurbulenceParameters:
    base_frequency_x: float
    base_frequency_y: float
    num_octaves: int
    seed: float
    turbulence_type: str
    stitch_tiles: bool
    result: str | None


def parse_channel(value: str | None) -> str:
    token = (value or "A").strip().upper()
    return token if token in _CHANNELS else "A"


def parse_float_list(payload: str | None) -> list[float]:
    """Parse a whitespace/comma-separated string of floats."""
    if not payload:
        return []
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    return parse_numeric_list(payload)


def parse_number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def parse_length(
    value: str | None,
    default: float = 0.0,
    *,
    context: Any | None = None,
    axis: str = "x",
) -> float:
    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default

    unit_converter = getattr(context, "unit_converter", None)
    conversion_context = getattr(context, "conversion_context", None)
    if unit_converter is None and context is not None:
        services = getattr(context, "services", None)
        resolver = getattr(services, "resolve", None)
        if callable(resolver):
            unit_converter = resolver("unit_converter")
            conversion_context = conversion_context or resolver("conversion_context")
            style_context = resolver("style_context")
            if conversion_context is None and style_context is not None:
                conversion_context = getattr(style_context, "conversion", None)

    if unit_converter is None:
        unit_converter = UnitConverter()
    if conversion_context is None and context is not None:
        viewport = getattr(context, "viewport", None)
        if isinstance(viewport, dict):
            width = float(viewport.get("width") or 0.0)
            height = float(viewport.get("height") or 0.0)
            conversion_context = unit_converter.create_context(
                width=width,
                height=height,
                parent_width=width,
                parent_height=height,
                viewport_width=width,
                viewport_height=height,
            )

    try:
        return float(unit_converter.to_px(token, conversion_context, axis=axis))
    except Exception:
        return parse_number(token, default=default)


def parse_displacement_map(element: etree._Element) -> DisplacementMapParameters:
    """Return structured parameters for an ``feDisplacementMap`` element."""

    return DisplacementMapParameters(
        source_graphic=element.get("in", "SourceGraphic"),
        displacement_map=element.get("in2", "SourceGraphic"),
        scale=parse_number(element.get("scale")),
        x_channel=parse_channel(element.get("xChannelSelector")),
        y_channel=parse_channel(element.get("yChannelSelector")),
        result=element.get("result"),
    )


def parse_turbulence(element: etree._Element) -> TurbulenceParameters:
    """Return structured parameters for an ``feTurbulence`` element."""

    base_frequency = (element.get("baseFrequency") or "0").strip()
    if " " in base_frequency:
        fx_str, fy_str = base_frequency.split(" ", 1)
    else:
        fx_str = fy_str = base_frequency

    stitch_tiles = (element.get("stitchTiles") or "no").strip().lower() == "stitch"

    return TurbulenceParameters(
        base_frequency_x=parse_number(fx_str),
        base_frequency_y=parse_number(fy_str),
        num_octaves=max(0, int(parse_number(element.get("numOctaves"), default=1))),
        seed=parse_number(element.get("seed")),
        turbulence_type=(element.get("type") or "turbulence").strip(),
        stitch_tiles=stitch_tiles,
        result=element.get("result"),
    )


__all__ = [
    "DisplacementMapParameters",
    "TurbulenceParameters",
    "parse_channel",
    "parse_float_list",
    "parse_length",
    "parse_number",
    "parse_displacement_map",
    "parse_turbulence",
]
