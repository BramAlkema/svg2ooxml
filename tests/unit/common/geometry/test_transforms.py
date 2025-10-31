"""Unit tests for the modern geometry transform helpers."""

from __future__ import annotations

import pytest

from svg2ooxml.common.geometry.transforms import (
    CoordinateSpace,
    IDENTITY,
    Matrix,
    parse_transform,
    rotate,
    scale,
    translate,
    decompose_matrix,
)


def test_parse_transform_composes_operations() -> None:
    matrix = parse_transform("translate(10, 20) rotate(90) scale(2)")
    origin = matrix.transform_xy(0, 0)
    x, y = matrix.transform_xy(1, 0)

    assert origin[0] == pytest.approx(10.0)
    assert origin[1] == pytest.approx(20.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(22.0)


def test_identity_matrix_multiplies_cleanly() -> None:
    mat = IDENTITY.multiply(scale(2.0))
    assert mat == scale(2.0)


def test_decompose_matrix_recovers_components() -> None:
    composed = translate(10, -5).multiply(rotate(30)).multiply(scale(2, 3))
    components = decompose_matrix(composed)

    assert components.translation.x == pytest.approx(10.0)
    assert components.translation.y == pytest.approx(-5.0)
    assert components.rotation_deg == pytest.approx(30.0)
    assert components.scale_x == pytest.approx(2.0, rel=1e-6)
    assert components.scale_y == pytest.approx(3.0, rel=1e-6)
    assert abs(components.shear) < 1e-6


def test_matrix_transform_xy() -> None:
    mat = Matrix(2, 0, 0, 3, 4, 5)
    x, y = mat.transform_xy(3, 2)

    assert x == pytest.approx(10.0)
    assert y == pytest.approx(11.0)


def test_parse_transform_invalid_op_raises() -> None:
    with pytest.raises(ValueError):
        parse_transform("invalid(1)")


def test_coordinate_space_pushes_transforms() -> None:
    space = CoordinateSpace()

    space.push(Matrix.translate(10, 5))
    x, y = space.apply_point(0, 0)

    assert x == 10
    assert y == 5

    space.push(Matrix.scale(2))
    x2, y2 = space.apply_point(1, 1)

    assert x2 == 12
    assert y2 == 7

    space.pop()
    x3, y3 = space.apply_point(1, 1)

    assert x3 == 11
    assert y3 == 6


def test_coordinate_space_duplicate_stack_when_none() -> None:
    space = CoordinateSpace()

    space.push(Matrix.translate(2, 3))
    space.push(None)  # Should duplicate current matrix

    x, y = space.apply_point(4, 5)
    assert x == 6
    assert y == 8
