"""Parsing helpers shared across filter primitives."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

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
    values: list[float] = []
    for token in payload.replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def parse_number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


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
    "parse_number",
    "parse_displacement_map",
    "parse_turbulence",
]
