"""Fractional EMU converter used by geometry modules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .constants import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_POINT,
    MAX_EMU_VALUE,
    MIN_EMU_VALUE,
)
from .errors import EMUBoundaryError
from .types import PrecisionMode


@dataclass(slots=True)
class FractionalEMUConverter:
    """Lightweight float-preserving EMU converter."""

    precision_mode: PrecisionMode = PrecisionMode.STANDARD
    dpi: float = DEFAULT_DPI
    validate_bounds: bool = True

    _scale: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "_scale", float(self.precision_mode.value))

    def pixels_to_emu(self, pixels: float, dpi: float | None = None) -> float:
        dpi = dpi or self.dpi
        emu = (pixels / dpi) * EMU_PER_INCH
        return self._validate(emu, pixels)

    def points_to_emu(self, points: float) -> float:
        emu = points * EMU_PER_POINT
        return self._validate(emu, points)

    def mm_to_emu(self, millimetres: float) -> float:
        emu = millimetres * EMU_PER_MM
        return self._validate(emu, millimetres)

    def cm_to_emu(self, centimetres: float) -> float:
        emu = centimetres * EMU_PER_CM
        return self._validate(emu, centimetres)

    def inches_to_emu(self, inches: float) -> float:
        emu = inches * EMU_PER_INCH
        return self._validate(emu, inches)

    def round_emu(self, emu: float) -> int:
        quantised = Decimal(emu * self._scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(quantised / Decimal(self._scale))

    def _validate(self, emu: float, value: float) -> float:
        if self.validate_bounds and not (MIN_EMU_VALUE <= emu <= MAX_EMU_VALUE):
            raise EMUBoundaryError(f"EMU value {emu} derived from {value} is out of bounds")
        return emu


__all__ = ["FractionalEMUConverter"]
