from __future__ import annotations

import pytest

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    apply_matrix_to_xy,
    matrix_to_matrix2d,
    matrix_to_numpy,
    matrix_to_string,
    matrix_to_tuple,
    matrix_tuple_to_string,
    parse_matrix_transform,
    transform_point,
)
from svg2ooxml.ir.geometry import Point


def test_matrix_to_tuple_accepts_resvg_and_matrix2d() -> None:
    matrix = Matrix(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)

    assert matrix_to_tuple(matrix) == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert matrix_to_tuple(Matrix2D.from_values(1, 2, 3, 4, 5, 6)) == (
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
    )


def test_matrix_to_matrix2d_preserves_svg_affine_order() -> None:
    matrix = matrix_to_matrix2d(Matrix(1.0, 0.0, 0.0, 1.0, 10.0, 20.0))

    assert matrix.transform_xy(2.0, 3.0) == (12.0, 23.0)


def test_apply_matrix_to_xy_and_point_use_svg_semantics() -> None:
    matrix = Matrix(2.0, 0.0, 0.0, 3.0, 10.0, 20.0)

    assert apply_matrix_to_xy(2.0, 3.0, matrix) == (14.0, 29.0)
    assert transform_point(Point(2.0, 3.0), matrix) == Point(14.0, 29.0)


def test_parse_matrix_transform_accepts_full_svg_transform_lists() -> None:
    value = "translate(10 20) scale(2)"

    assert parse_matrix_transform(value) == pytest.approx(parse_transform_list(value).as_tuple())


def test_matrix_to_string_suppresses_identity() -> None:
    assert matrix_tuple_to_string((1.0, 0.0, 0.0, 1.0, 0.0, 0.0)) is None
    assert matrix_to_string(Matrix(1.0, 0.0, 0.0, 1.0, 10.0, 20.0)) == (
        "matrix(1 0 0 1 10 20)"
    )


def test_matrix_to_numpy_returns_svg_affine_array() -> None:
    array = matrix_to_numpy(Matrix(1.0, 2.0, 3.0, 4.0, 5.0, 6.0))

    assert array is not None
    assert array.shape == (3, 3)
    assert array[0, 0] == 1.0
    assert array[0, 1] == 3.0
    assert array[0, 2] == 5.0
    assert array[1, 0] == 2.0
    assert array[1, 1] == 4.0
    assert array[1, 2] == 6.0
    assert matrix_to_numpy(None) is None
