"""Tests for radial gradient transform classification and policy decisions.

This test suite verifies the Phase 1 implementation of transform detection and telemetry
for radial gradients. See docs/tasks/resvg-transform-limitations.md for specifications.
"""

from __future__ import annotations

import math

import pytest

# Skip entire module if resvg is not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    TransformClass,
    classify_linear,
    decide_radial_policy,
    radial_gradient_to_paint,
)


class TestTransformClassification:
    """Test SVD-based transform classification."""

    def test_identity_transform(self):
        """Test identity matrix classification."""
        cls = classify_linear(1.0, 0.0, 0.0, 1.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(1.0)
        assert cls.s2 == pytest.approx(1.0)
        assert cls.ratio == pytest.approx(1.0)

    def test_uniform_scale(self):
        """Test uniform scale (2x in both directions)."""
        cls = classify_linear(2.0, 0.0, 0.0, 2.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(2.0)
        assert cls.s2 == pytest.approx(2.0)
        assert cls.ratio == pytest.approx(1.0)

    def test_non_uniform_scale_2x1(self):
        """Test non-uniform scale (2x horizontal, 1x vertical)."""
        cls = classify_linear(2.0, 0.0, 0.0, 1.0)
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(2.0)  # Larger singular value
        assert cls.s2 == pytest.approx(1.0)  # Smaller singular value
        assert cls.ratio == pytest.approx(2.0)

    def test_mild_anisotropy(self):
        """Test mild anisotropy (ratio ≈ 1.015, should warn but not rasterize)."""
        # Scale(1.015, 1.0)
        cls = classify_linear(1.015, 0.0, 0.0, 1.0)
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.ratio == pytest.approx(1.015, abs=0.001)

    def test_skewx_transform(self):
        """Test skewX transform (shear)."""
        # SkewX(30°): tan(30°) ≈ 0.577
        cls = classify_linear(1.0, 0.0, 0.577, 1.0)
        assert cls.has_shear
        assert cls.det_sign == 1

    def test_rotation_90_degrees(self):
        """Test 90-degree rotation (should be uniform, no shear)."""
        # Rotation by 90°: [[0, -1], [1, 0]]
        cls = classify_linear(0.0, 1.0, -1.0, 0.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(1.0)
        assert cls.s2 == pytest.approx(1.0)

    def test_rotation_with_uniform_scale(self):
        """Test rotation + uniform scale (should be uniform, no shear)."""
        # Scale(2) * Rotation(45°)
        c = 2 * math.cos(math.radians(45))
        s = 2 * math.sin(math.radians(45))
        cls = classify_linear(c, s, -s, c)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.s1 == pytest.approx(2.0)
        assert cls.s2 == pytest.approx(2.0)

    def test_reflection_negative_determinant(self):
        """Test reflection (negative determinant)."""
        # Flip in X: [[-1, 0], [0, 1]]
        cls = classify_linear(-1.0, 0.0, 0.0, 1.0)
        assert cls.det_sign == -1

    def test_degenerate_zero_determinant(self):
        """Test degenerate transform (zero determinant)."""
        # Projection onto x-axis: [[1, 0], [0, 0]]
        cls = classify_linear(1.0, 0.0, 0.0, 0.0)
        assert cls.det_sign == 0
        assert cls.s2 == pytest.approx(0.0)


class TestRadialGradientPolicy:
    """Test policy decisions for radial gradient transforms."""

    def test_policy_vector_ok_identity(self):
        """Test identity transform → vector_ok."""
        policy, cls = decide_radial_policy(1.0, 0.0, 0.0, 1.0)
        assert policy == "vector_ok"
        assert not cls.non_uniform

    def test_policy_vector_ok_uniform_scale(self):
        """Test uniform scale → vector_ok."""
        policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 2.0)
        assert policy == "vector_ok"
        assert not cls.non_uniform

    def test_policy_vector_ok_rotation(self):
        """Test rotation → vector_ok."""
        c = math.cos(math.radians(45))
        s = math.sin(math.radians(45))
        policy, cls = decide_radial_policy(c, s, -s, c)
        assert policy == "vector_ok"

    def test_policy_warn_mild_anisotropy(self):
        """Test mild anisotropy (ratio=1.015) → vector_warn_mild_anisotropy."""
        policy, cls = decide_radial_policy(1.015, 0.0, 0.0, 1.0, mild_ratio=1.02)
        assert policy == "vector_warn_mild_anisotropy"
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.ratio <= 1.02

    def test_policy_rasterize_severe_anisotropy(self):
        """Test severe anisotropy (ratio=2.0) → rasterize_nonuniform."""
        policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 1.0)
        assert policy == "rasterize_nonuniform"
        assert cls.ratio == pytest.approx(2.0)

    def test_policy_rasterize_skew(self):
        """Test skew transform → rasterize_nonuniform."""
        # SkewX(30°)
        policy, cls = decide_radial_policy(1.0, 0.0, 0.577, 1.0)
        assert policy == "rasterize_nonuniform"
        assert cls.has_shear

    def test_policy_rasterize_scale_plus_rotation(self):
        """Test non-uniform scale + rotation → rasterize_nonuniform."""
        # Scale(2, 1) * Rotation(30°)
        c = math.cos(math.radians(30))
        s = math.sin(math.radians(30))
        a = 2 * c
        b = 2 * s
        c_val = -1 * s
        d = 1 * c
        policy, cls = decide_radial_policy(a, b, c_val, d)
        assert policy == "rasterize_nonuniform"


class TestGradientTransformIntegration:
    """Integration tests for gradient adapter with transform classification."""

    def test_radial_gradient_no_transform(self):
        """Test radial gradient without transform."""
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color

        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            stops=stops,
            transform=None,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        # Verify no classification for no transform
        assert paint.had_transform_flag is False
        assert paint.policy_decision is None
        assert paint.transform_class is None
        assert paint.gradient_transform is None

    def test_radial_gradient_with_uniform_scale(self):
        """Test radial gradient with uniform scale transform."""
        from svg2ooxml.core.resvg.geometry.matrix import Matrix
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color

        transform = Matrix(a=2.0, b=0.0, c=0.0, d=2.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            stops=stops,
            transform=transform,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        # Verify classification for uniform scale
        assert paint.had_transform_flag is True
        assert paint.policy_decision == "vector_ok"
        assert paint.transform_class is not None
        assert not paint.transform_class.non_uniform
        assert paint.transform_class.ratio == pytest.approx(1.0)
        assert paint.gradient_transform == transform

    def test_radial_gradient_with_non_uniform_scale(self):
        """Test radial gradient with non-uniform scale requests raster fallback (Phase 3)."""
        from svg2ooxml.core.resvg.geometry.matrix import Matrix
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color
        from svg2ooxml.ir.paint import RadialGradientPaint

        transform = Matrix(a=2.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            stops=stops,
            transform=transform,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"
        assert paint.transform is not None

    def test_radial_gradient_with_skew(self):
        """Test radial gradient with skew transform requests raster fallback (Phase 3)."""
        from svg2ooxml.core.resvg.geometry.matrix import Matrix
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color
        from svg2ooxml.ir.paint import RadialGradientPaint

        # SkewX(30°): tan(30°) ≈ 0.577
        transform = Matrix(a=1.0, b=0.0, c=0.577, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            stops=stops,
            transform=transform,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"
        assert paint.transform is not None

    def test_radial_gradient_with_mild_anisotropy(self):
        """Test radial gradient with mild anisotropy (should warn)."""
        from svg2ooxml.core.resvg.geometry.matrix import Matrix
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color

        transform = Matrix(a=1.015, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            stops=stops,
            transform=transform,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        # Verify mild anisotropy warning
        assert paint.had_transform_flag is True
        assert paint.policy_decision == "vector_warn_mild_anisotropy"
        assert paint.transform_class is not None
        assert paint.transform_class.non_uniform
        assert not paint.transform_class.has_shear
        assert paint.transform_class.ratio <= 1.02
