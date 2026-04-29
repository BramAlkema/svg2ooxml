"""Color parsing utilities shared across the project."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from svg2ooxml.common.conversions.transforms import parse_angle_strict
from svg2ooxml.common.math_utils import finite_float
from svg2ooxml.common.units.lengths import (
    parse_number,
    parse_number_or_percent,
    parse_percentage,
    split_length_list,
)

from .models import TRANSPARENT, Color
from .names import CSS3_NAMES_TO_HEX

_HEX_RE = re.compile(r"^#?(?P<value>[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_RE = re.compile(r"^rgba?\((?P<body>.+)\)$")
_HSL_RE = re.compile(r"^hsla?\((?P<body>.+)\)$")
_OKLAB_RE = re.compile(r"^oklab\((?P<body>.+)\)$")
_OKLCH_RE = re.compile(r"^oklch\((?P<body>.+)\)$")

# CSS system colors → sensible sRGB defaults
_SYSTEM_COLORS: dict[str, str] = {
    "canvas": "ffffff", "canvastext": "000000",
    "linktext": "0000ee", "visitedtext": "551a8b", "activetext": "ff0000",
    "buttonface": "f0f0f0", "buttontext": "000000", "buttonborder": "767676",
    "field": "ffffff", "fieldtext": "000000",
    "highlight": "3390ff", "highlighttext": "ffffff",
    "selecteditem": "3390ff", "selecteditemtext": "ffffff",
    "mark": "ffff00", "marktext": "000000",
    "graytext": "808080", "accentcolor": "0078d4", "accentcolortext": "ffffff",
}


def coerce_color(value) -> Color | None:
    """Attempt to interpret *value* as a ``Color`` instance."""
    if isinstance(value, Color):
        return value
    if not hasattr(value, "r") or not hasattr(value, "g") or not hasattr(value, "b"):
        return None
    red = finite_float(getattr(value, "r", None))
    green = finite_float(getattr(value, "g", None))
    blue = finite_float(getattr(value, "b", None))
    if red is None or green is None or blue is None:
        return None
    alpha = finite_float(getattr(value, "a", 1.0), 1.0)
    return Color(red, green, blue, alpha if alpha is not None else 1.0)


def parse_color(
    value: str | Color | object | None,
    *,
    current_color: Color | None = None,
    palette: Mapping[str, Color | str] | None = None,
) -> Color | None:
    if value is None:
        return None
    coerced = coerce_color(value)
    if coerced is not None:
        return coerced
    if not isinstance(value, str):
        return None

    token = value.strip()
    if not token:
        return None

    lowered = token.lower()
    if lowered == "none":
        return None
    if lowered == "transparent":
        return TRANSPARENT
    if lowered == "currentcolor":
        return current_color

    if palette:
        resolved = _lookup_palette(lowered, palette)
        if resolved is not None:
            return resolved

    try:
        hex_match = _HEX_RE.match(token)
        if hex_match:
            return _parse_hex(hex_match.group("value"))

        rgb_match = _RGB_RE.match(lowered)
        if rgb_match:
            return _parse_rgb(rgb_match.group("body"))

        hsl_match = _HSL_RE.match(lowered)
        if hsl_match:
            return _parse_hsl(hsl_match.group("body"))

        oklab_match = _OKLAB_RE.match(lowered)
        if oklab_match:
            return _parse_oklab(oklab_match.group("body"))

        oklch_match = _OKLCH_RE.match(lowered)
        if oklch_match:
            return _parse_oklch(oklch_match.group("body"))
    except ValueError:
        return None

    hex_value = CSS3_NAMES_TO_HEX.get(lowered)
    if hex_value:
        return _parse_hex(hex_value[1:])

    # CSS system colors
    system_hex = _SYSTEM_COLORS.get(lowered)
    if system_hex:
        return _parse_hex(system_hex)

    return None


def _lookup_palette(key: str, palette: Mapping[str, Color | str]) -> Color | None:
    candidate = palette.get(key)
    if candidate is None:
        candidate = palette.get(key.lower())
    if candidate is None and key.startswith("#"):
        candidate = palette.get(key[1:])
    if candidate is None:
        return None
    if isinstance(candidate, Color):
        return candidate
    return parse_color(candidate, palette=None)


def _parse_hex(value: str) -> Color:
    digits = value.lstrip("#")
    if len(digits) in {3, 4}:
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) == 6:
        digits += "ff"
    if len(digits) != 8:
        raise ValueError("hex colours must be 3, 4, 6, or 8 digits")
    r = int(digits[0:2], 16) / 255.0
    g = int(digits[2:4], 16) / 255.0
    b = int(digits[4:6], 16) / 255.0
    a = int(digits[6:8], 16) / 255.0
    return Color(r, g, b, a)


def _parse_rgb(body: str) -> Color:
    parts = _split_components(body, expected_min=3, expected_max=4)
    r = _parse_rgb_component(parts[0])
    g = _parse_rgb_component(parts[1])
    b = _parse_rgb_component(parts[2])
    a = _parse_alpha(parts[3]) if len(parts) == 4 else 1.0
    return Color(r, g, b, a)


def _parse_hsl(body: str) -> Color:
    parts = _split_components(body, expected_min=3, expected_max=4)
    h = _parse_hue(parts[0])
    s = _parse_percentage(parts[1])
    l = _parse_percentage(parts[2])  # noqa: E741 -- HSL spec notation for lightness
    a = _parse_alpha(parts[3]) if len(parts) == 4 else 1.0
    r, g, b = _hsl_to_rgb(h, s, l)
    return Color(r, g, b, a)


def _split_components(body: str, *, expected_min: int, expected_max: int) -> list[str]:
    token = body.strip()
    if _has_top_level_comma(token):
        parts = _split_top_level(token, separators={",", "/"})
    else:
        main, alpha = _partition_top_level_slash(token)
        parts = split_length_list(main)
        if alpha is not None and alpha.strip():
            parts.append(alpha.strip())
    if not (expected_min <= len(parts) <= expected_max):
        raise ValueError("unexpected number of parameters")
    return parts


def _has_top_level_comma(value: str) -> bool:
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            continue
        if depth == 0 and char == ",":
            return True
    return False


def _partition_top_level_slash(value: str) -> tuple[str, str | None]:
    depth = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            continue
        if depth == 0 and char == "/":
            return value[:index].strip(), value[index + 1 :].strip()
    return value, None


def _split_top_level(value: str, *, separators: set[str]) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
            current.append(char)
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            current.append(char)
            continue
        if depth == 0 and char in separators:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _parse_rgb_component(component: str) -> float:
    percent = parse_percentage(component, math.nan)
    if not math.isnan(percent):
        return round(_clamp(percent) * 255.0) / 255.0

    value = parse_number(component, math.nan)
    if math.isnan(value):
        raise ValueError("expected RGB component")
    return _clamp(value / 255.0)


def _parse_alpha(component: str) -> float:
    value = parse_number_or_percent(component, math.nan)
    if math.isnan(value):
        raise ValueError("expected alpha component")
    return _clamp(value)


def _parse_hue(component: str) -> float:
    value = parse_angle_strict(component)
    if value is None:
        raise ValueError("expected hue component")
    return (value % 360.0) / 360.0


def _parse_percentage(component: str) -> float:
    value = parse_percentage(component, math.nan)
    if math.isnan(value):
        raise ValueError("expected percentage")
    return _clamp(value)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:  # noqa: E741 -- HSL spec notation for lightness
    if s == 0.0:
        return l, l, l
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = _hue_to_rgb(p, q, h + 1 / 3)
    g = _hue_to_rgb(p, q, h)
    b = _hue_to_rgb(p, q, h - 1 / 3)
    return r, g, b


def _hue_to_rgb(p: float, q: float, t: float) -> float:
    t = t % 1.0
    if t < 1 / 6:
        return p + (q - p) * 6 * t
    if t < 1 / 2:
        return q
    if t < 2 / 3:
        return p + (q - p) * (2 / 3 - t) * 6
    return p


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _parse_oklab(body: str) -> Color | None:
    """Parse ``oklab(L a b [/ alpha])`` → Color (sRGB)."""
    from .oklab import oklab_to_rgb

    parts = _split_components(body, expected_min=3, expected_max=4)
    if len(parts) < 3:
        return None
    l_val = parse_number_or_percent(parts[0], math.nan)
    a_val = parse_number(parts[1], math.nan)
    b_val = parse_number(parts[2], math.nan)
    alpha = _parse_alpha(parts[3]) if len(parts) > 3 else 1.0
    if any(math.isnan(value) for value in (l_val, a_val, b_val, alpha)):
        return None
    r, g, b = oklab_to_rgb(l_val, a_val, b_val)
    return Color(_clamp(r), _clamp(g), _clamp(b), _clamp(alpha))


def _parse_oklch(body: str) -> Color | None:
    """Parse ``oklch(L C H [/ alpha])`` → Color (sRGB)."""
    from .oklab import oklch_to_rgb

    parts = _split_components(body, expected_min=3, expected_max=4)
    if len(parts) < 3:
        return None
    l_val = parse_number_or_percent(parts[0], math.nan)
    c_val = parse_number(parts[1], math.nan)
    h_val = parse_angle_strict(parts[2])
    alpha = _parse_alpha(parts[3]) if len(parts) > 3 else 1.0
    if (
        math.isnan(l_val)
        or math.isnan(c_val)
        or h_val is None
        or math.isnan(alpha)
    ):
        return None
    r, g, b = oklch_to_rgb(l_val, c_val, h_val)
    return Color(_clamp(r), _clamp(g), _clamp(b), _clamp(alpha))


__all__ = ["parse_color"]
