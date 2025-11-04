"""Value formatters for animation TAV elements.

This module provides formatters that convert animation values (strings)
into lxml elements suitable for use in <a:tav> elements.

Each formatter produces a <a:val> element with the appropriate child
structure for the value type (numeric, color, point, angle).
"""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_elem, a_sub

from .value_processors import ValueProcessor

__all__ = [
    "format_numeric_value",
    "format_color_value",
    "format_point_value",
    "format_angle_value",
]


def format_numeric_value(value: str) -> etree._Element:
    """Format numeric value as <a:val val="..."/>.

    Used for simple numeric animations (position, size, etc.).

    Args:
        value: Numeric value as string (already normalized to PPT units)

    Returns:
        lxml Element: <a:val val="..."/>

    Example:
        >>> elem = format_numeric_value("914400")
        >>> # <a:val val="914400"/>
    """
    return a_elem("val", val=value)


def format_color_value(value: str) -> etree._Element:
    """Format color as <a:val><a:srgbClr val="..."/></a:val>.

    Used for color animations (fill, stroke, etc.).

    Args:
        value: Color string (hex, rgb, named, etc.)

    Returns:
        lxml Element: <a:val> with <a:srgbClr> child

    Example:
        >>> elem = format_color_value("#FF0000")
        >>> # <a:val><a:srgbClr val="FF0000"/></a:val>
    """
    # Parse color to hex (without #)
    hex_color = ValueProcessor.parse_color(value)

    # Build <a:val><a:srgbClr val="..."/></a:val>
    val = a_elem("val")
    a_sub(val, "srgbClr", val=hex_color)

    return val


def format_point_value(value: str) -> etree._Element:
    """Format point as <a:val><a:pt x="..." y="..."/></a:val>.

    Used for scale animations (which use 2D points in PowerPoint).

    The value string should contain two space/comma-separated numbers
    representing x and y scale factors (or coordinates).

    Args:
        value: Point string like "1.5 2.0" or "100 200"

    Returns:
        lxml Element: <a:val> with <a:pt> child

    Example:
        >>> elem = format_point_value("1.5 2.0")
        >>> # <a:val><a:pt x="1.5" y="2.0"/></a:val>
    """
    # Parse scale/point pair
    x, y = ValueProcessor.parse_scale_pair(value)

    # Convert to strings (preserve decimals for scale factors)
    x_str = str(x)
    y_str = str(y)

    # Build <a:val><a:pt x="..." y="..."/></a:val>
    val = a_elem("val")
    a_sub(val, "pt", x=x_str, y=y_str)

    return val


def format_angle_value(value: str) -> etree._Element:
    """Format angle as <a:val val="..."/> (in 60000ths of a degree).

    Used for rotation animations. The value is converted from degrees
    to PowerPoint's angle units (60000ths).

    Args:
        value: Angle string in degrees (e.g., "45")

    Returns:
        lxml Element: <a:val val="..."/> with angle in PPT units

    Example:
        >>> elem = format_angle_value("45")
        >>> # <a:val val="2700000"/>  (45 * 60000)
    """
    # Parse angle in degrees
    degrees = ValueProcessor.parse_angle(value)

    # Convert to PowerPoint units (60000ths)
    ppt_angle = ValueProcessor.format_ppt_angle(degrees)

    return a_elem("val", val=ppt_angle)
