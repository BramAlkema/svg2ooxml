"""Style context and viewport helpers for the parser."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.viewbox import resolve_viewbox_dimensions

from .units import ConversionContext, UnitConverter


@dataclass(slots=True)
class StyleContext:
    """Lightweight style context capturing viewport information."""

    conversion: ConversionContext
    viewport_width: float
    viewport_height: float


def build_style_context(
    svg_root: etree._Element,
    unit_converter: UnitConverter,
    default_width: float | None = 800.0,
    default_height: float | None = 600.0,
) -> StyleContext:
    """Create a style context containing viewport dimensions."""

    width_px, height_px = resolve_viewport(
        svg_root,
        unit_converter,
        default_width=default_width,
        default_height=default_height,
    )
    conversion = unit_converter.create_context(
        width=width_px,
        height=height_px,
        font_size=12.0,
        dpi=unit_converter.dpi,
        parent_width=width_px,
        parent_height=height_px,
    )
    return StyleContext(
        conversion=conversion,
        viewport_width=width_px,
        viewport_height=height_px,
    )


def resolve_viewport(
    svg_root: etree._Element,
    unit_converter: UnitConverter,
    *,
    default_width: float | None = None,
    default_height: float | None = None,
) -> tuple[float, float]:
    """Resolve viewport width/height in pixels."""

    width_px, height_px, _, _ = resolve_viewbox_dimensions(
        svg_root,
        unit_converter,
        default_width=default_width or 800.0,
        default_height=default_height or 600.0,
    )
    return width_px, height_px


__all__ = ["StyleContext", "build_style_context", "resolve_viewport"]
