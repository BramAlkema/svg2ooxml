"""Lightweight 2D matrix utilities and SVG transform parsing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import cos, radians, sin

from svg2ooxml.ir.geometry import Point


@dataclass(slots=True)
class Matrix2D:
    """Simple 3x3 matrix representation for 2D transforms."""

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
        """Apply the matrix to an IR point."""
        x = point.x * self.a + point.y * self.c + self.e
        y = point.x * self.b + point.y * self.d + self.f
        return Point(x, y)

    def transform_points(self, points: Iterable[Point | tuple[float, float]]) -> list[Point]:
        """Apply the matrix to an iterable of points."""
        transformed: list[Point] = []
        for item in points:
            if isinstance(item, Point):
                source = item
            else:
                source = Point(float(item[0]), float(item[1]))
            transformed.append(self.transform_point(source))
        return transformed

    def is_identity(self, *, tolerance: float = 1e-9) -> bool:
        """Return True if the matrix is effectively an identity matrix."""
        return (
            abs(self.a - 1.0) <= tolerance
            and abs(self.d - 1.0) <= tolerance
            and abs(self.b) <= tolerance
            and abs(self.c) <= tolerance
            and abs(self.e) <= tolerance
            and abs(self.f) <= tolerance
        )

    @classmethod
    def identity(cls) -> "Matrix2D":
        return cls()

    @classmethod
    def from_transform(cls, name: str, values: Iterable[float]) -> "Matrix2D":
        vals = list(values)
        if name == "matrix" and len(vals) >= 6:
            return cls(*vals[:6])
        if name == "translate":
            tx = vals[0] if vals else 0.0
            ty = vals[1] if len(vals) > 1 else 0.0
            return cls(e=tx, f=ty)
        if name == "scale":
            sx = vals[0] if vals else 1.0
            sy = vals[1] if len(vals) > 1 else sx
            return cls(a=sx, d=sy)
        if name == "rotate":
            angle = radians(vals[0]) if vals else 0.0
            cos_a = cos(angle)
            sin_a = sin(angle)
            if len(vals) > 2:
                cx, cy = vals[1:3]
                return cls(
                    a=cos_a,
                    b=sin_a,
                    c=-sin_a,
                    d=cos_a,
                    e=cx - cx * cos_a + cy * sin_a,
                    f=cy - cx * sin_a - cy * cos_a,
                )
            return cls(a=cos_a, b=sin_a, c=-sin_a, d=cos_a)
        if name == "skewX" and vals:
            angle = radians(vals[0])
            return cls(c=sin(angle))
        if name == "skewY" and vals:
            angle = radians(vals[0])
            return cls(b=sin(angle))
        return cls.identity()


def parse_transform_list(transform: str | None) -> Matrix2D:
    if not transform:
        return Matrix2D.identity()

    current = Matrix2D.identity()
    for name, values in _tokenize_transforms(transform):
        matrix = Matrix2D.from_transform(name, values)
        current = current.multiply(matrix)
    return current


def _tokenize_transforms(transform: str) -> list[tuple[str, list[float]]]:
    tokens: list[tuple[str, list[float]]] = []
    name = ""
    args = ""
    depth = 0
    for char in transform:
        if char.isalpha() or char in {"-", "_"}:
            if depth == 0:
                name += char
            else:
                args += char
        elif char == "(":
            depth += 1
            if depth == 1:
                continue
            args += char
        elif char == ")":
            depth -= 1
            if depth == 0:
                tokens.append((name.strip(), _parse_floats(args)))
                name = ""
                args = ""
            else:
                args += char
        else:
            args += char
    return tokens


def _parse_floats(text: str) -> list[float]:
    cleaned = text.replace(",", " ")
    parts = cleaned.split()
    values: list[float] = []
    for part in parts:
        try:
            values.append(float(part))
        except ValueError:
            continue
    return values


__all__ = ["Matrix2D", "parse_transform_list"]
