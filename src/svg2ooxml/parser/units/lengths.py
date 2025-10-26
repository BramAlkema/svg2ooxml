"""Length conversion and viewBox helpers."""

from __future__ import annotations

from svg2ooxml.units import ConversionContext, UnitConverter


def viewbox_to_px(
    viewbox: tuple[float, float, float, float],
    width: float,
    height: float,
) -> tuple[float, float]:
    """Return scale factors that map the provided viewBox into the viewport."""

    _, _, vb_width, vb_height = viewbox
    if vb_width == 0 or vb_height == 0:
        return width, height
    scale_x = width / vb_width
    scale_y = height / vb_height
    return scale_x, scale_y


__all__ = ["ConversionContext", "UnitConverter", "viewbox_to_px"]
