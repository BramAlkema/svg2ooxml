"""Affine matrix helpers shared across the svg2ooxml pipeline."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Matrix:
    """Immutable 2D affine transformation matrix.

    The matrix is represented using the SVG convention:

        [a c e]
        [b d f]
        [0 0 1]

    Instances are immutable – composition produces new matrices, making the
    class safe to share across threads and functional pipelines.
    """

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    # ------------------------------------------------------------------ #
    # Constructors                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def identity(cls) -> "Matrix":
        return cls()

    @classmethod
    def from_values(
        cls,
        a: float,
        b: float,
        c: float,
        d: float,
        e: float,
        f: float,
    ) -> "Matrix":
        return cls(a, b, c, d, e, f)

    @classmethod
    def translate(cls, tx: float, ty: float = 0.0) -> "Matrix":
        return cls(1.0, 0.0, 0.0, 1.0, tx, ty)

    @classmethod
    def scale(cls, sx: float, sy: float | None = None) -> "Matrix":
        return cls(sx, 0.0, 0.0, sy if sy is not None else sx, 0.0, 0.0)

    @classmethod
    def rotate(cls, angle_degrees: float, cx: float | None = None, cy: float | None = None) -> "Matrix":
        radians = math.radians(angle_degrees)
        cos_a = math.cos(radians)
        sin_a = math.sin(radians)
        base = cls(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
        if cx is None or cy is None:
            return base
        return cls.translate(cx, cy).multiply(base).multiply(cls.translate(-cx, -cy))

    @classmethod
    def skew_x(cls, angle_degrees: float) -> "Matrix":
        return cls(1.0, 0.0, math.tan(math.radians(angle_degrees)), 1.0, 0.0, 0.0)

    @classmethod
    def skew_y(cls, angle_degrees: float) -> "Matrix":
        return cls(1.0, math.tan(math.radians(angle_degrees)), 0.0, 1.0, 0.0, 0.0)

    # ------------------------------------------------------------------ #
    # Composition & inspection                                           #
    # ------------------------------------------------------------------ #

    def multiply(self, other: "Matrix") -> "Matrix":
        return Matrix(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def __matmul__(self, other: "Matrix") -> "Matrix":
        return self.multiply(other)

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> "Matrix":
        det = self.determinant()
        if abs(det) < 1e-12:
            raise ValueError("Matrix is not invertible")
        inv_det = 1.0 / det
        a = self.d * inv_det
        b = -self.b * inv_det
        c = -self.c * inv_det
        d = self.a * inv_det
        e = -(a * self.e + c * self.f)
        f = -(b * self.e + d * self.f)
        return Matrix(a, b, c, d, e, f)

    def is_identity(self, *, tol: float = 1e-9) -> bool:
        return (
            math.isclose(self.a, 1.0, abs_tol=tol)
            and math.isclose(self.d, 1.0, abs_tol=tol)
            and math.isclose(self.b, 0.0, abs_tol=tol)
            and math.isclose(self.c, 0.0, abs_tol=tol)
            and math.isclose(self.e, 0.0, abs_tol=tol)
            and math.isclose(self.f, 0.0, abs_tol=tol)
        )

    # ------------------------------------------------------------------ #
    # Geometry helpers                                                   #
    # ------------------------------------------------------------------ #

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def transform_points(self, points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
        return [self.transform_point(x, y) for x, y in points]

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return self.a, self.b, self.c, self.d, self.e, self.f


IDENTITY = Matrix.identity()


def matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> Matrix:
    return Matrix.from_values(a, b, c, d, e, f)


def translate(tx: float, ty: float = 0.0) -> Matrix:
    return Matrix.translate(tx, ty)


def scale(sx: float, sy: float | None = None) -> Matrix:
    return Matrix.scale(sx, sy)


def rotate(angle_degrees: float) -> Matrix:
    return Matrix.rotate(angle_degrees)


def skew_x(angle_degrees: float) -> Matrix:
    return Matrix.skew_x(angle_degrees)


def skew_y(angle_degrees: float) -> Matrix:
    return Matrix.skew_y(angle_degrees)


__all__ = [
    "IDENTITY",
    "Matrix",
    "matrix",
    "rotate",
    "scale",
    "skew_x",
    "skew_y",
    "translate",
]
