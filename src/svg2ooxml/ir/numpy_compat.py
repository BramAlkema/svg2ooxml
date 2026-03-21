"""Lightweight NumPy compatibility helpers for IR."""

from __future__ import annotations

import math
from collections.abc import Iterable

try:  # pragma: no cover - real numpy branch exercised in integration
    import numpy as _np

    NUMPY_AVAILABLE = True

    np = _np  # re-export for callers that expect numpy-like API

    def matmul(a, b):
        return _np.matmul(a, b)

    sqrt = _np.sqrt
except ImportError:  # pragma: no cover - fallback is simple deterministic code
    NUMPY_AVAILABLE = False

    class _DummyArray(tuple):
        """Tuple subclass that supports numpy-like .shape, [row,col], and .tolist()."""

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
        """Minimal numpy shim used when numpy is unavailable."""

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
                _DummyArray(1.0 if i == j else 0.0 for j in range(n))
                for i in range(n)
            )

    np = _DummyNumpy()

    def matmul(a, b):
        """Matrix/vector multiplication for the fallback shim."""
        if isinstance(b, (list, tuple)):
            vector = tuple(float(x) for x in b)
        else:
            raise TypeError("Fallback matmul expects sequence operands")

        if isinstance(a, (list, tuple)) and a and isinstance(a[0], (list, tuple)):
            result = []
            for row in a:
                result.append(sum(float(r) * float(c) for r, c in zip(row, vector, strict=True)))
            return tuple(result)

        raise TypeError("Fallback matmul expects 2-D matrix and 1-D vector")

    def sqrt(value: float) -> float:
        return math.sqrt(float(value))


__all__ = ["np", "NUMPY_AVAILABLE", "matmul", "sqrt"]
