"""Tests for geometry helper utilities used by the converter."""

from __future__ import annotations

import math

from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.common.geometry import Matrix2D


def test_is_axis_aligned_detects_simple_scale() -> None:
    matrix = Matrix2D(2.0, 0.0, 0.0, 3.0, 0.0, 0.0)
    assert is_axis_aligned(matrix)


def test_is_axis_aligned_rejects_rotation() -> None:
    angle = math.radians(45)
    matrix = Matrix2D(math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle), 0.0, 0.0)
    assert not is_axis_aligned(matrix)


def test_scaled_corner_radius_scales_with_matrix() -> None:
    matrix = Matrix2D(2.0, 0.0, 0.0, 3.0, 0.0, 0.0)
    assert scaled_corner_radius(4.0, matrix) == 4.0 * 2.0  # min scale component


def test_scaled_corner_radius_returns_original_for_skew() -> None:
    matrix = Matrix2D(1.0, 0.5, 0.0, 1.0, 0.0, 0.0)
    assert scaled_corner_radius(5.0, matrix) == 5.0


def test_transform_axis_aligned_rect_applies_transform() -> None:
    matrix = Matrix2D(2.0, 0.0, 0.0, 3.0, 5.0, -7.0)
    bounds = transform_axis_aligned_rect(matrix, 1.0, 2.0, 4.0, 3.0)
    assert bounds is not None
    assert bounds.x == 5.0 + 1.0 * 2.0
    assert bounds.y == -7.0 + 2.0 * 3.0
    assert bounds.width == 4.0 * 2.0
    assert bounds.height == 3.0 * 3.0


def test_transform_axis_aligned_rect_returns_none_for_degenerate() -> None:
    matrix = Matrix2D(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert transform_axis_aligned_rect(matrix, 0.0, 0.0, 10.0, 10.0) is None


__all__ = []
