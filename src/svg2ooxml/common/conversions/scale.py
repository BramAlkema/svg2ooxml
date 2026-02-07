"""Scale and position conversion utilities for PowerPoint.

PowerPoint uses 100000ths scale for percentage/scale values:
- 100000 = 100% (1.0)
- 50000 = 50% (0.5)
- 200000 = 200% (2.0)

For positions (gradient stops, radial fill rects), values are clamped to 0-1.
For scale factors, values are unclamped (can exceed 1.0).
"""

from __future__ import annotations

# PowerPoint scale/percentage unit: 1.0 = 100000 units
PPT_SCALE = 100000

__all__ = [
    "scale_to_ppt",
    "position_to_ppt",
    "PPT_SCALE",
]


def scale_to_ppt(factor: float) -> int:
    """Convert a scale factor to PowerPoint units (100000ths).

    No clamping — scale factors can exceed 1.0 (e.g. 2.0 = 200%).

    Args:
        factor: Scale factor (1.0 = 100%)

    Returns:
        PowerPoint scale units (int)

    Example:
        >>> scale_to_ppt(1.0)
        100000
        >>> scale_to_ppt(0.5)
        50000
        >>> scale_to_ppt(2.0)
        200000
        >>> scale_to_ppt(0.0)
        0
    """
    return int(round(factor * PPT_SCALE))


def position_to_ppt(fraction: float) -> int:
    """Convert a fractional position (0-1) to PowerPoint units (100000ths).

    Values are clamped to 0.0-1.0 range before conversion.

    Args:
        fraction: Position as fraction 0.0-1.0

    Returns:
        PowerPoint position units (0-100000)

    Example:
        >>> position_to_ppt(0.0)
        0
        >>> position_to_ppt(0.5)
        50000
        >>> position_to_ppt(1.0)
        100000
        >>> position_to_ppt(1.5)
        100000
        >>> position_to_ppt(-0.5)
        0
    """
    clamped = max(0.0, min(1.0, fraction))
    return int(round(clamped * PPT_SCALE))
