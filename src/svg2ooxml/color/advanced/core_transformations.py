"""Fluent transformation methods for advanced colors."""

from __future__ import annotations

from typing import Any

import colorspacious
import numpy as np

from .core_cache import cached_color_convert


class ColorTransformationMixin:
    """Color manipulation methods mixed into the advanced Color class."""

    def darken(self, amount: float = 0.1):
        """
        Darken the color by reducing lightness in Lab space.

        Args:
            amount: Amount to darken (0.0-1.0, values > 1.0 are clamped)

        Returns:
            New Color instance with reduced lightness
        """
        amount = max(0.0, min(1.0, amount))

        try:
            lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")
            lab[0] = max(0, lab[0] - (amount * 50))
            new_rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)
            return _with_alpha(self, new_rgb)

        except Exception:
            factor = 1.0 - amount
            new_rgb = tuple(max(0, min(255, int(c * factor))) for c in self._rgb)
            return _with_alpha(self, new_rgb)

    def lighten(self, amount: float = 0.1):
        """
        Lighten the color by increasing lightness in Lab space.

        Args:
            amount: Amount to lighten (0.0-1.0, values > 1.0 are clamped)

        Returns:
            New Color instance with increased lightness
        """
        amount = max(0.0, min(1.0, amount))

        try:
            lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")
            lab[0] = min(100, lab[0] + (amount * 50))
            new_rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)
            return _with_alpha(self, new_rgb)

        except Exception:
            factor = 1.0 + amount
            new_rgb = tuple(max(0, min(255, int(c * factor))) for c in self._rgb)
            return _with_alpha(self, new_rgb)

    def saturate(self, amount: float = 0.1):
        """
        Increase color saturation in LCH space.

        Args:
            amount: Amount to increase saturation

        Returns:
            New Color instance with increased saturation
        """
        try:
            lch = cached_color_convert(self._rgb, "sRGB255", "CIELCh")
            lch[1] = max(0, lch[1] + (amount * 50))
            new_rgb = cached_color_convert(lch, "CIELCh", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)
            return _with_alpha(self, new_rgb)

        except Exception:
            hsl = self._rgb_to_hsl(*self._rgb)
            new_s = max(0, min(1, hsl[1] + amount))
            new_rgb = self._hsl_to_rgb(hsl[0], new_s, hsl[2])
            return _with_alpha(self, new_rgb)

    def desaturate(self, amount: float = 0.1):
        """
        Decrease color saturation in LCH space.

        Args:
            amount: Amount to decrease saturation

        Returns:
            New Color instance with decreased saturation
        """
        return self.saturate(-amount)

    def adjust_hue(self, degrees: float):
        """
        Adjust hue by rotating in HSL color space.

        Args:
            degrees: Degrees to rotate hue (-360 to 360)

        Returns:
            New Color instance with adjusted hue
        """
        hsl = self._rgb_to_hsl(*self._rgb)
        new_hue = (hsl[0] + degrees) % 360
        new_rgb = self._hsl_to_rgb(new_hue, hsl[1], hsl[2])
        return _with_alpha(self, new_rgb)

    def temperature(self, kelvin: int):
        """
        Adjust color temperature using blackbody radiation approximation.

        Args:
            kelvin: Target color temperature (1000-40000K)

        Returns:
            New Color instance with adjusted temperature
        """
        if not 1000 <= kelvin <= 40000:
            raise ValueError(f"Color temperature must be 1000-40000K, got {kelvin}")

        red, green, blue = _blackbody_rgb(kelvin)
        temp_color = self.__class__((int(red), int(green), int(blue)))
        original_rgb = np.array(self.rgb(), dtype=np.float32)
        temp_rgb = np.array(temp_color.rgb(), dtype=np.float32)
        blend_factor = 0.3
        blended_rgb = ((1 - blend_factor) * original_rgb + blend_factor * temp_rgb)
        blended_rgb = np.clip(blended_rgb, 0, 255).astype(int)
        return _with_alpha(self, tuple(int(c) for c in blended_rgb))

    def alpha(self, value: float):
        """
        Set alpha channel value.

        Args:
            value: Alpha value (0.0-1.0)

        Returns:
            New Color instance with specified alpha
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {value}")

        new_color = object.__new__(self.__class__)
        new_color._input_value = self._input_value
        new_color._rgb = self._rgb
        new_color._alpha = value
        return new_color


def _with_alpha(source: Any, rgb: tuple[int, int, int]):
    new_color = source.__class__(rgb)
    new_color._alpha = source._alpha
    return new_color


def _blackbody_rgb(kelvin: int) -> tuple[float, float, float]:
    temp = kelvin / 100.0

    if temp <= 66:
        red = 255
    else:
        red = temp - 60
        red = 329.698727446 * (red**-0.1332047592)
        red = max(0, min(255, red))

    if temp <= 66:
        green = temp
        green = 99.4708025861 * np.log(green) - 161.1195681661
        green = max(0, min(255, green))
    else:
        green = temp - 60
        green = 288.1221695283 * (green**-0.0755148492)
        green = max(0, min(255, green))

    if temp >= 66:
        blue = 255
    elif temp <= 19:
        blue = 0
    else:
        blue = temp - 10
        blue = 138.5177312231 * np.log(blue) - 305.0447927307
        blue = max(0, min(255, blue))

    return red, green, blue


__all__ = ["ColorTransformationMixin"]
