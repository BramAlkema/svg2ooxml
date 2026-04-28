#!/usr/bin/env python3
"""
Core Color class with fluent API and NumPy/colorspacious backend.

This module provides the primary Color class that supports method chaining
and leverages colorspacious for accurate color science operations.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .core_cache import cached_color_convert as _cached_color_convert
from .core_factories import ColorFactoryMixin
from .core_outputs import ColorOutputMixin
from .core_parsing import ColorParsingMixin
from .core_science import ColorScienceMixin
from .core_transformations import ColorTransformationMixin


class Color(
    ColorParsingMixin,
    ColorTransformationMixin,
    ColorOutputMixin,
    ColorScienceMixin,
    ColorFactoryMixin,
):
    """
    Immutable Color class with fluent API and professional color science backend.

    Uses colorspacious and NumPy for accurate, performant color operations while
    providing an intuitive chainable interface for color manipulation.

    Examples:
        >>> color = Color('#ff0000')
        >>> result = color.darken(0.2).saturate(1.5).hex()
        >>> palette = Color('#3498db').analogous(5)
    """

    def __init__(
        self,
        value: (
            str
            | tuple[int, int, int]
            | tuple[int, int, int, float]
            | dict[str, Any]
            | np.ndarray
        ),
    ):
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
        self._input_value = value
        self._rgb = None
        self._alpha = 1.0
        self._parse_input(value)

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


__all__ = ["Color", "_cached_color_convert"]
