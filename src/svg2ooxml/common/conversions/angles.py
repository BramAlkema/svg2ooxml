"""Angle conversion utilities for PowerPoint.

PowerPoint uses 60000ths of a degree internally for angle values.
SVG/CSS typically uses degrees or radians.

This module provides conversions between these representations.
"""

from __future__ import annotations

import math

# PowerPoint angle unit: 1 degree = 60000 units
PPT_ANGLE_SCALE = 60000

__all__ = [
    "degrees_to_ppt",
    "radians_to_ppt",
    "ppt_to_degrees",
    "ppt_to_radians",
    "PPT_ANGLE_SCALE",
]


def degrees_to_ppt(degrees: float) -> int:
    """
    Convert degrees to PowerPoint angle units (60000ths).

    Args:
        degrees: Angle in degrees

    Returns:
        PowerPoint angle units (int)

    Example:
        >>> degrees_to_ppt(0.0)
        0
        >>> degrees_to_ppt(45.0)
        2700000
        >>> degrees_to_ppt(90.0)
        5400000
        >>> degrees_to_ppt(180.0)
        10800000
        >>> degrees_to_ppt(360.0)
        21600000
    """
    return int(round(degrees * PPT_ANGLE_SCALE))


def radians_to_ppt(radians: float) -> int:
    """
    Convert radians to PowerPoint angle units (60000ths).

    Args:
        radians: Angle in radians

    Returns:
        PowerPoint angle units (int)

    Example:
        >>> import math
        >>> radians_to_ppt(0.0)
        0
        >>> radians_to_ppt(math.pi / 4)  # 45 degrees
        2700000
        >>> radians_to_ppt(math.pi / 2)  # 90 degrees
        5400000
    """
    degrees = math.degrees(radians)
    return degrees_to_ppt(degrees)


def ppt_to_degrees(ppt_value: int) -> float:
    """
    Convert PowerPoint angle units to degrees.

    Args:
        ppt_value: PowerPoint angle units

    Returns:
        Angle in degrees

    Example:
        >>> ppt_to_degrees(0)
        0.0
        >>> ppt_to_degrees(2700000)
        45.0
        >>> ppt_to_degrees(5400000)
        90.0
    """
    return ppt_value / PPT_ANGLE_SCALE


def ppt_to_radians(ppt_value: int) -> float:
    """
    Convert PowerPoint angle units to radians.

    Args:
        ppt_value: PowerPoint angle units

    Returns:
        Angle in radians

    Example:
        >>> import math
        >>> ppt_to_radians(0)
        0.0
        >>> abs(ppt_to_radians(2700000) - math.pi / 4) < 0.0001
        True
    """
    degrees = ppt_to_degrees(ppt_value)
    return math.radians(degrees)
