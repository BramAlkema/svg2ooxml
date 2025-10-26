"""Tests for the CTM coordinate space stack."""

from svg2ooxml.transforms import CoordinateSpace, Matrix


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
