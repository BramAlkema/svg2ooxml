"""Compatibility wrapper for the centralized NumPy gateway."""

from __future__ import annotations

from svg2ooxml.common.numpy_compat import (
    NUMPY_AVAILABLE,
    REAL_NUMPY,
    matmul,
    np,
    require_numpy,
    sqrt,
)

__all__ = [
    "NUMPY_AVAILABLE",
    "REAL_NUMPY",
    "matmul",
    "np",
    "require_numpy",
    "sqrt",
]
