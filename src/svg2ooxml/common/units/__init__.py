"""Shared unit conversion utilities for svg2ooxml."""

from .conversion import (
    ConversionContext,
    UnitConverter,
    emu_to_px,
    emu_to_unit,
    px_to_emu,
)
from .scalars import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_PICA,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
    EMU_PER_Q,
    PX_PER_INCH,
)

__all__ = [
    "ConversionContext",
    "UnitConverter",
    "px_to_emu",
    "emu_to_px",
    "emu_to_unit",
    "DEFAULT_DPI",
    "EMU_PER_INCH",
    "EMU_PER_CM",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "EMU_PER_PICA",
    "EMU_PER_Q",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "PX_PER_INCH",
]
