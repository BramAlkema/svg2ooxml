"""Tests for geometry helpers."""

from math import isclose

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list


def test_matrix_multiply_composes_transforms() -> None:
    translate = Matrix2D.from_transform("translate", [10, 5])
    scale = Matrix2D.from_transform("scale", [2])

    combined = translate.multiply(scale)

    assert combined.a == 2
    assert combined.d == 2
    assert combined.e == 10
    assert combined.f == 5


def test_parse_transform_list_handles_multiple_entries() -> None:
    matrix = parse_transform_list("translate(10,5) rotate(90)")

    assert isclose(matrix.a, 0.0, abs_tol=1e-6)
    assert isclose(matrix.b, 1.0, abs_tol=1e-6)
    assert isclose(matrix.c, -1.0, abs_tol=1e-6)
    assert isclose(matrix.d, 0.0, abs_tol=1e-6)
    assert isclose(matrix.e, 10.0, abs_tol=1e-6)
    assert isclose(matrix.f, 5.0, abs_tol=1e-6)


def test_parse_transform_list_defaults_to_identity() -> None:
    matrix = parse_transform_list(None)

    assert matrix == Matrix2D.identity()
