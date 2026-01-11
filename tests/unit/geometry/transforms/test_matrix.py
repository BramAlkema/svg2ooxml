"""Tests for transform matrix utilities."""

import pytest

from svg2ooxml.common.geometry.transforms.decompose import compose_matrix, decompose_matrix
from svg2ooxml.common.geometry.transforms.matrix import Matrix2D
from svg2ooxml.ir.geometry import Point


def test_matrix_multiply_and_transform() -> None:
    translate = Matrix2D.translation(5, 10)
    scale = Matrix2D.scale(2, 3)

    combined = translate.multiply(scale)
    point = combined.transform_point(Point(1, 1))

    assert point.x == 7
    assert point.y == 13


def test_decompose_and_compose_roundtrip() -> None:
    original = Matrix2D(a=2, b=1, c=0.5, d=3, e=4, f=5)
    components = decompose_matrix(original)
    recomposed = compose_matrix(components)

    assert recomposed.a == pytest.approx(original.a, rel=1e-6)
    assert recomposed.e == pytest.approx(original.e, rel=1e-6)
