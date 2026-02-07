"""OKLab/OKLCh colour space helpers ported from svg2pptx."""

from __future__ import annotations

from math import atan2, cos, degrees, radians, sin

__all__ = [
    "rgb_to_oklab",
    "oklab_to_rgb",
    "oklab_to_oklch",
    "oklch_to_oklab",
    "rgb_to_oklch",
    "oklch_to_rgb",
]


def _srgb_to_linear(component: float) -> float:
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(component: float) -> float:
    if component <= 0.0031308:
        return 12.92 * component
    return 1.055 * (component ** (1.0 / 2.4)) - 0.055


def _cbrt(value: float) -> float:
    return value ** (1.0 / 3.0) if value >= 0 else -((-value) ** (1.0 / 3.0))


def rgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert sRGB components (0-1) to OKLab."""

    r_lin = _srgb_to_linear(r)
    g_lin = _srgb_to_linear(g)
    b_lin = _srgb_to_linear(b)

    l = 0.4122214708 * r_lin + 0.5363325363 * g_lin + 0.0514459929 * b_lin  # noqa: E741 -- OKLab spec notation for lightness
    m = 0.2119034982 * r_lin + 0.6806995451 * g_lin + 0.1073969566 * b_lin
    s = 0.0883024619 * r_lin + 0.2817188376 * g_lin + 0.6299787005 * b_lin

    l_ = _cbrt(l)
    m_ = _cbrt(m)
    s_ = _cbrt(s)

    ok_l = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    ok_a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    ok_b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return ok_l, ok_a, ok_b


def oklab_to_rgb(l: float, a: float, b: float) -> tuple[float, float, float]:  # noqa: E741 -- OKLab spec notation for lightness
    """Convert OKLab components back to sRGB (0-1)."""

    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b

    l_lin = l_ ** 3
    m_lin = m_ ** 3
    s_lin = s_ ** 3

    r_lin = +4.0767416621 * l_lin - 3.3077115913 * m_lin + 0.2309699292 * s_lin
    g_lin = -1.2684380046 * l_lin + 2.6097574011 * m_lin - 0.3413193965 * s_lin
    b_lin = -0.0041960863 * l_lin - 0.7034186147 * m_lin + 1.7076147010 * s_lin

    r = _linear_to_srgb(r_lin)
    g = _linear_to_srgb(g_lin)
    b = _linear_to_srgb(b_lin)
    return _clamp(r), _clamp(g), _clamp(b)


def oklab_to_oklch(l: float, a: float, b: float) -> tuple[float, float, float]:  # noqa: E741 -- OKLab spec notation for lightness
    """Convert OKLab to cylindrical OKLCh."""

    c = (a * a + b * b) ** 0.5
    h = degrees(atan2(b, a))
    if h < 0:
        h += 360.0
    return l, c, h


def oklch_to_oklab(l: float, c: float, h_degrees: float) -> tuple[float, float, float]:  # noqa: E741 -- OKLCh spec notation for lightness
    """Convert OKLCh back to OKLab."""

    h_rad = radians(h_degrees)
    a = c * cos(h_rad)
    b = c * sin(h_rad)
    return l, a, b


def rgb_to_oklch(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convenience conversion from sRGB to OKLCh."""

    return oklab_to_oklch(*rgb_to_oklab(r, g, b))


def oklch_to_rgb(l: float, c: float, h_degrees: float) -> tuple[float, float, float]:  # noqa: E741 -- OKLCh spec notation for lightness
    """Convenience conversion from OKLCh to sRGB."""

    return oklab_to_rgb(*oklch_to_oklab(l, c, h_degrees))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
