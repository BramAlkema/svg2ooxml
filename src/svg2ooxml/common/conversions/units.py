"""Unit conversion utilities - re-export from common.units.

This module provides a convenient import path for unit conversion utilities
that are implemented in svg2ooxml.common.units.
"""

from svg2ooxml.common.units.conversion import (
    ConversionContext,
    UnitConverter,
    emu_to_px,
    emu_to_unit,
    px_to_emu,
)
from svg2ooxml.common.units.scalars import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_PICA,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
    EMU_PER_Q,
)

__all__ = [
    "UnitConverter",
    "px_to_emu",
    "emu_to_px",
    "emu_to_unit",
    "ConversionContext",
    "DEFAULT_DPI",
    "EMU_PER_INCH",
    "EMU_PER_CM",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "EMU_PER_PICA",
    "EMU_PER_Q",
]
