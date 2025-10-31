"""Lightweight NumPy compatibility helpers for IR."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

try:  # pragma: no cover - real numpy branch exercised in integration
    import numpy as _np

    NUMPY_AVAILABLE = True

    np = _np  # re-export for callers that expect numpy-like API

    def matmul(a, b):
        return _np.matmul(a, b)

    sqrt = _np.sqrt
except ImportError:  # pragma: no cover - fallback is simple deterministic code
    NUMPY_AVAILABLE = False

    class _DummyNumpy:
        """Minimal numpy shim used when numpy is unavailable."""

        ndarray = tuple

        @staticmethod
        def array(data: Iterable[float], dtype=None):
            items = list(data)
            if not items:
                return tuple()
            first = items[0]
            if isinstance(first, (list, tuple)):
                return tuple(_DummyNumpy.array(item, dtype=dtype) for item in items)
            return tuple(float(x) for x in items)

        @staticmethod
        def identity(n: int):
            return tuple(
                tuple(1.0 if i == j else 0.0 for j in range(n))
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
                result.append(sum(float(r) * float(c) for r, c in zip(row, vector)))
            return tuple(result)

        raise TypeError("Fallback matmul expects 2-D matrix and 1-D vector")

    def sqrt(value: float) -> float:
        return math.sqrt(float(value))


__all__ = ["np", "NUMPY_AVAILABLE", "matmul", "sqrt"]
