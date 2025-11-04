"""Tests for Phase 3: Radial gradient rasterization fallback.

This test suite verifies the solid color fallback for radial gradients with
severe non-uniform transforms that cannot be accurately rendered as circles.
"""

from __future__ import annotations

import pytest

# Skip if resvg not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    _calculate_raster_size,
    radial_gradient_to_paint,
)
from svg2ooxml.ir.paint import SolidPaint, RadialGradientPaint


class TestRasterSizeCalculation:
    """Test raster size calculation with clamping."""

    def test_small_size_clamped_to_min(self):
        """Test that small sizes are clamped to minimum (64px)."""
        size = _calculate_raster_size(s1=2.0, s2=2.0)
        assert size == 64  # ceil(2.0 * 2.0) = 4, clamped to 64

    def test_moderate_size_within_range(self):
        """Test moderate sizes are not clamped."""
        size = _calculate_raster_size(s1=50.0, s2=25.0)
        assert size == 100  # ceil(50.0 * 2.0) = 100

    def test_large_size_clamped_to_max(self):
        """Test that large sizes are clamped to maximum (4096px)."""
        size = _calculate_raster_size(s1=10000.0, s2=5000.0)
        assert size == 4096  # ceil(10000 * 2.0) = 20000, clamped to 4096

    def test_exact_min_boundary(self):
        """Test exact minimum boundary."""
        size = _calculate_raster_size(s1=32.0, s2=32.0)
        assert size == 64  # ceil(32.0 * 2.0) = 64

    def test_just_above_min(self):
        """Test size just above minimum."""
        size = _calculate_raster_size(s1=33.0, s2=33.0)
        assert size == 66  # ceil(33.0 * 2.0) = 66

    def test_exact_max_boundary(self):
        """Test exact maximum boundary."""
        size = _calculate_raster_size(s1=2048.0, s2=2048.0)
        assert size == 4096  # ceil(2048.0 * 2.0) = 4096

    def test_just_below_max(self):
        """Test size just below maximum."""
        size = _calculate_raster_size(s1=2047.0, s2=2047.0)
        assert size == 4094  # ceil(2047.0 * 2.0) = 4094

    def test_custom_oversample(self):
        """Test custom oversampling factor."""
        size = _calculate_raster_size(s1=100.0, s2=50.0, oversample=3.0)
        assert size == 300  # ceil(100.0 * 3.0) = 300

    def test_custom_min_max(self):
        """Test custom min/max bounds."""
        size = _calculate_raster_size(s1=10.0, s2=10.0, min_size=128, max_size=2048)
        assert size == 128  # ceil(10.0 * 2.0) = 20, clamped to 128

    def test_uses_max_singular_value(self):
        """Test that max singular value is used (not min)."""
        # s1=100, s2=10, max=100
        size = _calculate_raster_size(s1=100.0, s2=10.0)
        assert size == 200  # ceil(100.0 * 2.0) = 200


class TestSolidColorFallback:
    """Test solid color fallback for severe non-uniform transforms."""

    def test_severe_non_uniform_scale_returns_solid(self):
        """Test severe non-uniform scale returns SolidPaint."""
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

        # Should return SolidPaint, not RadialGradientPaint
        assert isinstance(paint, SolidPaint)
        assert not isinstance(paint, RadialGradientPaint)

    def test_skew_transform_returns_solid(self):
        """Test skew/shear transform returns SolidPaint."""
        # SkewX(30°): tan(30°) ≈ 0.577
        transform = Matrix(a=1.0, b=0.0, c=0.577, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=100, g=150, b=200, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=200, g=100, b=50, a=1.0)),
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

        # Should return SolidPaint for shear
        assert isinstance(paint, SolidPaint)

    def test_average_color_calculation_two_stops(self):
        """Test average color calculation with two stops."""
        transform = Matrix(a=3.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=100, g=200, b=50, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=200, g=100, b=150, a=0.8)),
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

        assert isinstance(paint, SolidPaint)
        # Average: r=(100+200)/2=150, g=(200+100)/2=150, b=(50+150)/2=100
        # Hex: 150=0x96, 150=0x96, 100=0x64
        expected_r = int((100 + 200) / 2)  # 150
        expected_g = int((200 + 100) / 2)  # 150
        expected_b = int((50 + 150) / 2)   # 100
        expected_rgb = f"{expected_r:02X}{expected_g:02X}{expected_b:02X}"
        assert paint.rgb == expected_rgb  # "969664"

        # Average opacity: (1.0 + 0.8) / 2 = 0.9
        assert paint.opacity == pytest.approx(0.9)

    def test_average_color_calculation_three_stops(self):
        """Test average color calculation with three stops."""
        transform = Matrix(a=5.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=0, g=0, b=0, a=1.0)),
            GradientStop(offset=0.5, color=Color(r=150, g=150, b=150, a=0.5)),
            GradientStop(offset=1.0, color=Color(r=255, g=255, b=255, a=0.0)),
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

        assert isinstance(paint, SolidPaint)
        # Average: r=(0+150+255)/3=135, g=(0+150+255)/3=135, b=(0+150+255)/3=135
        expected_r = int((0 + 150 + 255) / 3)  # 135
        expected_g = int((0 + 150 + 255) / 3)  # 135
        expected_b = int((0 + 150 + 255) / 3)  # 135
        expected_rgb = f"{expected_r:02X}{expected_g:02X}{expected_b:02X}"
        assert paint.rgb == expected_rgb  # "878787"

        # Average opacity: (1.0 + 0.5 + 0.0) / 3 = 0.5
        assert paint.opacity == pytest.approx(0.5)

    def test_uniform_scale_does_not_return_solid(self):
        """Test uniform scale does NOT return SolidPaint (returns RadialGradientPaint)."""
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

        # Should return RadialGradientPaint for uniform scale
        assert isinstance(paint, RadialGradientPaint)
        assert not isinstance(paint, SolidPaint)

    def test_mild_anisotropy_does_not_return_solid(self):
        """Test mild anisotropy does NOT return SolidPaint."""
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

        # Should return RadialGradientPaint for mild anisotropy
        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "vector_warn_mild_anisotropy"

    def test_no_transform_does_not_return_solid(self):
        """Test no transform does NOT return SolidPaint."""
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

        # Should return RadialGradientPaint for no transform
        assert isinstance(paint, RadialGradientPaint)
        assert paint.had_transform_flag is False


class TestLoggingOutputPhase3:
    """Test logging output for Phase 3 rasterization fallback."""

    def test_severe_anisotropy_mentions_raster_size(self, caplog):
        """Test that severe anisotropy log includes raster size."""
        import logging
        caplog.set_level(logging.INFO)

        transform = Matrix(a=100.0, b=0.0, c=0.0, d=50.0, e=0.0, f=0.0)
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

        radial_gradient_to_paint(gradient)

        # Check that log includes raster size
        assert any("Raster size would be:" in record.message for record in caplog.records)
        assert any("200px" in record.message for record in caplog.records)  # ceil(100 * 2.0) = 200

    def test_severe_anisotropy_mentions_solid_color_fallback(self, caplog):
        """Test that severe anisotropy log mentions solid color fallback."""
        import logging
        caplog.set_level(logging.INFO)

        transform = Matrix(a=3.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
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

        radial_gradient_to_paint(gradient)

        # Check that log mentions solid color fallback
        assert any("solid color fallback" in record.message for record in caplog.records)
        assert any("avg of 2 stops" in record.message for record in caplog.records)

    def test_skew_log_mentions_shear_reason(self, caplog):
        """Test that skew transform log mentions shear as reason."""
        import logging
        caplog.set_level(logging.INFO)

        # SkewX(30°)
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

        radial_gradient_to_paint(gradient)

        # Check that log mentions shear as reason
        assert any("shear" in record.message for record in caplog.records)

    def test_non_uniform_scale_log_mentions_ratio(self, caplog):
        """Test that non-uniform scale log includes ratio in reason."""
        import logging
        caplog.set_level(logging.INFO)

        transform = Matrix(a=2.5, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
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

        radial_gradient_to_paint(gradient)

        # Check that log mentions non-uniform scale with ratio
        assert any("non-uniform scale" in record.message for record in caplog.records)
        assert any("ratio=" in record.message for record in caplog.records)
