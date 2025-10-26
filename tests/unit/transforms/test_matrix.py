"""Tests for affine transform helpers."""

import pytest

from svg2ooxml.transforms import (
    IDENTITY,
    Matrix,
    parse_transform,
    rotate,
    scale,
    translate,
)
from svg2ooxml.transforms.decomposition import decompose_matrix


def test_parse_transform_composes_operations() -> None:
    matrix = parse_transform("translate(10, 20) rotate(90) scale(2)")
    origin = matrix.transform_point(0, 0)
    x, y = matrix.transform_point(1, 0)

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

    assert components.translate_x == pytest.approx(10.0)
    assert components.translate_y == pytest.approx(-5.0)
    assert components.rotation == pytest.approx(30.0)
    assert components.scale_x == pytest.approx(2.0, rel=1e-6)
    assert components.scale_y == pytest.approx(3.0, rel=1e-6)
    assert abs(components.skew_x) < 1e-6


def test_matrix_transform_point() -> None:
    mat = Matrix(2, 0, 0, 3, 4, 5)
    x, y = mat.transform_point(3, 2)

    assert x == pytest.approx(10.0)
    assert y == pytest.approx(11.0)


def test_parse_transform_invalid_op_raises() -> None:
    with pytest.raises(ValueError):
        parse_transform("invalid(1)")
