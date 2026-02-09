"""Value formatters for animation TAV elements.

This module provides formatters that convert animation values (strings)
into lxml elements suitable for use in <a:tav> elements.

Each formatter produces a <a:val> element with the appropriate child
structure for the value type (numeric, color, point, angle).
"""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub

from .value_processors import ValueProcessor

__all__ = [
    "format_numeric_value",
    "format_color_value",
    "format_point_value",
    "format_angle_value",
]


def format_numeric_value(value: str) -> etree._Element:
    """Format numeric value as <p:val><p:fltVal val="..."/></p:val>.

    Used for simple numeric animations (position, size, etc.).

    Args:
        value: Numeric value as string (already normalized to PPT units)

    Returns:
        lxml Element: <p:val> with <p:fltVal> child

    Example:
        >>> elem = format_numeric_value("914400")
        >>> # <p:val><p:fltVal val="914400"/></p:val>
    """
    val = p_elem("val")
    p_sub(val, "fltVal", val=value)
    return val


def format_color_value(value: str) -> etree._Element:
    """Format color as <p:val><p:clrVal><a:srgbClr val="..."/></p:clrVal></p:val>.

    Used for color animations (fill, stroke, etc.).

    Args:
        value: Color string (hex, rgb, named, etc.)

    Returns:
        lxml Element: <p:val> with <p:clrVal>/<a:srgbClr> children

    Example:
        >>> elem = format_color_value("#FF0000")
        >>> # <p:val><p:clrVal><a:srgbClr val="FF0000"/></p:clrVal></p:val>
    """
    # Parse color to hex (without #)
    hex_color = ValueProcessor.parse_color(value)

    # Build <p:val><p:clrVal><a:srgbClr val="..."/></p:clrVal></p:val>
    val = p_elem("val")
    clr_val = p_sub(val, "clrVal")
    a_sub(clr_val, "srgbClr", val=hex_color)

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

    # Convert to strings while trimming trailing zeros but keep a decimal place
    def _fmt(value: float) -> str:
        formatted = f"{value:.6f}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        if "." not in formatted:
            formatted = f"{formatted}.0"
        return formatted

    x_str = _fmt(x)
    y_str = _fmt(y)

    # Build <p:val><p:pt x="..." y="..."/></p:val>
    val = p_elem("val")
    p_sub(val, "pt", x=x_str, y=y_str)

    return val


def format_angle_value(value: str) -> etree._Element:
    """Format angle as <p:val><p:fltVal val="..."/></p:val> (in 60000ths of a degree).

    Used for rotation animations. The value is converted from degrees
    to PowerPoint's angle units (60000ths).

    Args:
        value: Angle string in degrees (e.g., "45")

    Returns:
        lxml Element: <p:val> with <p:fltVal> child (angle in PPT units)

    Example:
        >>> elem = format_angle_value("45")
        >>> # <p:val><p:fltVal val="2700000"/></p:val>  (45 * 60000)
    """
    # Parse angle in degrees
    degrees = ValueProcessor.parse_angle(value)

    # Convert to PowerPoint units (60000ths)
    ppt_angle = ValueProcessor.format_ppt_angle(degrees)

    val = p_elem("val")
    p_sub(val, "fltVal", val=ppt_angle)
    return val
