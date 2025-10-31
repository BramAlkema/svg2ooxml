"""Functional helpers around ``Matrix2D`` for affine transforms."""

from __future__ import annotations

from svg2ooxml.common.geometry.matrix import Matrix2D, parse_transform_list

Matrix = Matrix2D
IDENTITY: Matrix2D = Matrix2D.identity()


def matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> Matrix2D:
    return Matrix2D.from_values(a, b, c, d, e, f)


def translate(tx: float, ty: float = 0.0) -> Matrix2D:
    return Matrix2D.translate(tx, ty)


def scale(sx: float, sy: float | None = None) -> Matrix2D:
    return Matrix2D.scale(sx, sy)


def rotate(angle_deg: float, cx: float | None = None, cy: float | None = None) -> Matrix2D:
    if cx is not None and cy is not None:
        return Matrix2D.rotate(angle_deg, cx, cy)
    return Matrix2D.rotate(angle_deg)


def skew_x(angle_deg: float) -> Matrix2D:
    return Matrix2D.skew_x(angle_deg)


def skew_y(angle_deg: float) -> Matrix2D:
    return Matrix2D.skew_y(angle_deg)


__all__ = [
    "IDENTITY",
    "Matrix",
    "Matrix2D",
    "matrix",
    "parse_transform_list",
    "rotate",
    "scale",
    "skew_x",
    "skew_y",
    "translate",
]
