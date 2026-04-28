"""Output and color-space accessors for advanced colors."""

from __future__ import annotations

import colorspacious

from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string

from .color_spaces import ColorSpaceConverter


class ColorOutputMixin:
    """Output format methods mixed into the advanced Color class."""

    def hex(self, include_hash: bool = False) -> str:
        """
        Get hexadecimal representation.

        Args:
            include_hash: Whether to include '#' prefix

        Returns:
            Hex color string
        """
        if self._rgb is None:
            raise ValueError("Color not properly initialized")

        hex_str = f"{self._rgb[0]:02x}{self._rgb[1]:02x}{self._rgb[2]:02x}"
        return f"#{hex_str}" if include_hash else hex_str

    def rgb(self) -> tuple[int, int, int]:
        """
        Get RGB tuple.

        Returns:
            RGB values as (r, g, b) tuple
        """
        if self._rgb is None:
            raise ValueError("Color not properly initialized")
        return self._rgb

    def rgba(self) -> tuple[int, int, int, float]:
        """
        Get RGBA tuple.

        Returns:
            RGBA values as (r, g, b, a) tuple
        """
        if self._rgb is None:
            raise ValueError("Color not properly initialized")
        return (*self._rgb, self._alpha)

    def lab(self) -> tuple[float, float, float]:
        """
        Get CIE Lab representation using colorspacious.

        Returns:
            Lab values as (L*, a*, b*) tuple
        """
        lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")
        return tuple(float(x) for x in lab)

    def lch(self) -> tuple[float, float, float]:
        """
        Get CIE LCH representation using colorspacious.

        Returns:
            LCH values as (L*, C*, h°) tuple
        """
        lch = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELCh")
        return tuple(float(x) for x in lch)

    def hsl(self) -> tuple[float, float, float]:
        """
        Get HSL representation.

        Returns:
            HSL values as (h, s, l) tuple
        """
        return self._rgb_to_hsl(*self._rgb)

    def oklab(self) -> tuple[float, float, float]:
        """
        Get OKLab representation - a modern perceptually uniform color space.

        Returns:
            OKLab values as (L, a, b) tuple.
        """
        return ColorSpaceConverter.rgb_to_oklab(*self._rgb)

    def oklch(self) -> tuple[float, float, float]:
        """
        Get OKLCh representation - cylindrical form of OKLab.

        Returns:
            OKLCh values as (L, C, h) tuple.
        """
        return ColorSpaceConverter.rgb_to_oklch(*self._rgb)

    def to_xyz(self) -> tuple[float, float, float]:
        """
        Get CIE XYZ representation using colorspacious.

        Returns:
            XYZ values tuple
        """
        xyz = colorspacious.cspace_convert(self._rgb, "sRGB255", "XYZ100")
        return tuple(float(x) for x in xyz)

    def drawingml(self) -> str:
        """
        Get PowerPoint DrawingML representation.

        Returns:
            DrawingML XML string for PowerPoint integration
        """
        if self._alpha == 0.0:
            noFill = a_elem("noFill")
            return to_string(noFill)

        srgbClr = a_elem("srgbClr", val=self.hex())

        if self._alpha < 1.0:
            a_sub(srgbClr, "alpha", val=opacity_to_ppt(self._alpha))

        return to_string(srgbClr)


__all__ = ["ColorOutputMixin"]
