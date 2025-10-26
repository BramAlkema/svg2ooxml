"""Exception types for fractional EMU conversion."""


class FractionalEMUError(ValueError):
    """Base error for fractional EMU issues."""


class CoordinateValidationError(FractionalEMUError):
    """Raised when incoming coordinates are invalid."""


class PrecisionOverflowError(FractionalEMUError):
    """Raised when precision mode would overflow bounds."""


class EMUBoundaryError(FractionalEMUError):
    """Raised when converted EMU values leave the allowed range."""


__all__ = [
    "FractionalEMUError",
    "CoordinateValidationError",
    "PrecisionOverflowError",
    "EMUBoundaryError",
]
