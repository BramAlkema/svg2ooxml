"""Numeric constants used by the unit conversion layer."""

from __future__ import annotations

EMU_PER_INCH: int = 914_400
PX_PER_INCH: float = 96.0
DEFAULT_DPI: float = PX_PER_INCH

EMU_PER_CM: float = EMU_PER_INCH / 2.54
EMU_PER_MM: float = EMU_PER_CM / 10.0
EMU_PER_Q: float = EMU_PER_MM / 4.0  # Q is a quarter millimetre.
EMU_PER_POINT: float = EMU_PER_INCH / 72.0
EMU_PER_PICA: float = EMU_PER_POINT * 12.0

EMU_PER_PX_AT_DEFAULT_DPI: float = EMU_PER_INCH / PX_PER_INCH

__all__ = [
    "DEFAULT_DPI",
    "EMU_PER_CM",
    "EMU_PER_INCH",
    "EMU_PER_MM",
    "EMU_PER_PICA",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "EMU_PER_Q",
    "PX_PER_INCH",
]
