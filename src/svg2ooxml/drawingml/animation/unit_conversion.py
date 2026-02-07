"""Centralized unit conversion for PowerPoint animation generation.

All SVG-to-PowerPoint animation unit conversions live here. Handlers call
these methods instead of scattering inline ``int(round(... * 100000))``
conversions across their ``build()`` methods.
"""

from __future__ import annotations

from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.conversions.scale import scale_to_ppt as _scale_to_ppt
from svg2ooxml.common.units import UnitConverter

from .constants import ANGLE_ATTRIBUTES, AXIS_MAP

__all__ = [
    "AnimationUnitConverter",
    "PPT_ANGLE_FACTOR",
    "PPT_OPACITY_FACTOR",
    "PPT_SCALE_FACTOR",
]

# Named constants for the magic multipliers used throughout animation code.
PPT_ANGLE_FACTOR: int = 60_000
"""Degrees → 60 000ths of a degree (ECMA-376 §19.5.1)."""

PPT_OPACITY_FACTOR: int = 100_000
"""0.0–1.0 → 0–100 000 (ECMA-376 §20.1.2.2.27)."""

PPT_SCALE_FACTOR: int = 100_000
"""1.0 = 100 % → 100 000 (ECMA-376 §19.5.72)."""

# Standard slide dimensions (EMU).
DEFAULT_SLIDE_WIDTH_EMU: int = 9_144_000
DEFAULT_SLIDE_HEIGHT_EMU: int = 6_858_000


class AnimationUnitConverter:
    """All SVG-to-PPT animation unit conversions in one place.

    This replaces the scattered conversion logic previously spread across
    ``ValueProcessor``, ``value_formatters``, and inline handler code.
    """

    def __init__(
        self,
        slide_width_emu: int = DEFAULT_SLIDE_WIDTH_EMU,
        slide_height_emu: int = DEFAULT_SLIDE_HEIGHT_EMU,
        dpi: float = 96.0,
    ) -> None:
        self._slide_w = slide_width_emu
        self._slide_h = slide_height_emu
        self._uc = UnitConverter(dpi=dpi)

    # ------------------------------------------------------------------ #
    # Primitive conversions                                               #
    # ------------------------------------------------------------------ #

    def opacity_to_ppt(self, value: float) -> int:
        """SVG 0.0–1.0 → PPT 0–100 000."""
        clamped = max(0.0, min(1.0, value))
        return opacity_to_ppt(clamped)

    def degrees_to_ppt(self, degrees: float) -> int:
        """Degrees → PPT 60 000ths of a degree."""
        return degrees_to_ppt(degrees)

    def px_to_emu(self, px: float, *, axis: str | None = None) -> int:
        """Pixels → EMU (integer)."""
        return int(round(self._uc.to_emu(px, axis=axis)))

    def scale_to_ppt(self, factor: float) -> int:
        """Scale factor (1.0 = 100 %) → PPT 100 000."""
        return _scale_to_ppt(factor)

    # ------------------------------------------------------------------ #
    # Slide-relative conversions                                          #
    # ------------------------------------------------------------------ #

    def px_to_slide_fraction(self, px: float, *, axis: str) -> float:
        """Pixels → fraction of slide dimension (for motion paths)."""
        emu = self._uc.to_emu(px, axis=axis)
        dim = self._slide_w if axis in ("x", "width") else self._slide_h
        return emu / dim

    # ------------------------------------------------------------------ #
    # Attribute-aware dispatch                                            #
    # ------------------------------------------------------------------ #

    def normalize_attribute_value(self, ppt_attribute: str, raw_value: str) -> str:
        """Normalize a raw numeric value based on its PPT attribute name.

        Angles are converted to 60 000ths; positional/size attributes to EMU.
        Falls back to returning *raw_value* unchanged if it cannot be parsed.
        """
        try:
            numeric = float(raw_value)
        except (ValueError, TypeError):
            return raw_value

        if ppt_attribute in ANGLE_ATTRIBUTES:
            return str(self.degrees_to_ppt(numeric))

        axis = AXIS_MAP.get(ppt_attribute)
        return str(self.px_to_emu(numeric, axis=axis))
