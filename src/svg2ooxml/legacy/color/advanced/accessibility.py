#!/usr/bin/env python3
"""
Color accessibility utilities for WCAG compliance and inclusive design.

Provides tools for contrast ratio calculations, color blindness simulation,
and automatic accessible color generation following WCAG 2.1 guidelines.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

import colorspacious
import numpy as np

from .core import Color


class ContrastLevel(Enum):
    """WCAG contrast ratio levels."""
    AA_NORMAL = 4.5      # WCAG AA for normal text
    AA_LARGE = 3.0       # WCAG AA for large text (18pt+ or 14pt+ bold)
    AAA_NORMAL = 7.0     # WCAG AAA for normal text
    AAA_LARGE = 4.5      # WCAG AAA for large text


class ColorBlindnessType(Enum):
    """Types of color blindness for simulation."""
    PROTANOPIA = "protanopia"        # Red-blind (1% of males)
    DEUTERANOPIA = "deuteranopia"    # Green-blind (1% of males)
    TRITANOPIA = "tritanopia"        # Blue-blind (0.01% of population)
    PROTANOMALY = "protanomaly"      # Reduced red sensitivity (1% of males)
    DEUTERANOMALY = "deuteranomaly"  # Reduced green sensitivity (5% of males)
    TRITANOMALY = "tritanomaly"      # Reduced blue sensitivity (rare)


class ColorAccessibility:
    """
    Comprehensive color accessibility toolkit.

    Provides WCAG compliance checking, contrast ratio calculations,
    color blindness simulation, and accessible color generation.

    Examples:
        >>> accessibility = ColorAccessibility()
        >>> ratio = accessibility.contrast_ratio(Color('#000000'), Color('#ffffff'))
        >>> accessible_color = accessibility.find_accessible_color(Color('#ff0000'), Color('#ffffff'))
        >>> simulated = accessibility.simulate_color_blindness(Color('#ff0000'), ColorBlindnessType.DEUTERANOPIA)
    """

    def __init__(self):
        """Initialize ColorAccessibility with WCAG standards."""
        # Color blindness transformation matrices (LMS color space)
        self._colorblind_matrices = {
            ColorBlindnessType.PROTANOPIA: np.array([
                [0.567, 0.433, 0.000],
                [0.558, 0.442, 0.000],
                [0.000, 0.242, 0.758],
            ]),
            ColorBlindnessType.DEUTERANOPIA: np.array([
                [0.625, 0.375, 0.000],
                [0.700, 0.300, 0.000],
                [0.000, 0.300, 0.700],
            ]),
            ColorBlindnessType.TRITANOPIA: np.array([
                [0.950, 0.050, 0.000],
                [0.000, 0.433, 0.567],
                [0.000, 0.475, 0.525],
            ]),
            ColorBlindnessType.PROTANOMALY: np.array([
                [0.817, 0.183, 0.000],
                [0.333, 0.667, 0.000],
                [0.000, 0.125, 0.875],
            ]),
            ColorBlindnessType.DEUTERANOMALY: np.array([
                [0.800, 0.200, 0.000],
                [0.258, 0.742, 0.000],
                [0.000, 0.142, 0.858],
            ]),
            ColorBlindnessType.TRITANOMALY: np.array([
                [0.967, 0.033, 0.000],
                [0.000, 0.733, 0.267],
                [0.000, 0.183, 0.817],
            ]),
        }

    def contrast_ratio(self, foreground: Color, background: Color) -> float:
        """
        Calculate WCAG contrast ratio between two colors.

        Args:
            foreground: Foreground color
            background: Background color

        Returns:
            Contrast ratio (1:1 to 21:1)
        """
        # Get relative luminance values
        fg_luminance = self._relative_luminance(foreground)
        bg_luminance = self._relative_luminance(background)

        # WCAG formula: (lighter + 0.05) / (darker + 0.05)
        lighter = max(fg_luminance, bg_luminance)
        darker = min(fg_luminance, bg_luminance)

        return (lighter + 0.05) / (darker + 0.05)

    def _relative_luminance(self, color: Color) -> float:
        """
        Calculate relative luminance according to WCAG definition.

        Args:
            color: Color to calculate luminance for

        Returns:
            Relative luminance (0.0-1.0)
        """
        rgb = color.rgb()

        # Convert to 0-1 range and apply gamma correction
        def linearize(c):
            c = c / 255.0
            if c <= 0.03928:
                return c / 12.92
            else:
                return ((c + 0.055) / 1.055) ** 2.4

        r_lin = linearize(rgb[0])
        g_lin = linearize(rgb[1])
        b_lin = linearize(rgb[2])

        # WCAG luminance formula
        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    def meets_contrast_requirement(self, foreground: Color, background: Color,
                                 level: ContrastLevel) -> bool:
        """
        Check if color combination meets WCAG contrast requirement.

        Args:
            foreground: Foreground color
            background: Background color
            level: Required contrast level

        Returns:
            True if meets requirement
        """
        ratio = self.contrast_ratio(foreground, background)
        return ratio >= level.value

    def find_accessible_color(self, target_color: Color, background: Color,
                             level: ContrastLevel = ContrastLevel.AA_NORMAL,
                             preserve_hue: bool = True) -> Color:
        """
        Find accessible color meeting contrast requirements.

        Args:
            target_color: Desired color to make accessible
            background: Background color to contrast against
            level: Required contrast level
            preserve_hue: Whether to preserve original hue

        Returns:
            Accessible color meeting contrast requirements
        """
        # If already accessible, return original
        if self.meets_contrast_requirement(target_color, background, level):
            return target_color

        if preserve_hue:
            return self._find_accessible_preserving_hue(target_color, background, level)
        else:
            return self._find_accessible_any_hue(target_color, background, level)

    def _find_accessible_preserving_hue(self, target_color: Color, background: Color,
                                       level: ContrastLevel) -> Color:
        """Find accessible color preserving hue by adjusting lightness."""
        try:
            # Convert to LCH for hue preservation
            target_lch = colorspacious.cspace_convert(target_color.rgb(), "sRGB255", "CIELCh")
            bg_lch = colorspacious.cspace_convert(background.rgb(), "sRGB255", "CIELCh")

            # Binary search for accessible lightness
            min_l, max_l = 0, 100
            best_color = target_color

            for _ in range(20):  # Limit iterations
                test_l = (min_l + max_l) / 2
                test_lch = target_lch.copy()
                test_lch[0] = test_l

                # Convert back to RGB
                test_rgb = colorspacious.cspace_convert(test_lch, "CIELCh", "sRGB255")
                test_rgb = tuple(max(0, min(255, int(c))) for c in test_rgb)

                test_color = Color(test_rgb)
                test_color._alpha = getattr(target_color, '_alpha', 1.0)

                if self.meets_contrast_requirement(test_color, background, level):
                    best_color = test_color
                    if bg_lch[0] > 50:  # Light background, try darker
                        max_l = test_l
                    else:  # Dark background, try lighter
                        min_l = test_l
                else:
                    if bg_lch[0] > 50:  # Light background, go darker
                        max_l = test_l
                    else:  # Dark background, go lighter
                        min_l = test_l

            return best_color

        except Exception:
            return self._find_accessible_any_hue(target_color, background, level)

    def _find_accessible_any_hue(self, target_color: Color, background: Color,
                                level: ContrastLevel) -> Color:
        """Find accessible color without hue constraint."""
        bg_luminance = self._relative_luminance(background)

        # Choose high contrast color
        if bg_luminance > 0.5:  # Light background
            accessible_color = Color('#000000')  # Black
        else:  # Dark background
            accessible_color = Color('#ffffff')  # White

        accessible_color._alpha = getattr(target_color, '_alpha', 1.0)
        return accessible_color

    def simulate_color_blindness(self, color: Color,
                                blindness_type: ColorBlindnessType) -> Color:
        """
        Simulate how a color appears to someone with color blindness.

        Args:
            color: Original color
            blindness_type: Type of color blindness to simulate

        Returns:
            Color as perceived by someone with the specified color blindness
        """
        # Simple RGB-based color blindness simulation using established matrices
        rgb = np.array(color.rgb(), dtype=np.float32)

        # Normalized RGB (0-1)
        rgb_norm = rgb / 255.0

        # Apply color blindness transformation matrix directly to RGB
        matrix = self._colorblind_matrices[blindness_type]
        rgb_blind = matrix @ rgb_norm

        # Clamp and convert back to 0-255 range
        rgb_blind = np.clip(rgb_blind * 255, 0, 255).astype(int)

        simulated_color = Color(tuple(int(c) for c in rgb_blind))
        simulated_color._alpha = getattr(color, '_alpha', 1.0)
        return simulated_color

    def get_accessible_palette(self, base_colors: list[Color],
                              background: Color,
                              level: ContrastLevel = ContrastLevel.AA_NORMAL) -> list[Color]:
        """
        Generate accessible palette from base colors.

        Args:
            base_colors: Original color palette
            background: Background color to contrast against
            level: Required contrast level

        Returns:
            List of accessible colors
        """
        accessible_colors = []

        for color in base_colors:
            accessible = self.find_accessible_color(color, background, level)
            accessible_colors.append(accessible)

        return accessible_colors

    def analyze_palette_accessibility(self, colors: list[Color],
                                    background: Color) -> dict[str, any]:
        """
        Analyze accessibility of a color palette.

        Args:
            colors: Color palette to analyze
            background: Background color

        Returns:
            Dictionary with accessibility analysis
        """
        analysis = {
            'total_colors': len(colors),
            'aa_normal_compliant': 0,
            'aa_large_compliant': 0,
            'aaa_normal_compliant': 0,
            'aaa_large_compliant': 0,
            'contrast_ratios': [],
            'non_compliant_colors': [],
            'recommendations': [],
        }

        for i, color in enumerate(colors):
            ratio = self.contrast_ratio(color, background)
            analysis['contrast_ratios'].append(ratio)

            # Check compliance levels
            if ratio >= ContrastLevel.AA_NORMAL.value:
                analysis['aa_normal_compliant'] += 1
            if ratio >= ContrastLevel.AA_LARGE.value:
                analysis['aa_large_compliant'] += 1
            if ratio >= ContrastLevel.AAA_NORMAL.value:
                analysis['aaa_normal_compliant'] += 1
            if ratio >= ContrastLevel.AAA_LARGE.value:
                analysis['aaa_large_compliant'] += 1

            # Track non-compliant colors
            if ratio < ContrastLevel.AA_LARGE.value:
                analysis['non_compliant_colors'].append({
                    'index': i,
                    'color': color.hex(),
                    'contrast_ratio': ratio,
                })

        # Generate recommendations
        if analysis['aa_normal_compliant'] < len(colors):
            analysis['recommendations'].append(
                f"{len(colors) - analysis['aa_normal_compliant']} colors need adjustment for AA normal text compliance",
            )

        if analysis['aaa_normal_compliant'] < len(colors):
            analysis['recommendations'].append(
                f"Consider adjusting {len(colors) - analysis['aaa_normal_compliant']} colors for AAA compliance",
            )

        return analysis

    def simulate_palette_for_color_blindness(self, colors: list[Color],
                                           blindness_types: list[ColorBlindnessType] | None = None) -> dict[ColorBlindnessType, list[Color]]:
        """
        Simulate entire palette for different types of color blindness.

        Args:
            colors: Original color palette
            blindness_types: Types to simulate (defaults to most common types)

        Returns:
            Dictionary mapping blindness types to simulated palettes
        """
        if blindness_types is None:
            # Most common types affecting ~8% of males, ~0.5% of females
            blindness_types = [
                ColorBlindnessType.PROTANOPIA,
                ColorBlindnessType.DEUTERANOPIA,
                ColorBlindnessType.DEUTERANOMALY,
            ]

        simulated_palettes = {}

        for blindness_type in blindness_types:
            simulated_palette = []
            for color in colors:
                simulated = self.simulate_color_blindness(color, blindness_type)
                simulated_palette.append(simulated)
            simulated_palettes[blindness_type] = simulated_palette

        return simulated_palettes

    def recommend_text_color(self, background: Color,
                           level: ContrastLevel = ContrastLevel.AA_NORMAL) -> Color:
        """
        Recommend optimal text color for given background.

        Args:
            background: Background color
            level: Required contrast level

        Returns:
            Recommended text color (black or white)
        """
        black = Color('#000000')
        white = Color('#ffffff')

        black_ratio = self.contrast_ratio(black, background)
        white_ratio = self.contrast_ratio(white, background)

        # Choose color that meets requirement and has higher ratio
        if black_ratio >= level.value and white_ratio >= level.value:
            return black if black_ratio > white_ratio else white
        elif black_ratio >= level.value:
            return black
        elif white_ratio >= level.value:
            return white
        else:
            # Neither meets requirement, choose higher ratio
            return black if black_ratio > white_ratio else white