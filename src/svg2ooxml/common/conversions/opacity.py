"""Opacity and alpha channel conversion utilities.

PowerPoint uses 100000ths scale (0-100000) for opacity/alpha values.
- 100000 = fully opaque (100%)
- 50000 = 50% opaque
- 0 = fully transparent (0%)

SVG/CSS typically uses:
- 0-1 scale (0.0 = transparent, 1.0 = opaque)
- 0-100 percentage (0% = transparent, 100% = opaque)

This module provides conversions between these representations.
"""

from __future__ import annotations

# PowerPoint opacity/alpha unit: 1.0 = 100000 units
PPT_OPACITY_SCALE = 100000

__all__ = [
    "opacity_to_ppt",
    "ppt_to_opacity",
    "alpha_to_ppt",
    "ppt_to_alpha",
    "percentage_to_ppt",
    "ppt_to_percentage",
    "parse_opacity",
    "PPT_OPACITY_SCALE",
]


def opacity_to_ppt(opacity: float) -> int:
    """
    Convert opacity (0-1 scale) to PowerPoint units.

    Values are clamped to 0.0-1.0 range before conversion.

    Args:
        opacity: Opacity value 0.0-1.0 (0 = transparent, 1 = opaque)

    Returns:
        PowerPoint opacity units (0-100000)

    Example:
        >>> opacity_to_ppt(1.0)  # Fully opaque
        100000
        >>> opacity_to_ppt(0.5)  # 50% opaque
        50000
        >>> opacity_to_ppt(0.0)  # Fully transparent
        0
        >>> opacity_to_ppt(1.5)  # Clamped to 1.0
        100000
        >>> opacity_to_ppt(-0.5)  # Clamped to 0.0
        0
    """
    clamped = max(0.0, min(1.0, opacity))
    return int(round(clamped * PPT_OPACITY_SCALE))


def parse_opacity(value: str | float | int | None, default: float = 1.0) -> float:
    """Parse CSS/SVG opacity syntax and clamp it to ``0.0``-``1.0``.

    Numeric values use the SVG opacity scale directly; percentage tokens are
    resolved as CSS alpha percentages.
    """

    if value is None:
        return max(0.0, min(1.0, float(default)))
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))

    token = value.strip()
    if not token:
        return max(0.0, min(1.0, float(default)))
    try:
        if token.endswith("%"):
            parsed = float(token[:-1]) / 100.0
        else:
            parsed = float(token)
    except ValueError:
        parsed = float(default)
    return max(0.0, min(1.0, parsed))


def ppt_to_opacity(ppt_value: int) -> float:
    """
    Convert PowerPoint opacity units to 0-1 scale.

    Values are clamped to 0-100000 range before conversion.

    Args:
        ppt_value: PowerPoint opacity units (0-100000)

    Returns:
        Opacity 0.0-1.0

    Example:
        >>> ppt_to_opacity(100000)
        1.0
        >>> ppt_to_opacity(50000)
        0.5
        >>> ppt_to_opacity(0)
        0.0
    """
    clamped = max(0, min(PPT_OPACITY_SCALE, ppt_value))
    return clamped / PPT_OPACITY_SCALE


def alpha_to_ppt(alpha: float) -> int:
    """
    Convert alpha channel (0-1 scale) to PowerPoint units.

    This is an alias for opacity_to_ppt() as they use the same scale.

    Args:
        alpha: Alpha value 0.0-1.0 (0 = transparent, 1 = opaque)

    Returns:
        PowerPoint alpha units (0-100000)

    Example:
        >>> alpha_to_ppt(1.0)
        100000
        >>> alpha_to_ppt(0.7)
        70000
    """
    return opacity_to_ppt(alpha)


def ppt_to_alpha(ppt_value: int) -> float:
    """
    Convert PowerPoint alpha units to 0-1 scale.

    This is an alias for ppt_to_opacity() as they use the same scale.

    Args:
        ppt_value: PowerPoint alpha units (0-100000)

    Returns:
        Alpha 0.0-1.0

    Example:
        >>> ppt_to_alpha(100000)
        1.0
        >>> ppt_to_alpha(70000)
        0.7
    """
    return ppt_to_opacity(ppt_value)


def percentage_to_ppt(percentage: float) -> int:
    """
    Convert percentage (0-100) to PowerPoint opacity units.

    Args:
        percentage: Percentage 0-100

    Returns:
        PowerPoint opacity units (0-100000)

    Example:
        >>> percentage_to_ppt(100.0)  # 100% opaque
        100000
        >>> percentage_to_ppt(50.0)   # 50% opaque
        50000
        >>> percentage_to_ppt(0.0)    # 0% opaque (transparent)
        0
    """
    return opacity_to_ppt(percentage / 100.0)


def ppt_to_percentage(ppt_value: int) -> float:
    """
    Convert PowerPoint opacity units to percentage (0-100).

    Args:
        ppt_value: PowerPoint opacity units (0-100000)

    Returns:
        Percentage 0-100

    Example:
        >>> ppt_to_percentage(100000)
        100.0
        >>> ppt_to_percentage(50000)
        50.0
        >>> ppt_to_percentage(0)
        0.0
    """
    return ppt_to_opacity(ppt_value) * 100.0
