"""Tests for transform matrix utilities."""

import pytest

from svg2ooxml.geometry.transforms import matrix, decompose
from svg2ooxml.ir.geometry import Point


def test_matrix_multiply_and_transform() -> None:
    translate = matrix.Matrix2D.translation(5, 10)
    scale = matrix.Matrix2D.scale(2, 3)

    combined = translate.multiply(scale)
    point = combined.transform_point(Point(1, 1))

    assert point.x == 7
    assert point.y == 13


def test_decompose_and_compose_roundtrip() -> None:
    original = matrix.Matrix2D(a=2, b=1, c=0.5, d=3, e=4, f=5)
    components = decompose.decompose_matrix(original)
    recomposed = decompose.compose_matrix(components)

    assert recomposed.a == pytest.approx(original.a, rel=1e-6)
    assert recomposed.e == pytest.approx(original.e, rel=1e-6)
