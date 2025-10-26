#!/usr/bin/env python3
"""
Color Space Conversion Engine

This module provides comprehensive color space conversion algorithms including
modern perceptually uniform color spaces like OKLab and OKLCh.

Key Features:
- OKLab: Modern perceptually uniform color space for better color mixing
- OKLCh: Cylindrical form of OKLab for intuitive color manipulation
- High accuracy conversion algorithms based on official specifications
- Optimized for performance with NumPy operations
"""

from typing import Tuple

import numpy as np


class ColorSpaceConverter:
    """
    High-performance color space conversion engine.

    Provides conversion algorithms between RGB, OKLab, and OKLCh color spaces
    with professional accuracy and performance optimization.
    """

    @staticmethod
    def rgb_to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
        """
        Convert sRGB to OKLab color space using the OKLab standard.

        OKLab is a perceptually uniform color space designed for better
        color mixing and manipulation than sRGB or CIE Lab.

        Args:
            r, g, b: RGB values (0-255)

        Returns:
            (L, a, b) tuple where L is lightness (0-1), a and b are color coordinates

        References:
            Björn Ottosson (2020). "A perceptual color space for image processing"
            https://bottosson.github.io/posts/oklab/
        """
        # Convert to 0-1 range
        r, g, b = r / 255.0, g / 255.0, b / 255.0

        # sRGB to linear RGB conversion (gamma correction)
        def srgb_to_linear(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r = srgb_to_linear(r)
        g = srgb_to_linear(g)
        b = srgb_to_linear(b)

        # Linear RGB to OKLab transformation matrix
        # Based on Björn Ottosson's OKLab specification
        l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
        m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
        s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

        # Apply cube root for perceptual uniformity
        l_prime = np.cbrt(l) if l >= 0 else -np.cbrt(-l)
        m_prime = np.cbrt(m) if m >= 0 else -np.cbrt(-m)
        s_prime = np.cbrt(s) if s >= 0 else -np.cbrt(-s)

        # Convert to OKLab coordinates
        ok_l = 0.2104542553 * l_prime + 0.7936177850 * m_prime - 0.0040720468 * s_prime
        ok_a = 1.9779984951 * l_prime - 2.4285922050 * m_prime + 0.4505937099 * s_prime
        ok_b = 0.0259040371 * l_prime + 0.7827717662 * m_prime - 0.8086757660 * s_prime

        return (ok_l, ok_a, ok_b)

    @staticmethod
    def oklab_to_rgb(l: float, a: float, b: float) -> tuple[int, int, int]:
        """
        Convert OKLab to sRGB color space.

        Args:
            l: Lightness (0-1)
            a, b: Color coordinates

        Returns:
            (r, g, b) tuple with values 0-255

        References:
            Björn Ottosson (2020). "A perceptual color space for image processing"
        """
        # OKLab to linear RGB transformation (inverse of above)
        l_prime = l + 0.3963377774 * a + 0.2158037573 * b
        m_prime = l - 0.1055613458 * a - 0.0638541728 * b
        s_prime = l - 0.0894841775 * a - 1.2914855480 * b

        # Apply cube to reverse cube root
        l_lin = l_prime ** 3
        m_lin = m_prime ** 3
        s_lin = s_prime ** 3

        # Linear RGB from LMS cone response
        r = +4.0767416621 * l_lin - 3.3077115913 * m_lin + 0.2309699292 * s_lin
        g = -1.2684380046 * l_lin + 2.6097574011 * m_lin - 0.3413193965 * s_lin
        b = -0.0041960863 * l_lin - 0.7034186147 * m_lin + 1.7076147010 * s_lin

        # Linear RGB to sRGB conversion (inverse gamma correction)
        def linear_to_srgb(c):
            return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055

        r = linear_to_srgb(r)
        g = linear_to_srgb(g)
        b = linear_to_srgb(b)

        # Clamp and convert to 0-255 range
        r = max(0, min(255, int(round(r * 255))))
        g = max(0, min(255, int(round(g * 255))))
        b = max(0, min(255, int(round(b * 255))))

        return (r, g, b)

    @staticmethod
    def oklab_to_oklch(l: float, a: float, b: float) -> tuple[float, float, float]:
        """
        Convert OKLab to OKLCh (cylindrical coordinates).

        OKLCh provides intuitive control over lightness, chroma, and hue
        while maintaining the perceptual advantages of OKLab.

        Args:
            l: Lightness
            a, b: Color coordinates

        Returns:
            (L, C, h) tuple where h is in degrees (0-360)
        """
        c = np.sqrt(a * a + b * b)
        h = np.degrees(np.arctan2(b, a))
        if h < 0:
            h += 360
        return (l, c, h)

    @staticmethod
    def oklch_to_oklab(l: float, c: float, h: float) -> tuple[float, float, float]:
        """
        Convert OKLCh to OKLab.

        Args:
            l: Lightness (0-1)
            c: Chroma (saturation)
            h: Hue in degrees (0-360)

        Returns:
            (L, a, b) tuple
        """
        h_rad = np.radians(h)
        a = c * np.cos(h_rad)
        b = c * np.sin(h_rad)
        return (l, a, b)

    @classmethod
    def rgb_to_oklch(cls, r: int, g: int, b: int) -> tuple[float, float, float]:
        """
        Direct conversion from RGB to OKLCh.

        Args:
            r, g, b: RGB values (0-255)

        Returns:
            (L, C, h) tuple for OKLCh
        """
        oklab = cls.rgb_to_oklab(r, g, b)
        return cls.oklab_to_oklch(*oklab)

    @classmethod
    def oklch_to_rgb(cls, l: float, c: float, h: float) -> tuple[int, int, int]:
        """
        Direct conversion from OKLCh to RGB.

        Args:
            l: Lightness (0-1)
            c: Chroma
            h: Hue in degrees

        Returns:
            (r, g, b) tuple with values 0-255
        """
        oklab = cls.oklch_to_oklab(l, c, h)
        return cls.oklab_to_rgb(*oklab)


# Convenience functions for direct access
def rgb_to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to OKLab."""
    return ColorSpaceConverter.rgb_to_oklab(r, g, b)


def oklab_to_rgb(l: float, a: float, b: float) -> tuple[int, int, int]:
    """Convert OKLab to RGB."""
    return ColorSpaceConverter.oklab_to_rgb(l, a, b)


def rgb_to_oklch(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to OKLCh."""
    return ColorSpaceConverter.rgb_to_oklch(r, g, b)


def oklch_to_rgb(l: float, c: float, h: float) -> tuple[int, int, int]:
    """Convert OKLCh to RGB."""
    return ColorSpaceConverter.oklch_to_rgb(l, c, h)


def oklab_to_oklch(l: float, a: float, b: float) -> tuple[float, float, float]:
    """Convert OKLab to OKLCh."""
    return ColorSpaceConverter.oklab_to_oklch(l, a, b)


def oklch_to_oklab(l: float, c: float, h: float) -> tuple[float, float, float]:
    """Convert OKLCh to OKLab."""
    return ColorSpaceConverter.oklch_to_oklab(l, c, h)