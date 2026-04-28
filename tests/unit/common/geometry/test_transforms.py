"""Unit tests for the modern geometry transform helpers."""

from __future__ import annotations

import math

import pytest

from svg2ooxml.common.geometry.transforms.decompose import (
    classify_affine_matrix,
    classify_linear_transform,
    decompose_matrix,
    dominant_affine_component,
    identity_payload_for_affine_component,
)
from svg2ooxml.common.geometry.transforms.matrix import (
    IDENTITY,
    Matrix,
    rotate,
    scale,
    translate,
)
from svg2ooxml.common.geometry.transforms.parser import parse_transform
from svg2ooxml.common.geometry.transforms.space import CoordinateSpace


def test_parse_transform_composes_operations() -> None:
    matrix = parse_transform("translate(10, 20) rotate(90) scale(2)")
    origin = matrix.transform_xy(0, 0)
    x, y = matrix.transform_xy(1, 0)

    assert origin[0] == pytest.approx(10.0)
    assert origin[1] == pytest.approx(20.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(22.0)


def test_parse_transform_uses_tangent_for_skew() -> None:
    skew_x = parse_transform("skewX(45)")
    skew_y = parse_transform("skewY(30)")

    assert skew_x.transform_xy(0.0, 1.0)[0] == pytest.approx(math.tan(math.radians(45)))
    assert skew_y.transform_xy(1.0, 0.0)[1] == pytest.approx(math.tan(math.radians(30)))


def test_parse_transform_accepts_compact_signed_numbers() -> None:
    matrix = parse_transform("translate(10-20)")

    assert matrix.e == pytest.approx(10.0)
    assert matrix.f == pytest.approx(-20.0)


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


def test_classify_affine_matrix_identifies_basic_components() -> None:
    assert classify_affine_matrix(Matrix(1, 0, 0, 1, 0, 0)) == ("identity", None)
    assert classify_affine_matrix(Matrix(1, 0, 0, 1, 10, 20)) == (
        "translate",
        (10, 20),
    )
    assert classify_affine_matrix(Matrix(2, 0, 0, 3, 0, 0)) == (
        "scale",
        (2, 3),
    )


def test_classify_affine_matrix_decomposes_composites_by_priority() -> None:
    composed = translate(10, 20).multiply(rotate(30)).multiply(scale(2, 2))

    assert classify_affine_matrix(composed)[0] == "translate"
    assert dominant_affine_component(
        composed,
        component_priority=("rotate", "scale", "translate"),
    )[0] == "rotate"


def test_classify_affine_matrix_rejects_skew() -> None:
    skewed = Matrix(1, 0, math.tan(math.radians(30)), 1, 0, 0)

    assert classify_affine_matrix(skewed) == (None, None)
    assert dominant_affine_component(skewed) is None


def test_classify_linear_transform_reports_singular_values_and_shear() -> None:
    classification = classify_linear_transform(2.0, 0.0, 0.0, 1.0)

    assert classification.non_uniform is True
    assert classification.has_shear is False
    assert classification.det_sign == 1
    assert classification.s1 == pytest.approx(2.0)
    assert classification.s2 == pytest.approx(1.0)
    assert classification.ratio == pytest.approx(2.0)

    skew = classify_linear_transform(1.0, 0.0, math.tan(math.radians(15.0)), 1.0)
    assert skew.has_shear is True
    assert skew.shear_degrees == pytest.approx(15.0)


def test_affine_identity_payloads() -> None:
    assert identity_payload_for_affine_component("translate") == (0.0, 0.0)
    assert identity_payload_for_affine_component("scale") == (1.0, 1.0)
    assert identity_payload_for_affine_component("rotate") == 0.0


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
