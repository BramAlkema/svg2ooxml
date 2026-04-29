"""Transform value parsing utilities.

This module provides utilities for parsing transform-related values
commonly used in SVG and animation definitions.
"""

from __future__ import annotations

import re

from svg2ooxml.common.style.css_math import CSSMathError, evaluate_calc_string

_NUMBER_SOURCE = r"[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?"
_NUMBER_PATTERN = re.compile(_NUMBER_SOURCE)
_NUMERIC_SEPARATOR_PATTERN = re.compile(r"^[\s,]*$")
_ANGLE_TOKEN_PATTERN = re.compile(
    rf"^\s*(?P<number>{_NUMBER_SOURCE})(?P<unit>deg|grad|rad|turn)?\s*$",
    re.IGNORECASE,
)

__all__ = [
    "parse_scale_pair",
    "parse_translation_pair",
    "parse_angle",
    "parse_angle_strict",
    "parse_numeric_list",
    "parse_strict_numeric_list",
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

    if "calc(" not in value.lower():
        return _parse_plain_numbers(value)

    result: list[float] = []
    index = 0
    lower = value.lower()
    while index < len(value):
        calc_start = lower.find("calc(", index)
        if calc_start < 0:
            result.extend(_parse_plain_numbers(value[index:]))
            break

        result.extend(_parse_plain_numbers(value[index:calc_start]))
        calc_end = _find_function_end(value, calc_start)
        if calc_end is None:
            result.extend(_parse_plain_numbers(value[calc_start:]))
            break

        calc_token = value[calc_start:calc_end]
        try:
            calc_value = evaluate_calc_string(calc_token)
            if calc_value.kind in {"number", "percentage"}:
                result.append(calc_value.value)
            else:
                result.extend(_parse_plain_numbers(calc_token))
        except (CSSMathError, ZeroDivisionError):
            result.extend(_parse_plain_numbers(calc_token))
        index = calc_end

    return result


def _parse_plain_numbers(value: str) -> list[float]:
    result: list[float] = []
    for token in _NUMBER_PATTERN.findall(value):
        try:
            result.append(float(token))
        except ValueError:
            continue
    return result


def parse_strict_numeric_list(
    value: str | None,
    *,
    allow_calc: bool = False,
) -> list[float]:
    """Parse a numeric list and reject non-separator garbage."""

    if not value:
        return []
    if allow_calc and "calc(" in value.lower():
        return _parse_strict_numeric_calc_list(value)

    values: list[float] = []
    position = 0
    for match in _NUMBER_PATTERN.finditer(value):
        separator = value[position : match.start()]
        if not _NUMERIC_SEPARATOR_PATTERN.fullmatch(separator):
            raise ValueError(f"numeric list contains non-numeric values: {value!r}")
        values.append(float(match.group(0)))
        position = match.end()
    if not _NUMERIC_SEPARATOR_PATTERN.fullmatch(value[position:]):
        raise ValueError(f"numeric list contains non-numeric values: {value!r}")
    return values


def _parse_strict_numeric_calc_list(value: str) -> list[float]:
    values: list[float] = []
    position = 0
    first_token = True
    lower = value.lower()
    while position < len(value):
        separator_start = position
        while position < len(value) and (value[position].isspace() or value[position] == ","):
            position += 1
        if position >= len(value):
            break

        had_separator = position > separator_start
        if not first_token and not had_separator and value[position] not in "+-":
            raise ValueError(f"numeric list contains non-numeric values: {value!r}")

        if lower.startswith("calc(", position):
            if not first_token and not had_separator:
                raise ValueError(f"numeric list contains non-numeric values: {value!r}")
            calc_end = _find_function_end(value, position)
            if calc_end is None:
                raise ValueError(f"numeric list contains non-numeric values: {value!r}")
            try:
                calc_value = evaluate_calc_string(value[position:calc_end])
            except (CSSMathError, ZeroDivisionError) as exc:
                raise ValueError(f"numeric list contains non-numeric values: {value!r}") from exc
            if calc_value.kind not in {"number", "percentage"}:
                raise ValueError(f"numeric list contains non-numeric values: {value!r}")
            values.append(calc_value.value)
            position = calc_end
            first_token = False
            continue

        match = _NUMBER_PATTERN.match(value, position)
        if match is None:
            raise ValueError(f"numeric list contains non-numeric values: {value!r}")
        values.append(float(match.group(0)))
        position = match.end()
        first_token = False

    return values


def _find_function_end(value: str, start: int) -> int | None:
    depth = 0
    opened = False
    for index in range(start, len(value)):
        char = value[index]
        if char == "(":
            depth += 1
            opened = True
            continue
        if char == ")" and opened:
            depth -= 1
            if depth == 0:
                return index + 1
    return None


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

    Resolves CSS angle units and ``calc()`` expressions when possible, then
    falls back to the historical first-number behavior.

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
        >>> parse_angle("0.25turn")
        90.0
        >>> parse_angle("calc(1turn - 90deg)")
        270.0
        >>> parse_angle("")
        0.0
    """
    strict = parse_angle_strict(value)
    if strict is not None:
        return strict
    numbers = parse_numeric_list(value)
    return numbers[0] if numbers else 0.0


def parse_angle_strict(value: str | None) -> float | None:
    """Parse a single CSS/SVG angle token in degrees.

    Unitless values are treated as degrees. Invalid tokens return ``None`` so
    callers that need CSS-valid input do not accidentally accept the loose
    first-number fallback used by ``parse_angle``.
    """
    token = (value or "").strip()
    if not token:
        return None
    try:
        if token.lower().startswith("calc("):
            result = evaluate_calc_string(token)
            if result.kind == "angle":
                return result.as_degrees()
            if result.kind == "number":
                return result.value
            return None

        match = _ANGLE_TOKEN_PATTERN.match(token)
        if match is None:
            return None
        unit = match.group("unit")
        if unit:
            return evaluate_calc_string(
                f"calc({match.group('number')}{unit.lower()})"
            ).as_degrees()
        return float(match.group("number"))
    except (CSSMathError, ZeroDivisionError):
        return None
