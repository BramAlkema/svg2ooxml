"""Color science comparison helpers for advanced colors."""

from __future__ import annotations

import colorspacious
import numpy as np


class ColorScienceMixin:
    """Color science methods mixed into the advanced Color class."""

    def delta_e(self, other, method: str = "cie2000") -> float:
        """
        Calculate color difference using Delta E algorithms.

        Args:
            other: Color to compare with
            method: Delta E method ('cie76', 'cie94', 'cie2000')

        Returns:
            Delta E value (lower = more similar)
        """
        if not isinstance(other, self.__class__):
            raise TypeError("other must be a Color instance")

        try:
            color1_lab = colorspacious.cspace_convert(self._rgb, "sRGB255", "CIELab")
            color2_lab = colorspacious.cspace_convert(other._rgb, "sRGB255", "CIELab")

            if method.lower() == "cie76":
                return float(
                    np.sqrt(
                        sum(
                            (a - b) ** 2
                            for a, b in zip(color1_lab, color2_lab, strict=True)
                        )
                    )
                )

            if method.lower() == "cie2000":
                return colorspacious.delta_E(
                    color1_lab,
                    color2_lab,
                    input_space="CIELab",
                    uniform_space="CAM02-UCS",
                )

            raise ValueError(f"Unsupported Delta E method: {method}")

        except Exception:
            rgb_diff = sum(
                (a - b) ** 2 for a, b in zip(self._rgb, other._rgb, strict=True)
            )
            return float(np.sqrt(rgb_diff) / np.sqrt(3 * 255 * 255) * 100)


__all__ = ["ColorScienceMixin"]
