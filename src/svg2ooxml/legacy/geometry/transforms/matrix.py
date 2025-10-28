"""Matrix helpers for geometry transforms."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin

from svg2ooxml.ir.geometry import Point


@dataclass(slots=True)
class Matrix2D:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def multiply(self, other: "Matrix2D") -> "Matrix2D":
        return Matrix2D(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def transform_point(self, point: Point) -> Point:
        return Point(
            point.x * self.a + point.y * self.c + self.e,
            point.x * self.b + point.y * self.d + self.f,
        )

    @classmethod
    def identity(cls) -> "Matrix2D":
        return cls()

    @classmethod
    def translation(cls, tx: float, ty: float) -> "Matrix2D":
        return cls(e=tx, f=ty)

    @classmethod
    def scale(cls, sx: float, sy: float | None = None) -> "Matrix2D":
        sy = sy if sy is not None else sx
        return cls(a=sx, d=sy)

    @classmethod
    def rotation(cls, angle_deg: float, cx: float = 0.0, cy: float = 0.0) -> "Matrix2D":
        angle = radians(angle_deg)
        cos_a = cos(angle)
        sin_a = sin(angle)
        return cls(
            a=cos_a,
            b=sin_a,
            c=-sin_a,
            d=cos_a,
            e=cx - cx * cos_a + cy * sin_a,
            f=cy - cx * sin_a - cy * cos_a,
        )

    @classmethod
    def skew_x(cls, angle_deg: float) -> "Matrix2D":
        return cls(c=sin(radians(angle_deg)))

    @classmethod
    def skew_y(cls, angle_deg: float) -> "Matrix2D":
        return cls(b=sin(radians(angle_deg)))


__all__ = ["Matrix2D"]
