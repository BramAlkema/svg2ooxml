"""Input parsing helpers for the advanced Color class."""

from __future__ import annotations

import re
from typing import Any

from svg2ooxml.common.numpy_compat import require_numpy

np = require_numpy(
    "Advanced color support requires NumPy; install the 'color' extra."
)


class ColorParsingMixin:
    """Parse supported color inputs into internal RGB/alpha state."""

    def _parse_input(self, value: Any) -> None:
        """Parse input value and set internal RGB representation."""
        if isinstance(value, str):
            self._parse_string_value(value)
        elif isinstance(value, tuple):
            self._parse_tuple_value(value)
        elif isinstance(value, dict):
            self._parse_dict_value(value)
        elif isinstance(value, np.ndarray):
            self._parse_numpy_value(value)
        else:
            raise TypeError(f"Unsupported color input type: {type(value)}")

    def _parse_string_value(self, value: str) -> None:
        """Parse string color values."""
        value = value.strip().lower()

        if value.startswith("#"):
            hex_val = value[1:]
            if len(hex_val) == 3:
                hex_val = "".join(c * 2 for c in hex_val)
            elif len(hex_val) == 6:
                pass
            elif len(hex_val) == 8:
                self._alpha = round(int(hex_val[6:8], 16) / 255.0, 10)
                hex_val = hex_val[:6]
            else:
                raise ValueError(f"Invalid hex color format: {value}")

            try:
                self._rgb = tuple(int(hex_val[i : i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                raise ValueError(f"Invalid hex color format: {value}") from None

        elif value.startswith("rgb"):
            self._parse_rgb_function(value)
        elif value.startswith("hsl"):
            self._parse_hsl_function(value)
        elif value in ["transparent", "none"]:
            self._rgb = (0, 0, 0)
            self._alpha = 0.0
        else:
            from .css_colors import get_css_color

            css_color = get_css_color(value)
            if css_color:
                self._rgb = css_color
                if value.lower() == "transparent":
                    self._alpha = 0.0
            else:
                raise ValueError(f"Unknown color name: {value}")

    def _parse_rgb_function(self, value: str) -> None:
        if value.startswith("rgba"):
            pattern = (
                r"rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,"
                r"\s*([\d.]+)\s*\)"
            )
            match = re.match(pattern, value)
            if match:
                r, g, b, a = match.groups()
                r, g, b = int(r), int(g), int(b)
                if not all(0 <= c <= 255 for c in [r, g, b]):
                    raise ValueError(f"Invalid rgb format: {value}")
                self._rgb = (r, g, b)
                self._alpha = float(a)
            else:
                raise ValueError(f"Invalid rgba format: {value}")
            return

        pattern = r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
        match = re.match(pattern, value)
        if match:
            r, g, b = match.groups()
            r, g, b = int(r), int(g), int(b)
            if not all(0 <= c <= 255 for c in [r, g, b]):
                raise ValueError(f"Invalid rgb format: {value}")
            self._rgb = (r, g, b)
        else:
            raise ValueError(f"Invalid rgb format: {value}")

    def _parse_hsl_function(self, value: str) -> None:
        if value.startswith("hsla"):
            pattern = (
                r"hsla\s*\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,"
                r"\s*([\d.]+)%\s*,\s*([\d.]+)\s*\)"
            )
            match = re.match(pattern, value)
            if match:
                h, s, l_value, a = match.groups()
                h, s, l_value = float(h), float(s), float(l_value)
                if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= l_value <= 100):
                    raise ValueError(f"Invalid hsl format: {value}")
                self._rgb = self._hsl_to_rgb(h, s / 100, l_value / 100)
                self._alpha = float(a)
            else:
                raise ValueError(f"Invalid hsla format: {value}")
            return

        pattern = r"hsl\s*\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)"
        match = re.match(pattern, value)
        if match:
            h, s, l_value = match.groups()
            h, s, l_value = float(h), float(s), float(l_value)
            if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= l_value <= 100):
                raise ValueError(f"Invalid hsl format: {value}")
            self._rgb = self._hsl_to_rgb(h, s / 100, l_value / 100)
        else:
            raise ValueError(f"Invalid hsl format: {value}")

    def _parse_tuple_value(self, value: tuple) -> None:
        """Parse tuple color values."""
        if len(value) < 3:
            raise ValueError(f"Color tuple must have at least 3 values, got {len(value)}")

        for i, component in enumerate(value[:3]):
            if not isinstance(component, (int, float)) or not 0 <= component <= 255:
                raise ValueError(f"RGB component {i} must be 0-255, got {component}")

        self._rgb = tuple(int(c) for c in value[:3])

        if len(value) > 3:
            alpha = value[3]
            if not isinstance(alpha, (int, float)) or not 0.0 <= alpha <= 1.0:
                raise ValueError(f"Alpha must be 0.0-1.0, got {alpha}")
            self._alpha = float(alpha)

    def _parse_dict_value(self, value: dict) -> None:
        """Parse dictionary color values (HSL, etc.)."""
        if "h" in value and "s" in value and "l" in value:
            h = value.get("h", 0)
            s = value.get("s", 0) / 100.0 if value.get("s", 0) > 1 else value.get("s", 0)
            l_value = (
                value.get("l", 0) / 100.0
                if value.get("l", 0) > 1
                else value.get("l", 0)
            )
            self._rgb = self._hsl_to_rgb(h, s, l_value)
            self._alpha = value.get("a", 1.0)
        elif "r" in value and "g" in value and "b" in value:
            self._rgb = (int(value["r"]), int(value["g"]), int(value["b"]))
            self._alpha = value.get("a", 1.0)
        else:
            raise ValueError(f"Unsupported dictionary color format: {value}")

    def _parse_numpy_value(self, value: np.ndarray) -> None:
        """Parse NumPy array color values."""
        if value.shape[-1] < 3:
            raise ValueError(
                f"NumPy array must have at least 3 components, got {value.shape}"
            )

        rgb_values = value.flatten()[:3].astype(int)
        self._rgb = tuple(rgb_values)

        if value.shape[-1] > 3:
            self._alpha = float(value.flatten()[3])

    def _hsl_to_rgb(
        self,
        h: float,
        s: float,
        l: float,  # noqa: E741 -- HSL spec notation for lightness
    ) -> tuple[int, int, int]:
        """Convert HSL to RGB."""
        h = h % 360 / 360.0

        if s == 0:
            r = g = b = l
        else:

            def hue_to_rgb(p: float, q: float, t: float) -> float:
                if t < 0:
                    t += 1
                if t > 1:
                    t -= 1
                if t < 1 / 6:
                    return p + (q - p) * 6 * t
                if t < 1 / 2:
                    return q
                if t < 2 / 3:
                    return p + (q - p) * (2 / 3 - t) * 6
                return p

            q = l * (1 + s) if l < 0.5 else l + s - l * s
            p = 2 * l - q

            r = hue_to_rgb(p, q, h + 1 / 3)
            g = hue_to_rgb(p, q, h)
            b = hue_to_rgb(p, q, h - 1 / 3)

        return (int(r * 255), int(g * 255), int(b * 255))

    def _rgb_to_hsl(self, r: int, g: int, b: int) -> tuple[float, float, float]:
        """Convert RGB to HSL."""
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val

        l = (max_val + min_val) / 2.0  # noqa: E741

        if diff == 0:
            h = s = 0
        else:
            s = diff / (2.0 - max_val - min_val) if l > 0.5 else diff / (max_val + min_val)

            if max_val == r:
                h = ((g - b) / diff + (6 if g < b else 0)) / 6.0
            elif max_val == g:
                h = ((b - r) / diff + 2) / 6.0
            else:
                h = ((r - g) / diff + 4) / 6.0

        return (h * 360, s, l)


__all__ = ["ColorParsingMixin"]
