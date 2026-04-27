"""Bridge helpers for resvg affine matrices and core matrix utilities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.numpy_compat import np

MatrixTuple = tuple[float, float, float, float, float, float]
MatrixBridgeInput = ResvgMatrix | Matrix2D | Sequence[float] | None

IDENTITY_MATRIX_TUPLE: MatrixTuple = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def matrix_to_tuple(matrix: MatrixBridgeInput | Any) -> MatrixTuple:
    """Convert a supported affine matrix representation to SVG tuple order."""

    if matrix is None:
        return IDENTITY_MATRIX_TUPLE
    if isinstance(matrix, Matrix2D):
        return matrix.as_tuple()
    if isinstance(matrix, ResvgMatrix):
        return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
    if all(hasattr(matrix, attr) for attr in ("a", "b", "c", "d", "e", "f")):
        return (
            float(matrix.a),
            float(matrix.b),
            float(matrix.c),
            float(matrix.d),
            float(matrix.e),
            float(matrix.f),
        )
    if isinstance(matrix, Sequence) and not isinstance(matrix, (str, bytes)):
        return _sequence_to_tuple(matrix)
    if hasattr(matrix, "tolist"):
        return _sequence_to_tuple(matrix.tolist())
    raise TypeError(f"Unsupported matrix representation: {type(matrix)!r}")


def matrix_to_matrix2d(matrix: MatrixBridgeInput | Any) -> Matrix2D:
    """Convert a supported affine matrix representation to ``Matrix2D``."""

    return Matrix2D.from_values(*matrix_to_tuple(matrix))


def apply_matrix_to_xy(
    x: float,
    y: float,
    matrix: MatrixBridgeInput | Any,
) -> tuple[float, float]:
    """Apply a supported affine transform to an ``(x, y)`` coordinate."""

    if matrix is None:
        return (x, y)
    if hasattr(matrix, "apply_to_point"):
        return matrix.apply_to_point(x, y)
    if hasattr(matrix, "transform_xy"):
        return matrix.transform_xy(x, y)
    a, b, c, d, e, f = matrix_to_tuple(matrix)
    return (a * x + c * y + e, b * x + d * y + f)


def transform_point(point: Point, matrix: MatrixBridgeInput | Any) -> Point:
    """Apply a supported affine transform to an IR point."""

    x, y = apply_matrix_to_xy(point.x, point.y, matrix)
    return Point(x, y)


def matrix_to_numpy(matrix: MatrixBridgeInput | Any):
    """Convert a supported affine matrix to a 3x3 numpy-compatible array."""

    if matrix is None:
        return None
    a, b, c, d, e, f = matrix_to_tuple(matrix)
    return np.array(
        [
            [a, c, e],
            [b, d, f],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def matrix_tuple_to_string(values: MatrixBridgeInput | Any) -> str | None:
    """Serialize a matrix tuple as an SVG ``matrix(...)`` transform."""

    matrix = matrix_to_tuple(values)
    if matrix == IDENTITY_MATRIX_TUPLE:
        return None
    return (
        "matrix("
        f"{_format_number(matrix[0])} "
        f"{_format_number(matrix[1])} "
        f"{_format_number(matrix[2])} "
        f"{_format_number(matrix[3])} "
        f"{_format_number(matrix[4])} "
        f"{_format_number(matrix[5])}"
        ")"
    )


def matrix_to_string(matrix: MatrixBridgeInput | Any) -> str | None:
    """Serialize a supported affine matrix as an SVG ``matrix(...)`` transform."""

    return matrix_tuple_to_string(matrix)


def parse_matrix_transform(value: str | None) -> MatrixTuple:
    """Parse any SVG transform list into a matrix tuple."""

    if not value:
        return IDENTITY_MATRIX_TUPLE
    try:
        return parse_transform_list(value).as_tuple()
    except (TypeError, ValueError):
        return IDENTITY_MATRIX_TUPLE


def _sequence_to_tuple(value: Sequence[Any]) -> MatrixTuple:
    if len(value) == 6:
        return (
            float(value[0]),
            float(value[1]),
            float(value[2]),
            float(value[3]),
            float(value[4]),
            float(value[5]),
        )
    if len(value) == 3:
        row0 = value[0]
        row1 = value[1]
        row2 = value[2]
        if (
            isinstance(row0, Sequence)
            and isinstance(row1, Sequence)
            and isinstance(row2, Sequence)
            and len(row0) == 3
            and len(row1) == 3
            and len(row2) == 3
        ):
            return (
                float(row0[0]),
                float(row1[0]),
                float(row0[1]),
                float(row1[1]),
                float(row0[2]),
                float(row1[2]),
            )
    raise TypeError(f"Unsupported matrix sequence shape: {value!r}")


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


__all__ = [
    "IDENTITY_MATRIX_TUPLE",
    "MatrixBridgeInput",
    "MatrixTuple",
    "apply_matrix_to_xy",
    "matrix_to_matrix2d",
    "matrix_to_numpy",
    "matrix_to_string",
    "matrix_to_tuple",
    "matrix_tuple_to_string",
    "parse_matrix_transform",
    "transform_point",
]
