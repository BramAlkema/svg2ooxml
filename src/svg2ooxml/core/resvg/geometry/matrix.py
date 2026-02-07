"""Affine transform helper matching SVG matrix semantics."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from ..parser.presentation import TransformCommand


@dataclass(frozen=True)
class Matrix:
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @classmethod
    def identity(cls) -> Matrix:
        return cls(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def multiply(self, other: Matrix) -> Matrix:
        return Matrix(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def apply_to_point(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)


def _matrix_from_command(command: TransformCommand) -> Matrix:
    name = command.name.lower()
    values = command.values

    if name == "matrix" and len(values) == 6:
        return Matrix(*values)
    if name == "translate":
        tx = values[0] if len(values) >= 1 else 0.0
        ty = values[1] if len(values) >= 2 else 0.0
        return Matrix(1.0, 0.0, 0.0, 1.0, tx, ty)
    if name == "scale":
        sx = values[0] if len(values) >= 1 else 1.0
        sy = values[1] if len(values) >= 2 else sx
        return Matrix(sx, 0.0, 0.0, sy, 0.0, 0.0)
    if name == "rotate":
        angle = math.radians(values[0] if values else 0.0)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        if len(values) >= 3:
            cx, cy = values[1], values[2]
            return (
                Matrix(1.0, 0.0, 0.0, 1.0, cx, cy)
                .multiply(Matrix(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0))
                .multiply(Matrix(1.0, 0.0, 0.0, 1.0, -cx, -cy))
            )
        return Matrix(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
    if name == "skewx" and values:
        angle = math.tan(math.radians(values[0]))
        return Matrix(1.0, 0.0, angle, 1.0, 0.0, 0.0)
    if name == "skewy" and values:
        angle = math.tan(math.radians(values[0]))
        return Matrix(1.0, angle, 0.0, 1.0, 0.0, 0.0)
    return Matrix.identity()


def matrix_from_commands(commands: Iterable[TransformCommand] | None) -> Matrix:
    matrix = Matrix.identity()
    if not commands:
        return matrix
    for command in commands:
        matrix = matrix.multiply(_matrix_from_command(command))
    return matrix
