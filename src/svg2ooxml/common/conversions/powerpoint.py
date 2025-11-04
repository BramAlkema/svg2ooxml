"""High-level PowerPoint conversion utilities.

This module provides a unified PPTConverter class that combines all conversion
utilities into a single convenient interface.
"""

from __future__ import annotations

from .units import UnitConverter, px_to_emu as _px_to_emu, DEFAULT_DPI
from .colors import color_to_hex
from .angles import degrees_to_ppt, radians_to_ppt
from .opacity import opacity_to_ppt
from .transforms import parse_scale_pair, parse_translation_pair, parse_angle

__all__ = ["PPTConverter"]


class PPTConverter:
    """Unified PowerPoint conversion utilities.

    This class provides a convenient interface for all PowerPoint-specific
    conversions including units, colors, angles, opacity, and transform parsing.

    Example:
        >>> ppt = PPTConverter()
        >>> ppt.px_to_emu(100.0)
        914400
        >>> ppt.degrees_to_ppt(45.0)
        2700000
        >>> ppt.opacity_to_ppt(0.7)
        70000
        >>> ppt.color_to_hex("#FF0000")
        'FF0000'
    """

    def __init__(self, *, dpi: float = DEFAULT_DPI):
        """
        Initialize converter.

        Args:
            dpi: Dots per inch for unit conversions (default: 96)
        """
        self.dpi = dpi
        self._unit_converter = UnitConverter(dpi=dpi)

    # ------------------------------------------------------------------ #
    # Units                                                              #
    # ------------------------------------------------------------------ #

    def px_to_emu(self, px: float, *, axis: str | None = None) -> int:
        """
        Convert pixels to EMU (English Metric Units).

        Args:
            px: Pixel value
            axis: Optional axis hint for unit conversion

        Returns:
            EMU value (int)

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.px_to_emu(100.0)
            914400
        """
        emu = self._unit_converter.to_emu(px, axis=axis)
        return int(round(emu))

    def length_to_emu(self, value: str | float, *, axis: str | None = None) -> int:
        """
        Convert any length value to EMU.

        Supports: px, pt, cm, mm, in, etc.

        Args:
            value: Length value (string like "100px" or numeric)
            axis: Optional axis hint for unit conversion

        Returns:
            EMU value (int)

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.length_to_emu("1in")
            914400
            >>> ppt.length_to_emu(100.0)  # Defaults to px
            914400
        """
        emu = self._unit_converter.to_emu(value, axis=axis)
        return int(round(emu))

    # ------------------------------------------------------------------ #
    # Colors                                                             #
    # ------------------------------------------------------------------ #

    def color_to_hex(self, color: str | None, *, default: str = "000000") -> str:
        """
        Convert color to hex format.

        Args:
            color: Color string (hex, rgb, named color, etc.)
            default: Default color if parsing fails

        Returns:
            Hex color string (without #)

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.color_to_hex("#FF0000")
            'FF0000'
            >>> ppt.color_to_hex("red")
            'FF0000'
        """
        return color_to_hex(color, default=default)

    # ------------------------------------------------------------------ #
    # Angles                                                             #
    # ------------------------------------------------------------------ #

    def degrees_to_ppt(self, degrees: float) -> int:
        """
        Convert degrees to PowerPoint angle units (60000ths).

        Args:
            degrees: Angle in degrees

        Returns:
            PowerPoint angle units

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.degrees_to_ppt(45.0)
            2700000
        """
        return degrees_to_ppt(degrees)

    def radians_to_ppt(self, radians: float) -> int:
        """
        Convert radians to PowerPoint angle units (60000ths).

        Args:
            radians: Angle in radians

        Returns:
            PowerPoint angle units

        Example:
            >>> import math
            >>> ppt = PPTConverter()
            >>> ppt.radians_to_ppt(math.pi / 4)
            2700000
        """
        return radians_to_ppt(radians)

    # ------------------------------------------------------------------ #
    # Opacity                                                            #
    # ------------------------------------------------------------------ #

    def opacity_to_ppt(self, opacity: float) -> int:
        """
        Convert opacity (0-1) to PowerPoint units (100000ths).

        Args:
            opacity: Opacity 0.0-1.0

        Returns:
            PowerPoint opacity units

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.opacity_to_ppt(0.7)
            70000
        """
        return opacity_to_ppt(opacity)

    # ------------------------------------------------------------------ #
    # Transform parsing                                                  #
    # ------------------------------------------------------------------ #

    def parse_scale(self, value: str) -> tuple[float, float]:
        """
        Parse scale value.

        Args:
            value: Scale string like "1.5" or "1.5 2.0"

        Returns:
            (scale_x, scale_y) tuple

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.parse_scale("1.5")
            (1.5, 1.5)
            >>> ppt.parse_scale("1.5 2.0")
            (1.5, 2.0)
        """
        return parse_scale_pair(value)

    def parse_translation(self, value: str) -> tuple[float, float]:
        """
        Parse translation value.

        Args:
            value: Translation string like "10 20"

        Returns:
            (dx, dy) tuple

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.parse_translation("10 20")
            (10.0, 20.0)
        """
        return parse_translation_pair(value)

    def parse_angle(self, value: str) -> float:
        """
        Parse angle value.

        Args:
            value: Angle string like "45" or "45deg"

        Returns:
            Angle in degrees

        Example:
            >>> ppt = PPTConverter()
            >>> ppt.parse_angle("45")
            45.0
        """
        return parse_angle(value)
