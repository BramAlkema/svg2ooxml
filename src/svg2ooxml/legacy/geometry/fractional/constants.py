"""Constants for fractional EMU conversions."""

EMU_PER_INCH = 914400
EMU_PER_CM = EMU_PER_INCH / 2.54
EMU_PER_MM = EMU_PER_CM / 10.0
EMU_PER_POINT = EMU_PER_INCH / 72.0
DEFAULT_DPI = 96.0
MIN_EMU_VALUE = -2 ** 47
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
