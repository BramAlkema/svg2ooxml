"""Transform value parsing utilities.

This module provides utilities for parsing transform-related values
commonly used in SVG and animation definitions.
"""

from __future__ import annotations

import re

__all__ = [
    "parse_scale_pair",
    "parse_translation_pair",
    "parse_angle",
    "parse_numeric_list",
]


def parse_numeric_list(value: str) -> list[float]:
    """
    Parse space/comma-separated numeric list.

    Supports various formats:
    - Space-separated: "1.5 2.0 3.5"
    - Comma-separated: "1.5, 2.0, 3.5"
    - Mixed: "1.5,2.0 3.5"
    - Scientific notation: "1.5e-3 2.0e+2"

    Args:
        value: String containing numbers

    Returns:
        List of float values (empty list if no valid numbers found)

    Example:
        >>> parse_numeric_list("1.5 2.0 3.5")
        [1.5, 2.0, 3.5]
        >>> parse_numeric_list("1.5, 2.0, 3.5")
        [1.5, 2.0, 3.5]
        >>> parse_numeric_list("1.5e-3")
        [0.0015]
        >>> parse_numeric_list("")
        []
    """
    if not value:
        return []

    # Match numbers including scientific notation
    pattern = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
    tokens = re.findall(pattern, value)

    result: list[float] = []
    for token in tokens:
        try:
            result.append(float(token))
        except ValueError:
            continue

    return result


def parse_scale_pair(value: str) -> tuple[float, float]:
    """
    Parse scale value.

    Supports:
    - Single value: "1.5" → (1.5, 1.5) uniform scale
    - Pair: "1.5 2.0" → (1.5, 2.0) separate x/y scale
    - Empty: "" → (1.0, 1.0) identity scale

    Args:
        value: Scale value string

    Returns:
        (scale_x, scale_y) tuple

    Example:
        >>> parse_scale_pair("1.5")
        (1.5, 1.5)
        >>> parse_scale_pair("1.5 2.0")
        (1.5, 2.0)
        >>> parse_scale_pair("")
        (1.0, 1.0)
    """
    numbers = parse_numeric_list(value)
    if not numbers:
        return (1.0, 1.0)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (numbers[0], numbers[1])


def parse_translation_pair(value: str) -> tuple[float, float]:
    """
    Parse translation value.

    Supports:
    - Pair: "10 20" → (10.0, 20.0)
    - Comma-separated: "10,20" → (10.0, 20.0)
    - Single: "10" → (10.0, 0.0) x-only translation
    - Empty: "" → (0.0, 0.0) no translation

    Args:
        value: Translation value string

    Returns:
        (dx, dy) tuple

    Example:
        >>> parse_translation_pair("10 20")
        (10.0, 20.0)
        >>> parse_translation_pair("10")
        (10.0, 0.0)
        >>> parse_translation_pair("")
        (0.0, 0.0)
    """
    numbers = parse_numeric_list(value)
    if len(numbers) >= 2:
        return (numbers[0], numbers[1])
    if len(numbers) == 1:
        return (numbers[0], 0.0)
    return (0.0, 0.0)


def parse_angle(value: str) -> float:
    """
    Parse angle value (in degrees).

    Extracts the first number from the string, ignoring units.

    Args:
        value: Angle string like "45" or "45deg" or "45.5"

    Returns:
        Angle in degrees (0.0 if no valid number found)

    Example:
        >>> parse_angle("45")
        45.0
        >>> parse_angle("45deg")
        45.0
        >>> parse_angle("45.5")
        45.5
        >>> parse_angle("")
        0.0
    """
    numbers = parse_numeric_list(value)
    return numbers[0] if numbers else 0.0
