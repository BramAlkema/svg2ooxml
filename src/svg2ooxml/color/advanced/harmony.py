#!/usr/bin/env python3
"""
Color harmony generation utilities.

Provides ColorHarmony class for generating complementary, analogous,
triadic, and other color harmony schemes using perceptually accurate
color space operations.
"""

from __future__ import annotations

from typing import List, Tuple

import colorspacious
import numpy as np

from .core import Color


class ColorHarmony:
    """
    Generate color harmony schemes using perceptually accurate color spaces.

    Uses LCH color space for hue-based harmonies to ensure visually pleasing
    color relationships that work well in design applications.

    Examples:
        >>> base = Color('#ff6b6b')
        >>> harmony = ColorHarmony(base)
        >>> complementary = harmony.complementary()
        >>> analogous = harmony.analogous(count=5)
    """

    def __init__(self, base_color: Color):
        """
        Initialize ColorHarmony with a base color.

        Args:
            base_color: Base color for generating harmonies

        Raises:
            TypeError: If base_color is not a Color instance
        """
        if not isinstance(base_color, Color):
            raise TypeError("base_color must be a Color instance")
        self.base_color = base_color

    def complementary(self) -> Color:
        """
        Generate complementary color (180° opposite in hue).

        Returns:
            Complementary Color instance
        """
        try:
            # Convert base color to LCH for hue manipulation
            lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            # Add 180° to hue for complementary color
            complement_lch = lch.copy()
            complement_lch[2] = (lch[2] + 180) % 360

            # Convert back to RGB
            complement_rgb = colorspacious.cspace_convert(complement_lch, "CIELCh", "sRGB255")
            complement_rgb = tuple(max(0, min(255, int(c))) for c in complement_rgb)

            complement_color = Color(complement_rgb)
            complement_color._alpha = getattr(self.base_color, '_alpha', 1.0)
            return complement_color

        except Exception:
            # Fallback using simple RGB inversion
            base_rgb = self.base_color.rgb()
            complement_rgb = tuple(255 - c for c in base_rgb)
            complement_color = Color(complement_rgb)
            complement_color._alpha = getattr(self.base_color, '_alpha', 1.0)
            return complement_color

    def analogous(self, count: int = 5, spread: float = 30.0) -> list[Color]:
        """
        Generate analogous color harmony (adjacent hues).

        Args:
            count: Number of colors to generate (odd numbers work best)
            spread: Total hue spread in degrees

        Returns:
            List of analogous colors

        Raises:
            ValueError: If count < 3
        """
        if count < 3:
            raise ValueError("count must be at least 3")

        # Convert base color to LCH for hue manipulation
        base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

        # Generate hue offsets centered around base hue
        half_spread = spread / 2.0
        hue_offsets = np.linspace(-half_spread, half_spread, count)

        analogous_colors = []
        for offset in hue_offsets:
            # Create new color with offset hue
            new_lch = base_lch.copy()
            new_lch[2] = (base_lch[2] + offset) % 360

            # Convert back to RGB
            new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            new_color = Color(new_rgb)
            new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
            analogous_colors.append(new_color)

        return analogous_colors

    def triadic(self) -> list[Color]:
        """
        Generate triadic color harmony (120° intervals).

        Returns:
            List of three colors in triadic harmony
        """
        try:
            # Convert base color to LCH for hue manipulation
            base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            # Generate triadic hues (0°, 120°, 240°)
            hue_offsets = [0, 120, 240]
            triadic_colors = []

            for offset in hue_offsets:
                new_lch = base_lch.copy()
                new_lch[2] = (base_lch[2] + offset) % 360

                # Convert back to RGB
                new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
                new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

                new_color = Color(new_rgb)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                triadic_colors.append(new_color)

            return triadic_colors

        except Exception:
            # Fallback using HSL hue rotation
            base_hsl = self.base_color.hsl()
            triadic_colors = []

            for offset in [0, 120, 240]:
                new_hue = (base_hsl[0] + offset) % 360
                new_color = Color.from_hsl(new_hue, base_hsl[1], base_hsl[2])
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                triadic_colors.append(new_color)

            return triadic_colors

    def split_complementary(self, spread: float = 30.0) -> list[Color]:
        """
        Generate split-complementary harmony.

        Args:
            spread: Angle spread from complement in degrees

        Returns:
            List of three colors (base + two split complements)
        """
        try:
            # Convert base color to LCH for hue manipulation
            base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            # Calculate complement hue and split positions
            complement_hue = (base_lch[2] + 180) % 360
            split_offsets = [-spread/2, spread/2]

            split_colors = [self.base_color]  # Include base color

            for offset in split_offsets:
                new_lch = base_lch.copy()
                new_lch[2] = (complement_hue + offset) % 360

                # Convert back to RGB
                new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
                new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

                new_color = Color(new_rgb)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                split_colors.append(new_color)

            return split_colors

        except Exception:
            # Fallback using HSL hue rotation
            base_hsl = self.base_color.hsl()
            complement_hue = (base_hsl[0] + 180) % 360

            split_colors = [self.base_color]

            for offset in [-spread/2, spread/2]:
                new_hue = (complement_hue + offset) % 360
                new_color = Color.from_hsl(new_hue, base_hsl[1], base_hsl[2])
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                split_colors.append(new_color)

            return split_colors

    def tetradic(self) -> list[Color]:
        """
        Generate tetradic (square) color harmony.

        Returns:
            List of four colors in tetradic harmony
        """
        try:
            # Convert base color to LCH for hue manipulation
            base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            # Generate square hues (0°, 90°, 180°, 270°)
            hue_offsets = [0, 90, 180, 270]
            tetradic_colors = []

            for offset in hue_offsets:
                new_lch = base_lch.copy()
                new_lch[2] = (base_lch[2] + offset) % 360

                # Convert back to RGB
                new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
                new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

                new_color = Color(new_rgb)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                tetradic_colors.append(new_color)

            return tetradic_colors

        except Exception:
            # Fallback using HSL hue rotation
            base_hsl = self.base_color.hsl()
            tetradic_colors = []

            for offset in [0, 90, 180, 270]:
                new_hue = (base_hsl[0] + offset) % 360
                new_color = Color.from_hsl(new_hue, base_hsl[1], base_hsl[2])
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                tetradic_colors.append(new_color)

            return tetradic_colors

    def monochromatic(self, count: int = 5,
                     lightness_range: tuple[float, float] = (20, 80)) -> list[Color]:
        """
        Generate monochromatic color scheme (same hue, different lightness).

        Args:
            count: Number of colors to generate
            lightness_range: Min and max lightness values (0-100)

        Returns:
            List of monochromatic colors
        """
        if count < 2:
            raise ValueError("count must be at least 2")

        try:
            # Convert base color to LCH for lightness manipulation
            base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            # Generate lightness values within range
            min_l, max_l = lightness_range
            lightness_values = np.linspace(min_l, max_l, count)

            monochromatic_colors = []
            for lightness in lightness_values:
                new_lch = base_lch.copy()
                new_lch[0] = lightness  # Set lightness, preserve chroma and hue

                # Convert back to RGB
                new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
                new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

                new_color = Color(new_rgb)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                monochromatic_colors.append(new_color)

            return monochromatic_colors

        except Exception:
            # Fallback using HSL lightness variation
            base_hsl = self.base_color.hsl()
            min_l, max_l = lightness_range
            # Convert to 0-1 scale for HSL
            lightness_values = np.linspace(min_l/100, max_l/100, count)

            monochromatic_colors = []
            for lightness in lightness_values:
                new_color = Color.from_hsl(base_hsl[0], base_hsl[1], lightness)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                monochromatic_colors.append(new_color)

            return monochromatic_colors

    def custom_harmony(self, hue_offsets: list[float]) -> list[Color]:
        """
        Generate custom harmony with specified hue offsets.

        Args:
            hue_offsets: List of hue offsets in degrees from base color

        Returns:
            List of colors with specified hue relationships
        """
        try:
            # Convert base color to LCH for hue manipulation
            base_lch = colorspacious.cspace_convert(self.base_color.rgb(), "sRGB255", "CIELCh")

            custom_colors = []
            for offset in hue_offsets:
                new_lch = base_lch.copy()
                new_lch[2] = (base_lch[2] + offset) % 360

                # Convert back to RGB
                new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
                new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

                new_color = Color(new_rgb)
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                custom_colors.append(new_color)

            return custom_colors

        except Exception:
            # Fallback using HSL hue rotation
            base_hsl = self.base_color.hsl()
            custom_colors = []

            for offset in hue_offsets:
                new_hue = (base_hsl[0] + offset) % 360
                new_color = Color.from_hsl(new_hue, base_hsl[1], base_hsl[2])
                new_color._alpha = getattr(self.base_color, '_alpha', 1.0)
                custom_colors.append(new_color)

            return custom_colors