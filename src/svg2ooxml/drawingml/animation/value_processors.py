"""Value processing for animation attributes.

This module provides animation-specific value processing, leveraging the
centralized conversions module for core parsing/conversion logic.

Most parsing is delegated to `svg2ooxml.common.conversions`. This module
adds animation-specific normalization (attribute → PowerPoint units).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.common.conversions import (
    parse_numeric_list,
    parse_angle,
    parse_scale_pair,
    parse_translation_pair,
    color_to_hex,
    degrees_to_ppt,
    opacity_to_ppt,
    px_to_emu,
)

from .constants import ANGLE_ATTRIBUTES, AXIS_MAP

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter

__all__ = ["ValueProcessor"]


class ValueProcessor:
    """Process and normalize animation values for PowerPoint.

    This class acts as an adapter around `common.conversions`, adding
    animation-specific attribute normalization logic.

    Most methods are simple delegates to the conversions module.
    The key animation-specific logic is in `normalize_numeric_value()`.
    """

    # ------------------------------------------------------------------ #
    # Core Parsing (Delegates to common.conversions)                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_numeric_list(value: str) -> list[float]:
        """Parse space/comma-separated numeric list.

        Delegates to: common.conversions.parse_numeric_list

        Args:
            value: String like "1 2 3" or "1.5, 2.5, 3.5"

        Returns:
            List of floats

        Example:
            >>> ValueProcessor.parse_numeric_list("1 2 3")
            [1.0, 2.0, 3.0]
        """
        return parse_numeric_list(value)

    @staticmethod
    def parse_color(value: str | None, *, default: str = "000000") -> str:
        """Parse color value to hex format (without #).

        Delegates to: common.conversions.color_to_hex

        Args:
            value: Color string (hex, rgb, named, etc.)
            default: Default color if parsing fails

        Returns:
            Hex color string (without #)

        Example:
            >>> ValueProcessor.parse_color("#FF0000")
            'FF0000'
        """
        return color_to_hex(value, default=default)

    @staticmethod
    def parse_angle(value: str) -> float:
        """Parse angle value in degrees.

        Delegates to: common.conversions.parse_angle

        Args:
            value: Angle string like "45" or "45deg"

        Returns:
            Angle in degrees

        Example:
            >>> ValueProcessor.parse_angle("45")
            45.0
        """
        return parse_angle(value)

    @staticmethod
    def parse_scale_pair(value: str) -> tuple[float, float]:
        """Parse scale value (single number or x,y pair).

        Delegates to: common.conversions.parse_scale_pair

        Args:
            value: Scale string like "1.5" or "1.5 2.0"

        Returns:
            (scale_x, scale_y) tuple

        Example:
            >>> ValueProcessor.parse_scale_pair("1.5")
            (1.5, 1.5)
            >>> ValueProcessor.parse_scale_pair("1.5 2.0")
            (1.5, 2.0)
        """
        return parse_scale_pair(value)

    @staticmethod
    def parse_translation_pair(value: str) -> tuple[float, float]:
        """Parse translation value (dx dy or dx,dy).

        Delegates to: common.conversions.parse_translation_pair

        Args:
            value: Translation string like "10 20"

        Returns:
            (dx, dy) tuple

        Example:
            >>> ValueProcessor.parse_translation_pair("10 20")
            (10.0, 20.0)
        """
        return parse_translation_pair(value)

    # ------------------------------------------------------------------ #
    # Animation-Specific Processing                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_opacity(value: str) -> str:
        """Parse opacity value to PowerPoint units (0-100000).

        Handles both 0-1 scale and 0-100 percentage scale.
        Returns string representation of PPT opacity units.

        Args:
            value: Opacity string like "0.7" or "70"

        Returns:
            String representation of PPT opacity (100000ths)

        Example:
            >>> ValueProcessor.parse_opacity("0.7")
            '70000'
            >>> ValueProcessor.parse_opacity("0.5")
            '50000'
        """
        try:
            opacity_float = float(value)
        except (ValueError, TypeError):
            opacity_float = 1.0  # Default to fully opaque

        # If value > 1, assume percentage (0-100), otherwise assume 0-1
        if opacity_float > 1.0:
            opacity_float = opacity_float / 100.0

        ppt_opacity = opacity_to_ppt(opacity_float)
        return str(ppt_opacity)

    @staticmethod
    def format_ppt_angle(degrees: float) -> str:
        """Convert degrees to PowerPoint angle units (60000ths).

        Args:
            degrees: Angle in degrees

        Returns:
            String representation of PPT angle units

        Example:
            >>> ValueProcessor.format_ppt_angle(45.0)
            '2700000'
        """
        ppt_angle = degrees_to_ppt(degrees)
        return str(ppt_angle)

    @staticmethod
    def normalize_numeric_value(
        attribute: str,
        value: str,
        *,
        unit_converter: UnitConverter,
    ) -> str:
        """Normalize numeric value to PowerPoint units (EMU or 60000ths).

        This is the key animation-specific logic that handles:
        - Angle attributes → degrees * 60000
        - Position/size attributes → px → EMU (using axis hint)

        Args:
            attribute: Attribute name (e.g., "ppt_x", "ppt_angle")
            value: Value string
            unit_converter: UnitConverter instance for px → EMU conversion

        Returns:
            String representation of normalized value

        Example:
            >>> uc = UnitConverter()
            >>> ValueProcessor.normalize_numeric_value("ppt_angle", "45", unit_converter=uc)
            '2700000'
            >>> ValueProcessor.normalize_numeric_value("ppt_x", "100", unit_converter=uc)
            '914400'
        """
        # Parse numeric value
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            return value  # Return as-is if can't parse

        # Angle attributes: degrees → 60000ths
        if attribute in ANGLE_ATTRIBUTES:
            return ValueProcessor.format_ppt_angle(numeric_value)

        # Position/size attributes: px → EMU
        # Get axis hint for proper DPI conversion
        axis = AXIS_MAP.get(attribute)
        emu = unit_converter.to_emu(numeric_value, axis=axis)
        return str(int(round(emu)))
