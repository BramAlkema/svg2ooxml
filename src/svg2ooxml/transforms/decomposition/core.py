"""Matrix decomposition helpers used by policy and geometry layers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..matrix import Matrix


@dataclass(slots=True, frozen=True)
class MatrixComponents:
    translate_x: float
    translate_y: float
    scale_x: float
    scale_y: float
    rotation: float
    skew_x: float

    def as_dict(self) -> dict[str, float]:
        return {
            "translate_x": self.translate_x,
            "translate_y": self.translate_y,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation": self.rotation,
            "skew_x": self.skew_x,
        }


def decompose_matrix(matrix: Matrix) -> MatrixComponents:
    a, b, c, d, e, f = matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f

    translate_x, translate_y = e, f

    scale_x = math.hypot(a, b)
    if scale_x == 0:
        # Degenerate; treat as pure shear on Y.
        rotation = 0.0
        skew_x = math.degrees(math.atan2(c, d))
        scale_y = math.hypot(c, d)
        return MatrixComponents(translate_x, translate_y, scale_x, scale_y, rotation, skew_x)

    a_norm = a / scale_x
    b_norm = b / scale_x

    skew = a_norm * c + b_norm * d
    c_prime = c - a_norm * skew
    d_prime = d - b_norm * skew
    scale_y = math.hypot(c_prime, d_prime)

    if scale_y != 0:
        skew /= scale_y
    else:
        skew = 0.0

    determinant = a * d - b * c
    if determinant < 0:
        if scale_x < scale_y:
            scale_x = -scale_x
        else:
            scale_y = -scale_y

    rotation = math.degrees(math.atan2(b_norm, a_norm))
    skew_x = math.degrees(math.atan(skew))

    return MatrixComponents(translate_x, translate_y, scale_x, scale_y, rotation, skew_x)


__all__ = ["MatrixComponents", "decompose_matrix"]
