"""Fractional EMU conversion utilities."""

from .constants import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_POINT,
    MAX_EMU_VALUE,
    MIN_EMU_VALUE,
)
from .converter import FractionalEMUConverter
from .errors import (
    CoordinateValidationError,
    EMUBoundaryError,
    FractionalEMUError,
    PrecisionOverflowError,
)
from .precision import PrecisionMetrics
from .types import PrecisionContext, PrecisionMode

__all__ = [
    "DEFAULT_DPI",
    "EMU_PER_CM",
    "EMU_PER_INCH",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "MIN_EMU_VALUE",
    "MAX_EMU_VALUE",
    "FractionalEMUConverter",
    "FractionalEMUError",
    "CoordinateValidationError",
    "EMUBoundaryError",
    "PrecisionOverflowError",
    "PrecisionMetrics",
    "PrecisionContext",
    "PrecisionMode",
]
