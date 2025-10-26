"""Color parsing utilities shared across the project."""

from __future__ import annotations

import math
import re
from typing import Mapping

from .models import Color, TRANSPARENT
from .names import CSS3_NAMES_TO_HEX

_HEX_RE = re.compile(r"^#?(?P<value>[0-9a-fA-F]{3,8})$")
_RGB_RE = re.compile(r"rgba?\((?P<body>.+)\)")
_HSL_RE = re.compile(r"hsla?\((?P<body>.+)\)")


def parse_color(
    value: str | Color | None,
    *,
    current_color: Color | None = None,
    palette: Mapping[str, Color | str] | None = None,
) -> Color | None:
    if value is None:
        return None
    if isinstance(value, Color):
        return value

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

    hex_match = _HEX_RE.match(token)
    if hex_match:
        return _parse_hex(hex_match.group("value"))

    rgb_match = _RGB_RE.match(lowered)
    if rgb_match:
        return _parse_rgb(rgb_match.group("body"))

    hsl_match = _HSL_RE.match(lowered)
    if hsl_match:
        return _parse_hsl(hsl_match.group("body"))

    hex_value = CSS3_NAMES_TO_HEX.get(lowered)
    if hex_value:
        return _parse_hex(hex_value[1:])

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
    l = _parse_percentage(parts[2])
    a = _parse_alpha(parts[3]) if len(parts) == 4 else 1.0
    r, g, b = _hsl_to_rgb(h, s, l)
    return Color(r, g, b, a)


def _split_components(body: str, *, expected_min: int, expected_max: int) -> list[str]:
    parts = [segment.strip() for segment in re.split(r"[,/]|(?<!\d)\s+", body) if segment.strip()]
    if not (expected_min <= len(parts) <= expected_max):
        raise ValueError("unexpected number of parameters")
    return parts


def _parse_rgb_component(component: str) -> float:
    if component.endswith("%"):
        value = float(component[:-1]) / 100.0
        return _clamp(value)
    return _clamp(float(component) / 255.0)


def _parse_alpha(component: str) -> float:
    if component.endswith("%"):
        return _clamp(float(component[:-1]) / 100.0)
    return _clamp(float(component))


def _parse_hue(component: str) -> float:
    if component.endswith("deg"):
        value = float(component[:-3])
    elif component.endswith("rad"):
        value = math.degrees(float(component[:-3]))
    elif component.endswith("turn"):
        value = float(component[:-4]) * 360.0
    else:
        value = float(component)
    return (value % 360.0) / 360.0


def _parse_percentage(component: str) -> float:
    if not component.endswith("%"):
        raise ValueError("expected percentage")
    return _clamp(float(component[:-1]) / 100.0)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
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


__all__ = ["parse_color"]
