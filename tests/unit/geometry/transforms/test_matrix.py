"""Tests for transform matrix utilities."""

import math

import pytest

from svg2ooxml.common.geometry import parse_transform_list
from svg2ooxml.common.geometry.transforms.decompose import (
    compose_matrix,
    decompose_matrix,
)
from svg2ooxml.common.geometry.transforms.matrix import Matrix2D
from svg2ooxml.ir.geometry import Point


def test_matrix_multiply_and_transform() -> None:
    translate = Matrix2D.translation(5, 10)
    scale = Matrix2D.scale(2, 3)

    combined = translate.multiply(scale)
    point = combined.transform_point(Point(1, 1))

    assert point.x == 7
    assert point.y == 13


def test_matrix_skew_uses_svg_tangent_semantics() -> None:
    point_x = Matrix2D.skew_x(45).transform_point(Point(0, 1))
    point_y = Matrix2D.skew_y(30).transform_point(Point(1, 0))

    assert point_x.x == pytest.approx(math.tan(math.radians(45)))
    assert point_y.y == pytest.approx(math.tan(math.radians(30)))


def test_parse_transform_list_accepts_compact_signed_numbers() -> None:
    matrix = parse_transform_list("translate(10-20)")

    assert matrix.e == pytest.approx(10.0)
    assert matrix.f == pytest.approx(-20.0)


def test_decompose_and_compose_roundtrip() -> None:
    original = Matrix2D(a=2, b=1, c=0.5, d=3, e=4, f=5)
    components = decompose_matrix(original)
    recomposed = compose_matrix(components)

    assert recomposed.a == pytest.approx(original.a, rel=1e-6)
    assert recomposed.e == pytest.approx(original.e, rel=1e-6)
