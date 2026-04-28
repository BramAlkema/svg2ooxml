"""Central NumPy gateway and lightweight fallback helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

try:  # pragma: no cover - real NumPy branch is exercised in optional lanes
    import numpy as _np
except ImportError:  # pragma: no cover - fallback is deterministic
    _np = None  # type: ignore[assignment]

NUMPY_AVAILABLE = _np is not None
REAL_NUMPY = _np


class _DummyArray(tuple):
    """Tuple subclass that supports a small NumPy-like matrix API."""

    @property
    def shape(self):
        if self and isinstance(self[0], tuple):
            return (len(self), len(self[0]))
        return (len(self),)

    def __getitem__(self, key):
        if isinstance(key, tuple) and len(key) == 2:
            row, col = key
            return super().__getitem__(row)[col]
        return super().__getitem__(key)

    def tolist(self):
        return [list(row) if isinstance(row, tuple) else row for row in self]


class _DummyNumpy:
    """Minimal NumPy shim used when NumPy is unavailable."""

    ndarray = tuple
    float64 = float

    @staticmethod
    def array(data: Iterable[float], dtype=None):
        items = list(data)
        if not items:
            return _DummyArray()
        first = items[0]
        if isinstance(first, (list, tuple)):
            return _DummyArray(
                _DummyArray(float(x) for x in item) for item in items
            )
        return _DummyArray(float(x) for x in items)

    @staticmethod
    def identity(n: int):
        return _DummyArray(
            _DummyArray(1.0 if i == j else 0.0 for j in range(n)) for i in range(n)
        )


np = _np if _np is not None else _DummyNumpy()


def require_numpy(message: str | None = None) -> Any:
    """Return real NumPy or raise a consistent optional-dependency error."""

    if _np is not None:
        return _np
    raise RuntimeError(
        message
        or "NumPy is required for this operation; install an extra that provides it."
    )


def matmul(a, b):
    """Matrix/vector multiplication with a small fallback for affine IR math."""

    if _np is not None:
        return _np.matmul(a, b)

    if isinstance(b, (list, tuple)):
        vector = tuple(float(x) for x in b)
    else:
        raise TypeError("Fallback matmul expects sequence operands")

    if isinstance(a, (list, tuple)) and a and isinstance(a[0], (list, tuple)):
        result = []
        for row in a:
            result.append(
                sum(float(r) * float(c) for r, c in zip(row, vector, strict=True))
            )
        return tuple(result)

    raise TypeError("Fallback matmul expects 2-D matrix and 1-D vector")


def sqrt(value: float) -> float:
    if _np is not None:
        return _np.sqrt(value)
    return math.sqrt(float(value))


__all__ = [
    "NUMPY_AVAILABLE",
    "REAL_NUMPY",
    "matmul",
    "np",
    "require_numpy",
    "sqrt",
]
