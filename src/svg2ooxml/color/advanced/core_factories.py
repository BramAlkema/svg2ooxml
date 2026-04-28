"""Factory constructors for the advanced Color class."""

from __future__ import annotations

import colorspacious
import numpy as np

from .color_spaces import ColorSpaceConverter


class ColorFactoryMixin:
    """Alternative constructors mixed into the advanced Color class."""

    @classmethod
    def from_lab(cls, l: float, a: float, b: float, alpha: float = 1.0):  # noqa: E741 -- CIE Lab spec notation for lightness
        """
        Create Color from Lab values using colorspacious.

        Args:
            l: Lightness (0-100)
            a: Green-red axis
            b: Blue-yellow axis
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        _validate_alpha(alpha)

        try:
            lab = np.array([l, a, b])
            rgb = colorspacious.cspace_convert(lab, "CIELab", "sRGB255")
            rgb = tuple(max(0, min(255, int(c))) for c in rgb)
            color = cls(rgb)
            color._alpha = alpha
            return color

        except Exception as e:
            raise ValueError(f"Invalid Lab values ({l}, {a}, {b}): {e}") from e

    @classmethod
    def from_lch(cls, l: float, c: float, h: float, alpha: float = 1.0):  # noqa: E741 -- CIE LCH spec notation for lightness
        """
        Create Color from LCH values using colorspacious.

        Args:
            l: Lightness (0-100)
            c: Chroma
            h: Hue angle (0-360)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        _validate_alpha(alpha)

        try:
            lch = np.array([l, c, h])
            rgb = colorspacious.cspace_convert(lch, "CIELCh", "sRGB255")
            rgb = tuple(max(0, min(255, int(c))) for c in rgb)
            color = cls(rgb)
            color._alpha = alpha
            return color

        except Exception as e:
            raise ValueError(f"Invalid LCH values ({l}, {c}, {h}): {e}") from e

    @classmethod
    def from_hsl(cls, h: float, s: float, l: float, alpha: float = 1.0):  # noqa: E741 -- HSL spec notation for lightness
        """
        Create Color from HSL values.

        Args:
            h: Hue angle (0-360)
            s: Saturation (0.0-1.0)
            l: Lightness (0.0-1.0)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        _validate_alpha(alpha)
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"Saturation must be between 0.0 and 1.0, got {s}")
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")

        color = cls((0, 0, 0))
        color._rgb = color._hsl_to_rgb(h, s, l)
        color._alpha = alpha
        return color

    @classmethod
    def from_oklab(cls, l: float, a: float, b: float, alpha: float = 1.0):  # noqa: E741 -- OKLab spec notation for lightness
        """
        Create Color from OKLab values.

        Args:
            l: Lightness (0.0-1.0)
            a: Green-red component
            b: Blue-yellow component
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        _validate_alpha(alpha)
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")

        color = cls((0, 0, 0))
        color._rgb = ColorSpaceConverter.oklab_to_rgb(l, a, b)
        color._alpha = alpha
        return color

    @classmethod
    def from_oklch(cls, l: float, c: float, h: float, alpha: float = 1.0):  # noqa: E741 -- OKLCh spec notation for lightness
        """
        Create Color from OKLCh values.

        Args:
            l: Lightness (0.0-1.0)
            c: Chroma (saturation)
            h: Hue angle in degrees (0-360)
            alpha: Alpha channel (0.0-1.0)

        Returns:
            New Color instance
        """
        _validate_alpha(alpha)
        if not 0.0 <= l <= 1.0:
            raise ValueError(f"Lightness must be between 0.0 and 1.0, got {l}")
        if c < 0.0:
            raise ValueError(f"Chroma must be non-negative, got {c}")

        color = cls((0, 0, 0))
        color._rgb = ColorSpaceConverter.oklch_to_rgb(l, c, h)
        color._alpha = alpha
        return color


def _validate_alpha(alpha: float) -> None:
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")


__all__ = ["ColorFactoryMixin"]
