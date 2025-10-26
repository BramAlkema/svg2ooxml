#!/usr/bin/env python3
"""
Core Color class with fluent API and NumPy/colorspacious backend.

This module provides the primary Color class that supports method chaining
and leverages colorspacious for accurate color science operations.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Tuple, Union

import colorspacious
import numpy as np

from .color_spaces import ColorSpaceConverter

# Global cache for color conversions to improve performance
_conversion_cache = {}
_cache_lock = threading.Lock()


def _cached_color_convert(color_value, from_space, to_space):
    """
    Cached color space conversion for performance optimization.

    Args:
        color_value: Color value to convert
        from_space: Source color space
        to_space: Target color space

    Returns:
        Converted color value
    """
    # Create cache key from inputs
    if isinstance(color_value, np.ndarray):
        cache_key = (tuple(color_value), from_space, to_space)
    else:
        cache_key = (color_value, from_space, to_space)

    # Check cache first
    with _cache_lock:
        if cache_key in _conversion_cache:
            return _conversion_cache[cache_key]

    # Perform conversion
    result = colorspacious.cspace_convert(color_value, from_space, to_space)

    # Cache result (limit cache size to prevent memory bloat)
    with _cache_lock:
        if len(_conversion_cache) > 1000:  # Clear cache when it gets too large
            _conversion_cache.clear()
        _conversion_cache[cache_key] = result

    return result


class Color:
    """
    Immutable Color class with fluent API and professional color science backend.

    Uses colorspacious and NumPy for accurate, performant color operations while
    providing an intuitive chainable interface for color manipulation.

    Examples:
        >>> color = Color('#ff0000')
        >>> result = color.darken(0.2).saturate(1.5).hex()
        >>> palette = Color('#3498db').analogous(5)
    """

    def __init__(self, value: str | tuple[int, int, int] | tuple[int, int, int, float] | dict[str, Any] | np.ndarray):
        """
        Initialize Color from various input formats.

        Args:
            value: Color specification in various formats:
                - str: Hex color ('#ff0000', 'red', etc.)
                - tuple: RGB(A) tuple ((255, 0, 0) or (255, 0, 0, 1.0))
                - dict: HSL/other format ({'h': 0, 's': 100, 'l': 50})
                - np.ndarray: NumPy array with RGB values

        Raises:
            ValueError: If color value cannot be parsed
            TypeError: If input type is not supported
        """
        # Implementation will be added in next subtask
        # For now, store the input for development
        self._input_value = value
        self._rgb = None
        self._alpha = 1.0

        # Parse the input value
        self._parse_input(value)

    def _parse_input(self, value: Any) -> None:
        """Parse input value and set internal RGB representation."""
        if isinstance(value, str):
            self._parse_string_value(value)
        elif isinstance(value, tuple):
            self._parse_tuple_value(value)
        elif isinstance(value, dict):
            self._parse_dict_value(value)
        elif isinstance(value, np.ndarray):
            self._parse_numpy_value(value)
        else:
            raise TypeError(f"Unsupported color input type: {type(value)}")

    def _parse_string_value(self, value: str) -> None:
        """Parse string color values."""
        value = value.strip().lower()

        if value.startswith('#'):
            # Hex color parsing
            hex_val = value[1:]
            if len(hex_val) == 3:
                # Short hex format #rgb -> #rrggbb
                hex_val = ''.join(c*2 for c in hex_val)
            elif len(hex_val) == 6:
                pass  # Standard hex format
            elif len(hex_val) == 8:
                # Hex with alpha #rrggbbaa
                self._alpha = round(int(hex_val[6:8], 16) / 255.0, 10)  # Round to avoid floating point issues
                hex_val = hex_val[:6]
            else:
                raise ValueError(f"Invalid hex color format: {value}")

            try:
                self._rgb = tuple(int(hex_val[i:i+2], 16) for i in (0, 2, 4))
            except ValueError:
                raise ValueError(f"Invalid hex color format: {value}")

        elif value.startswith('rgb'):
            # RGB/RGBA functional notation
            import re
            if value.startswith('rgba'):
                pattern = r'rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)'
                match = re.match(pattern, value)
                if match:
                    r, g, b, a = match.groups()
                    r, g, b = int(r), int(g), int(b)
                    # Validate RGB ranges
                    if not all(0 <= c <= 255 for c in [r, g, b]):
                        raise ValueError(f"Invalid rgb format: {value}")
                    self._rgb = (r, g, b)
                    self._alpha = float(a)
                else:
                    raise ValueError(f"Invalid rgba format: {value}")
            else:
                pattern = r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)'
                match = re.match(pattern, value)
                if match:
                    r, g, b = match.groups()
                    r, g, b = int(r), int(g), int(b)
                    # Validate RGB ranges
                    if not all(0 <= c <= 255 for c in [r, g, b]):
                        raise ValueError(f"Invalid rgb format: {value}")
                    self._rgb = (r, g, b)
                else:
                    raise ValueError(f"Invalid rgb format: {value}")

        elif value.startswith('hsl'):
            # HSL/HSLA functional notation - convert to RGB
            import re
            if value.startswith('hsla'):
                pattern = r'hsla\s*\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*,\s*([\d.]+)\s*\)'
                match = re.match(pattern, value)
                if match:
                    h, s, l, a = match.groups()
                    h, s, l = float(h), float(s), float(l)
                    # Validate HSL ranges
                    if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= l <= 100):
                        raise ValueError(f"Invalid hsl format: {value}")
                    self._rgb = self._hsl_to_rgb(h, s/100, l/100)
                    self._alpha = float(a)
                else:
                    raise ValueError(f"Invalid hsla format: {value}")
            else:
                pattern = r'hsl\s*\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)'
                match = re.match(pattern, value)
                if match:
                    h, s, l = match.groups()
                    h, s, l = float(h), float(s), float(l)
                    # Validate HSL ranges
                    if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= l <= 100):
                        raise ValueError(f"Invalid hsl format: {value}")
                    self._rgb = self._hsl_to_rgb(h, s/100, l/100)
                else:
                    raise ValueError(f"Invalid hsl format: {value}")

        elif value in ['transparent', 'none']:
            self._rgb = (0, 0, 0)
            self._alpha = 0.0

        else:
            # CSS named colors using comprehensive lookup table
            from .css_colors import get_css_color

            css_color = get_css_color(value)
            if css_color:
                self._rgb = css_color
                # Handle transparent specially
                if value.lower() == 'transparent':
                    self._alpha = 0.0
            else:
                raise ValueError(f"Unknown color name: {value}")

    def _parse_tuple_value(self, value: tuple) -> None:
        """Parse tuple color values."""
        if len(value) < 3:
            raise ValueError(f"Color tuple must have at least 3 values, got {len(value)}")

        # Validate RGB values
        for i, component in enumerate(value[:3]):
            if not isinstance(component, (int, float)) or not 0 <= component <= 255:
                raise ValueError(f"RGB component {i} must be 0-255, got {component}")

        self._rgb = tuple(int(c) for c in value[:3])

        if len(value) > 3:
            alpha = value[3]
            if not isinstance(alpha, (int, float)) or not 0.0 <= alpha <= 1.0:
                raise ValueError(f"Alpha must be 0.0-1.0, got {alpha}")
            self._alpha = float(alpha)

    def _parse_dict_value(self, value: dict) -> None:
        """Parse dictionary color values (HSL, etc.)."""
        if 'h' in value and 's' in value and 'l' in value:
            # HSL format
            h = value.get('h', 0)
            s = value.get('s', 0) / 100.0 if value.get('s', 0) > 1 else value.get('s', 0)
            l = value.get('l', 0) / 100.0 if value.get('l', 0) > 1 else value.get('l', 0)
            self._rgb = self._hsl_to_rgb(h, s, l)
            self._alpha = value.get('a', 1.0)
        elif 'r' in value and 'g' in value and 'b' in value:
            # RGB format
            self._rgb = (int(value['r']), int(value['g']), int(value['b']))
            self._alpha = value.get('a', 1.0)
        else:
            raise ValueError(f"Unsupported dictionary color format: {value}")

    def _parse_numpy_value(self, value: np.ndarray) -> None:
        """Parse NumPy array color values."""
        if value.shape[-1] < 3:
            raise ValueError(f"NumPy array must have at least 3 components, got {value.shape}")

        rgb_values = value.flatten()[:3].astype(int)
        self._rgb = tuple(rgb_values)

        if value.shape[-1] > 3:
            self._alpha = float(value.flatten()[3])

    def _hsl_to_rgb(self, h: float, s: float, l: float) -> tuple:
        """Convert HSL to RGB."""
        h = h % 360 / 360.0  # Normalize hue to 0-1

        if s == 0:
            # Achromatic (gray)
            r = g = b = l
        else:
            def hue_to_rgb(p, q, t):
                if t < 0: t += 1
                if t > 1: t -= 1
                if t < 1/6: return p + (q - p) * 6 * t
                if t < 1/2: return q
                if t < 2/3: return p + (q - p) * (2/3 - t) * 6
                return p

            q = l * (1 + s) if l < 0.5 else l + s - l * s
            p = 2 * l - q

            r = hue_to_rgb(p, q, h + 1/3)
            g = hue_to_rgb(p, q, h)
            b = hue_to_rgb(p, q, h - 1/3)

        return (int(r * 255), int(g * 255), int(b * 255))

    # Fluent API Methods
    def darken(self, amount: float = 0.1) -> Color:
        """
        Darken the color by reducing lightness in Lab space.

        Args:
            amount: Amount to darken (0.0-1.0, values > 1.0 are clamped)

        Returns:
            New Color instance with reduced lightness
        """
        # Clamp amount to valid range instead of raising error
        amount = max(0.0, min(1.0, amount))

        try:
            # Convert to Lab for perceptually uniform lightness adjustment
            lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")

            # Reduce lightness
            lab[0] = max(0, lab[0] - (amount * 50))  # L* ranges roughly 0-100

            # Convert back to RGB
            new_rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            # Create new Color instance
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

        except Exception:
            # Fallback to simpler RGB darkening
            factor = 1.0 - amount
            new_rgb = tuple(max(0, min(255, int(c * factor))) for c in self._rgb)
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

    def lighten(self, amount: float = 0.1) -> Color:
        """
        Lighten the color by increasing lightness in Lab space.

        Args:
            amount: Amount to lighten (0.0-1.0, values > 1.0 are clamped)

        Returns:
            New Color instance with increased lightness
        """
        # Clamp amount to valid range instead of raising error
        amount = max(0.0, min(1.0, amount))

        try:
            # Convert to Lab for perceptually uniform lightness adjustment
            lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")

            # Increase lightness
            lab[0] = min(100, lab[0] + (amount * 50))  # L* ranges roughly 0-100

            # Convert back to RGB
            new_rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            # Create new Color instance
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

        except Exception:
            # Fallback to simpler RGB lightening
            factor = 1.0 + amount
            new_rgb = tuple(max(0, min(255, int(c * factor))) for c in self._rgb)
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

    def saturate(self, amount: float = 0.1) -> Color:
        """
        Increase color saturation in LCH space.

        Args:
            amount: Amount to increase saturation

        Returns:
            New Color instance with increased saturation
        """
        try:
            # Convert to LCH for chroma adjustment using cached conversion
            lch = _cached_color_convert(self._rgb, "sRGB255", "CIELCh")

            # Adjust chroma (saturation)
            lch[1] = max(0, lch[1] + (amount * 50))  # Chroma adjustment

            # Convert back to RGB using cached conversion
            new_rgb = _cached_color_convert(lch, "CIELCh", "sRGB255")
            new_rgb = tuple(max(0, min(255, int(c))) for c in new_rgb)

            # Create new Color instance
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

        except Exception:
            # Fallback to HSL saturation adjustment
            hsl = self._rgb_to_hsl(*self._rgb)
            new_s = max(0, min(1, hsl[1] + amount))
            new_rgb = self._hsl_to_rgb(hsl[0], new_s, hsl[2])
            new_color = Color(new_rgb)
            new_color._alpha = self._alpha
            return new_color

    def desaturate(self, amount: float = 0.1) -> Color:
        """
        Decrease color saturation in LCH space.

        Args:
            amount: Amount to decrease saturation

        Returns:
            New Color instance with decreased saturation
        """
        return self.saturate(-amount)

    def adjust_hue(self, degrees: float) -> Color:
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

        new_color = Color(new_rgb)
        new_color._alpha = self._alpha
        return new_color

    def _rgb_to_hsl(self, r: int, g: int, b: int) -> tuple:
        """Convert RGB to HSL."""
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val

        # Lightness
        l = (max_val + min_val) / 2.0

        if diff == 0:
            # Achromatic
            h = s = 0
        else:
            # Saturation
            s = diff / (2.0 - max_val - min_val) if l > 0.5 else diff / (max_val + min_val)

            # Hue
            if max_val == r:
                h = ((g - b) / diff + (6 if g < b else 0)) / 6.0
            elif max_val == g:
                h = ((b - r) / diff + 2) / 6.0
            else:
                h = ((r - g) / diff + 4) / 6.0

        return (h * 360, s, l)


    def temperature(self, kelvin: int) -> Color:
        """
        Adjust color temperature using blackbody radiation approximation.

        Args:
            kelvin: Target color temperature (1000-40000K)

        Returns:
            New Color instance with adjusted temperature
        """
        if not 1000 <= kelvin <= 40000:
            raise ValueError(f"Color temperature must be 1000-40000K, got {kelvin}")

        # Calculate blackbody RGB values using Tanner Helland's algorithm
        temp = kelvin / 100.0

        # Calculate red
        if temp <= 66:
            red = 255
        else:
            red = temp - 60
            red = 329.698727446 * (red ** -0.1332047592)
            red = max(0, min(255, red))

        # Calculate green
        if temp <= 66:
            green = temp
            green = 99.4708025861 * np.log(green) - 161.1195681661
            green = max(0, min(255, green))
        else:
            green = temp - 60
            green = 288.1221695283 * (green ** -0.0755148492)
            green = max(0, min(255, green))

        # Calculate blue
        if temp >= 66:
            blue = 255
        else:
            if temp <= 19:
                blue = 0
            else:
                blue = temp - 10
                blue = 138.5177312231 * np.log(blue) - 305.0447927307
                blue = max(0, min(255, blue))

        # Create temperature color
        temp_color = Color((int(red), int(green), int(blue)))

        # Blend with original color
        original_rgb = np.array(self.rgb(), dtype=np.float32)
        temp_rgb = np.array(temp_color.rgb(), dtype=np.float32)

        # Use a blending that preserves the original color character
        blend_factor = 0.3  # Adjust temperature influence
        blended_rgb = ((1 - blend_factor) * original_rgb +
                      blend_factor * temp_rgb)
        blended_rgb = np.clip(blended_rgb, 0, 255).astype(int)

        new_color = Color(tuple(int(c) for c in blended_rgb))
        new_color._alpha = self._alpha
        return new_color

    def alpha(self, value: float) -> Color:
        """
        Set alpha channel value.

        Args:
            value: Alpha value (0.0-1.0)

        Returns:
            New Color instance with specified alpha
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {value}")

        new_color = Color(self._input_value)
        new_color._rgb = self._rgb
        new_color._alpha = value
        return new_color

    # Output Format Methods
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

        OKLab is designed for better color manipulation and mixing than
        traditional color spaces like sRGB or CIE Lab. It provides more
        accurate lightness perception and smoother color transitions.

        Returns:
            OKLab values as (L, a, b) tuple where:
            - L: Lightness (0.0-1.0)
            - a: Green-red component
            - b: Blue-yellow component
        """
        return ColorSpaceConverter.rgb_to_oklab(*self._rgb)

    def oklch(self) -> tuple[float, float, float]:
        """
        Get OKLCh representation - cylindrical form of OKLab.

        OKLCh provides intuitive control over lightness, chroma, and hue
        while maintaining the perceptual advantages of OKLab.

        Returns:
            OKLCh values as (L, C, h) tuple where:
            - L: Lightness (0.0-1.0)
            - C: Chroma (saturation)
            - h: Hue angle in degrees (0-360)
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
            return '<a:noFill/>'

        color_hex = self.hex()

        if self._alpha >= 1.0:
            return f'<a:srgbClr val="{color_hex}"/>'
        else:
            alpha_val = int(self._alpha * 100000)
            return f'<a:srgbClr val="{color_hex}"><a:alpha val="{alpha_val}"/></a:srgbClr>'

    # Color Science Methods
    def delta_e(self, other: Color, method: str = 'cie2000') -> float:
        """
        Calculate color difference using Delta E algorithms.

        Args:
            other: Color to compare with
            method: Delta E method ('cie76', 'cie94', 'cie2000')

        Returns:
            Delta E value (lower = more similar)
        """
        if not isinstance(other, Color):
            raise TypeError("other must be a Color instance")

        try:
            # Use colorspacious for accurate Delta E calculations
            color1_lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")
            color2_lab = colorspacious.cspace_convert(other._rgb, "sRGB255", "CIELab")

            if method.lower() == 'cie76':
                # Simple Euclidean distance in Lab space
                return float(np.sqrt(sum((a - b) ** 2 for a, b in zip(color1_lab, color2_lab))))

            elif method.lower() == 'cie2000':
                # Use colorspacious's Delta E 2000 implementation
                return colorspacious.delta_E(color1_lab, color2_lab, input_space="CIELab", uniform_space="CAM02-UCS")

            else:
                raise ValueError(f"Unsupported Delta E method: {method}")

        except Exception:
            # Fallback to simple RGB distance
            rgb_diff = sum((a - b) ** 2 for a, b in zip(self._rgb, other._rgb))
            return float(np.sqrt(rgb_diff) / np.sqrt(3 * 255 * 255) * 100)  # Normalize to ~0-100 scale

    # Utility Methods
    def __eq__(self, other: object) -> bool:
        """Check color equality."""
        if not isinstance(other, Color):
            return False
        return self._rgb == other._rgb and abs(self._alpha - other._alpha) < 1e-6

    def __hash__(self) -> int:
        """Make Color hashable for use in sets and dicts."""
        return hash((self._rgb, round(self._alpha, 6)))

    def __str__(self) -> str:
        """String representation."""
        return f"Color({self.hex(include_hash=True)})"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Color({self.hex(include_hash=True)}, alpha={self._alpha})"

    @classmethod
    def from_lab(cls, l: float, a: float, b: float, alpha: float = 1.0) -> Color:
        """
        Create Color from Lab values using colorspacious.

        Args:
            l: Lightness (0-100)
            a: Green-red axis
            b: Blue-yellow axis
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")

        try:
            # Convert Lab to RGB using colorspacious
            lab = np.array([l, a, b])
            rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            rgb = tuple(max(0, min(255, int(c))) for c in rgb)

            # Create Color instance
            color = cls(rgb)
            color._alpha = alpha
            return color

        except Exception as e:
            raise ValueError(f"Invalid Lab values ({l}, {a}, {b}): {e}")

    @classmethod
    def from_lch(cls, l: float, c: float, h: float, alpha: float = 1.0) -> Color:
        """
        Create Color from LCH values using colorspacious.

        Args:
            l: Lightness (0-100)
            c: Chroma
            h: Hue angle (0-360)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")

        try:
            # Convert LCH to RGB using colorspacious
            lch = np.array([l, c, h])
            rgb = colorspacious.cspace_convert(lch, "CIELCh", "sRGB255")
            rgb = tuple(max(0, min(255, int(c))) for c in rgb)

            # Create Color instance
            color = cls(rgb)
            color._alpha = alpha
            return color

        except Exception as e:
            raise ValueError(f"Invalid LCH values ({l}, {c}, {h}): {e}")

    @classmethod
    def from_hsl(cls, h: float, s: float, l: float, alpha: float = 1.0) -> Color:
        """
        Create Color from HSL values.

        Args:
            h: Hue angle (0-360)
            s: Saturation (0.0-1.0)
            l: Lightness (0.0-1.0)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"Saturation must be between 0.0 and 1.0, got {s}")
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")

        color = cls((0, 0, 0))  # Temporary RGB values
        color._rgb = color._hsl_to_rgb(h, s, l)
        color._alpha = alpha
        return color

    @classmethod
    def from_oklab(cls, l: float, a: float, b: float, alpha: float = 1.0) -> Color:
        """
        Create Color from OKLab values.

        Args:
            l: Lightness (0.0-1.0)
            a: Green-red component
            b: Blue-yellow component
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance

        Raises:
            ValueError: If values are outside valid ranges
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")

        color = cls((0, 0, 0))  # Temporary RGB values
        color._rgb = ColorSpaceConverter.oklab_to_rgb(l, a, b)
        color._alpha = alpha
        return color

    @classmethod
    def from_oklch(cls, l: float, c: float, h: float, alpha: float = 1.0) -> Color:
        """
        Create Color from OKLCh values.

        Args:
            l: Lightness (0.0-1.0)
            c: Chroma (saturation)
            h: Hue angle in degrees (0-360)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance

        Raises:
            ValueError: If values are outside valid ranges
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")
        if c < 0.0:
            raise ValueError(f"Chroma must be non-negative, got {c}")

        color = cls((0, 0, 0))  # Temporary RGB values
        color._rgb = ColorSpaceConverter.oklch_to_rgb(l, c, h)
        color._alpha = alpha
        return color