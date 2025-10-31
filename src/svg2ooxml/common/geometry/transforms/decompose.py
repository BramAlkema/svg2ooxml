"""Affine transform decomposition utilities."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin, sqrt

from svg2ooxml.common.geometry.matrix import Matrix2D
from svg2ooxml.ir.geometry import Point


@dataclass
class DecomposedTransform:
    translation: Point
    rotation_deg: float
    scale_x: float
    scale_y: float
    shear: float


def decompose_matrix(matrix: Matrix2D) -> DecomposedTransform:
    determinant = matrix.a * matrix.d - matrix.b * matrix.c
    if determinant == 0:
        raise ValueError("Matrix is not invertible, cannot decompose")

    scale_x = sqrt(matrix.a ** 2 + matrix.b ** 2)
    rotation = atan2(matrix.b, matrix.a)

    shear = (matrix.a * matrix.c + matrix.b * matrix.d) / max(scale_x ** 2, 1e-12)
    scale_y = sqrt((matrix.c ** 2 + matrix.d ** 2) - shear ** 2 * scale_x ** 2)

    return DecomposedTransform(
        translation=Point(matrix.e, matrix.f),
        rotation_deg=rotation * 180.0 / 3.141592653589793,
        scale_x=scale_x,
        scale_y=scale_y,
        shear=shear,
    )


def compose_matrix(transform: DecomposedTransform) -> Matrix2D:
    angle = transform.rotation_deg * 3.141592653589793 / 180.0
    cos_a = cos(angle)
    sin_a = sin(angle)

    a = cos_a * transform.scale_x
    b = sin_a * transform.scale_x
    c = -sin_a * transform.scale_y + transform.shear * cos_a * transform.scale_x
    d = cos_a * transform.scale_y + transform.shear * sin_a * transform.scale_x

    return Matrix2D(a=a, b=b, c=c, d=d, e=transform.translation.x, f=transform.translation.y)


__all__ = ["DecomposedTransform", "decompose_matrix", "compose_matrix"]
