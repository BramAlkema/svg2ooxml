"""Constants for fractional EMU conversions."""

from svg2ooxml.common.units.scalars import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_POINT,
)

MIN_EMU_VALUE = -(2 ** 47)
MAX_EMU_VALUE = 2 ** 47

__all__ = [
    "EMU_PER_INCH",
    "EMU_PER_CM",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "DEFAULT_DPI",
    "MIN_EMU_VALUE",
    "MAX_EMU_VALUE",
]
