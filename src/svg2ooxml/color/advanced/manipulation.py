#!/usr/bin/env python3
"""
Advanced color manipulation and transformation utilities.

Provides sophisticated color operations including tinting, shading,
mixing, gradients, and professional color adjustment tools.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

import colorspacious
import numpy as np

from .batch import ColorBatch
from .core import Color


class BlendMode(Enum):
    """Color blending modes for advanced compositing."""
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    COLOR_DODGE = "color_dodge"
    COLOR_BURN = "color_burn"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"


class ColorManipulation:
    """
    Advanced color manipulation and transformation toolkit.

    Provides professional-grade color operations for design applications,
    including sophisticated blending modes, tinting, shading, and mixing.

    Examples:
        >>> manipulator = ColorManipulation()
        >>> tinted = manipulator.tint(Color('#ff0000'), 0.3)
        >>> mixed = manipulator.mix_colors([Color('#ff0000'), Color('#0000ff')], [0.7, 0.3])
        >>> blended = manipulator.blend(Color('#ff0000'), Color('#0000ff'), BlendMode.MULTIPLY)
    """

    def __init__(self):
        """Initialize ColorManipulation toolkit."""
        pass

    def tint(self, color: Color, amount: float = 0.1) -> Color:
        """
        Add white to lighten color (tinting).

        Args:
            color: Base color to tint
            amount: Amount of white to add (0.0-1.0)

        Returns:
            Tinted color
        """
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"Amount must be 0.0-1.0, got {amount}")

        white = Color('#ffffff')
        return self._blend_colors(color, white, amount, BlendMode.NORMAL)

    def shade(self, color: Color, amount: float = 0.1) -> Color:
        """
        Add black to darken color (shading).

        Args:
            color: Base color to shade
            amount: Amount of black to add (0.0-1.0)

        Returns:
            Shaded color
        """
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"Amount must be 0.0-1.0, got {amount}")

        black = Color('#000000')
        return self._blend_colors(color, black, amount, BlendMode.NORMAL)

    def tone(self, color: Color, amount: float = 0.1) -> Color:
        """
        Add gray to desaturate color (toning).

        Args:
            color: Base color to tone
            amount: Amount of gray to add (0.0-1.0)

        Returns:
            Toned color
        """
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"Amount must be 0.0-1.0, got {amount}")

        # Calculate gray with same luminance as original color
        try:
            # Use Lab lightness to create matching gray
            lab = colorspacious.cspace_convert(color.rgb(), "sRGB255", "CIELab")
            gray_lab = np.array([lab[0], 0, 0])  # Zero chroma = gray
            gray_rgb = colorspacious.cspace_convert(gray_lab, "CIELab", "sRGB255")
            gray_rgb = tuple(max(0, min(255, int(c))) for c in gray_rgb)
            gray = Color(gray_rgb)
        except Exception:
            # Fallback to simple gray
            luminance = sum(color.rgb()) // 3
            gray = Color((luminance, luminance, luminance))

        return self._blend_colors(color, gray, amount, BlendMode.NORMAL)

    def mix_colors(self, colors: list[Color], weights: list[float] | None = None) -> Color:
        """
        Mix multiple colors with optional weights.

        Args:
            colors: List of colors to mix
            weights: Optional weights for each color (defaults to equal)

        Returns:
            Mixed color
        """
        if not colors:
            raise ValueError("Cannot mix empty color list")

        if weights is None:
            weights = [1.0 / len(colors)] * len(colors)

        if len(weights) != len(colors):
            raise ValueError("Weights list must match colors list length")

        # Normalize weights
        total_weight = sum(weights)
        if total_weight <= 0:
            raise ValueError("Total weight must be positive")

        weights = [w / total_weight for w in weights]

        # Mix in RGB space for simplicity
        mixed_rgb = np.zeros(3)
        total_alpha = 0.0

        for color, weight in zip(colors, weights):
            rgb = np.array(color.rgb())
            mixed_rgb += rgb * weight
            total_alpha += getattr(color, '_alpha', 1.0) * weight

        mixed_rgb = np.clip(mixed_rgb, 0, 255).astype(int)
        mixed_color = Color(tuple(int(c) for c in mixed_rgb))
        mixed_color._alpha = total_alpha

        return mixed_color

    def blend(self, base: Color, overlay: Color, mode: BlendMode, opacity: float = 1.0) -> Color:
        """
        Blend two colors using specified blend mode.

        Args:
            base: Base color
            overlay: Overlay color
            mode: Blending mode
            opacity: Overlay opacity (0.0-1.0)

        Returns:
            Blended color
        """
        if not 0.0 <= opacity <= 1.0:
            raise ValueError(f"Opacity must be 0.0-1.0, got {opacity}")

        return self._blend_colors(base, overlay, opacity, mode)

    def _blend_colors(self, base: Color, overlay: Color, opacity: float, mode: BlendMode) -> Color:
        """Internal color blending implementation."""
        base_rgb = np.array(base.rgb(), dtype=np.float32) / 255.0
        overlay_rgb = np.array(overlay.rgb(), dtype=np.float32) / 255.0

        if mode == BlendMode.NORMAL:
            result = base_rgb * (1 - opacity) + overlay_rgb * opacity

        elif mode == BlendMode.MULTIPLY:
            result = base_rgb * overlay_rgb
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.SCREEN:
            result = 1 - (1 - base_rgb) * (1 - overlay_rgb)
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.OVERLAY:
            result = np.where(base_rgb < 0.5,
                            2 * base_rgb * overlay_rgb,
                            1 - 2 * (1 - base_rgb) * (1 - overlay_rgb))
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.SOFT_LIGHT:
            result = np.where(overlay_rgb < 0.5,
                            base_rgb - (1 - 2 * overlay_rgb) * base_rgb * (1 - base_rgb),
                            base_rgb + (2 * overlay_rgb - 1) * (np.sqrt(base_rgb) - base_rgb))
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.HARD_LIGHT:
            result = np.where(overlay_rgb < 0.5,
                            2 * base_rgb * overlay_rgb,
                            1 - 2 * (1 - base_rgb) * (1 - overlay_rgb))
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.COLOR_DODGE:
            result = np.where(overlay_rgb >= 1.0, 1.0, base_rgb / (1 - overlay_rgb))
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.COLOR_BURN:
            result = np.where(overlay_rgb <= 0.0, 0.0, 1 - (1 - base_rgb) / overlay_rgb)
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.DARKEN:
            result = np.minimum(base_rgb, overlay_rgb)
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.LIGHTEN:
            result = np.maximum(base_rgb, overlay_rgb)
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.DIFFERENCE:
            result = np.abs(base_rgb - overlay_rgb)
            result = base_rgb * (1 - opacity) + result * opacity

        elif mode == BlendMode.EXCLUSION:
            result = base_rgb + overlay_rgb - 2 * base_rgb * overlay_rgb
            result = base_rgb * (1 - opacity) + result * opacity

        else:
            result = base_rgb  # Fallback to base

        # Clamp and convert back to 0-255 range
        result = np.clip(result * 255, 0, 255).astype(int)

        blended_color = Color(tuple(int(c) for c in result))

        # Blend alpha channels
        base_alpha = getattr(base, '_alpha', 1.0)
        overlay_alpha = getattr(overlay, '_alpha', 1.0)
        blended_alpha = base_alpha * (1 - opacity) + overlay_alpha * opacity
        blended_color._alpha = blended_alpha

        return blended_color

    def adjust_vibrance(self, color: Color, amount: float = 0.1) -> Color:
        """
        Adjust color vibrance (smart saturation that protects skin tones).

        Args:
            color: Color to adjust
            amount: Vibrance adjustment (-1.0 to 1.0)

        Returns:
            Color with adjusted vibrance
        """
        if not -1.0 <= amount <= 1.0:
            raise ValueError(f"Amount must be -1.0 to 1.0, got {amount}")

        try:
            # Convert to LCH for chroma adjustment
            lch = colorspacious.cspace_convert(color.rgb(), "sRGB255", "CIELCh")

            # Calculate skin tone protection
            # Skin tones typically have hue around 25-45 degrees
            hue = lch[2]
            skin_tone_factor = 1.0
            if 15 <= hue <= 55:  # Skin tone range
                # Reduce vibrance adjustment for skin tones
                skin_tone_factor = 0.3

            # Apply vibrance adjustment with skin tone protection
            chroma_adjustment = amount * 30 * skin_tone_factor
            new_lch = lch.copy()
            new_lch[1] = max(0, lch[1] + chroma_adjustment)

            # Convert back to RGB
            new_rgb = colorspacious.cspace_convert(new_lch, "CIELCh", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            new_color = Color(new_rgb)
            new_color._alpha = getattr(color, '_alpha', 1.0)
            return new_color

        except Exception:
            # Fallback to simple saturation adjustment
            return color.saturate(amount * 0.5)

    def create_gradient(self, start: Color, end: Color, steps: int,
                       easing: str = 'linear') -> list[Color]:
        """
        Create smooth gradient between colors with easing functions.

        Args:
            start: Starting color
            end: Ending color
            steps: Number of gradient steps
            easing: Easing function ('linear', 'ease_in', 'ease_out', 'ease_in_out')

        Returns:
            List of gradient colors
        """
        if steps < 2:
            raise ValueError("Steps must be at least 2")

        # Create parameter array based on easing
        if easing == 'linear':
            t_values = np.linspace(0, 1, steps)
        elif easing == 'ease_in':
            t_values = np.linspace(0, 1, steps) ** 2
        elif easing == 'ease_out':
            t_values = 1 - (1 - np.linspace(0, 1, steps)) ** 2
        elif easing == 'ease_in_out':
            t_raw = np.linspace(0, 1, steps)
            t_values = np.where(t_raw < 0.5,
                              2 * t_raw ** 2,
                              1 - 2 * (1 - t_raw) ** 2)
        else:
            raise ValueError(f"Unknown easing function: {easing}")

        # Interpolate in Lab color space for perceptual uniformity
        try:
            start_lab = colorspacious.cspace_convert(start.rgb(), "sRGB255", "CIELab")
            end_lab = colorspacious.cspace_convert(end.rgb(), "sRGB255", "CIELab")

            gradient_colors = []
            start_alpha = getattr(start, '_alpha', 1.0)
            end_alpha = getattr(end, '_alpha', 1.0)

            for t in t_values:
                # Interpolate Lab values
                interp_lab = (1 - t) * start_lab + t * end_lab

                # Convert back to RGB
                interp_rgb = colorspacious.cspace_convert(interp_lab, "CIELab", "sRGB255")
                interp_rgb = tuple(max(0, min(255, int(c))) for c in interp_rgb)

                # Interpolate alpha
                interp_alpha = (1 - t) * start_alpha + t * end_alpha

                color = Color(interp_rgb)
                color._alpha = interp_alpha
                gradient_colors.append(color)

            return gradient_colors

        except Exception:
            # Fallback to RGB interpolation
            return ColorBatch.gradient(start, end, steps).to_colors()

    def create_palette_from_image_colors(self, dominant_colors: list[Color],
                                       target_size: int = 5) -> list[Color]:
        """
        Create harmonious palette from dominant image colors.

        Args:
            dominant_colors: List of dominant colors from image
            target_size: Desired palette size

        Returns:
            Harmonious color palette
        """
        if not dominant_colors:
            raise ValueError("Cannot create palette from empty color list")

        if len(dominant_colors) <= target_size:
            return dominant_colors[:target_size]

        # Use k-means-like clustering to reduce colors
        return self._cluster_colors(dominant_colors, target_size)

    def _cluster_colors(self, colors: list[Color], k: int) -> list[Color]:
        """Cluster colors using Lab color space for perceptual accuracy."""
        try:
            # Convert colors to Lab space
            lab_colors = []
            for color in colors:
                lab = colorspacious.cspace_convert(color.rgb(), "sRGB255", "CIELab")
                lab_colors.append(lab)

            lab_array = np.array(lab_colors)

            # Simple k-means clustering
            # Initialize centroids randomly
            np.random.seed(42)  # For reproducible results
            centroids = lab_array[np.random.choice(len(lab_array), k, replace=False)]

            for _ in range(10):  # Max iterations
                # Assign points to closest centroids
                distances = np.sqrt(((lab_array[:, np.newaxis] - centroids) ** 2).sum(axis=2))
                assignments = np.argmin(distances, axis=1)

                # Update centroids
                new_centroids = np.array([lab_array[assignments == i].mean(axis=0)
                                        for i in range(k)])

                # Check convergence
                if np.allclose(centroids, new_centroids):
                    break

                centroids = new_centroids

            # Convert centroids back to colors
            clustered_colors = []
            for centroid in centroids:
                rgb = colorspacious.cspace_convert(centroid, "CIELab", "sRGB255")
                rgb = tuple(max(0, min(255, int(c))) for c in rgb)
                clustered_colors.append(Color(rgb))

            return clustered_colors

        except Exception:
            # Fallback: just take first k colors
            return colors[:k]

    def adjust_color_balance(self, color: Color, shadows: float = 0.0,
                           midtones: float = 0.0, highlights: float = 0.0) -> Color:
        """
        Adjust color balance in shadows, midtones, and highlights.

        Args:
            color: Color to adjust
            shadows: Shadow adjustment (-1.0 to 1.0)
            midtones: Midtone adjustment (-1.0 to 1.0)
            highlights: Highlight adjustment (-1.0 to 1.0)

        Returns:
            Color with adjusted balance
        """
        # Get luminance to determine shadow/midtone/highlight regions
        try:
            lab = colorspacious.cspace_convert(color.rgb(), "sRGB255", "CIELab")
            lightness = lab[0] / 100.0  # Normalize to 0-1

            # Calculate weights for each region
            shadow_weight = max(0, 1 - lightness * 2)  # High for dark areas
            highlight_weight = max(0, lightness * 2 - 1)  # High for bright areas
            midtone_weight = 1 - shadow_weight - highlight_weight

            # Apply adjustments
            total_adjustment = (shadows * shadow_weight +
                              midtones * midtone_weight +
                              highlights * highlight_weight) * 0.3

            # Adjust lightness
            new_lab = lab.copy()
            new_lab[0] = np.clip(lab[0] + total_adjustment * 50, 0, 100)

            # Convert back to RGB
            new_rgb = colorspacious.cspace_convert(new_lab, "CIELab", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            new_color = Color(new_rgb)
            new_color._alpha = getattr(color, '_alpha', 1.0)
            return new_color

        except Exception:
            # Fallback: simple brightness adjustment
            avg_adjustment = (shadows + midtones + highlights) / 3
            if avg_adjustment > 0:
                return color.lighten(abs(avg_adjustment) * 0.2)
            else:
                return color.darken(abs(avg_adjustment) * 0.2)