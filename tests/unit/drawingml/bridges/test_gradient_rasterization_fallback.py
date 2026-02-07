"""Tests for Phase 3: Radial gradient rasterization fallback.

This test suite verifies that severe non-uniform transforms retain gradient
data for bitmap fallback instead of collapsing to a flat solid color.
"""

from __future__ import annotations

import pytest

# Skip if resvg not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.painting.gradients import GradientStop, RadialGradient
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    _calculate_raster_size,
    radial_gradient_to_paint,
)
from svg2ooxml.ir.paint import RadialGradientPaint


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


class TestRasterFallback:
    """Test raster fallback metadata for severe non-uniform transforms."""

    def test_severe_non_uniform_scale_requests_raster(self):
        """Test severe non-uniform scale returns raster-capable gradient."""
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

    def test_skew_transform_requests_raster(self):
        """Test skew/shear transform returns raster-capable gradient."""
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

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"

    def test_raster_fallback_preserves_two_stop_colors(self):
        """Test raster fallback preserves stop colors/opacity."""
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

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"
        assert [stop.rgb for stop in paint.stops] == ["64C832", "C86496"]
        assert [stop.opacity for stop in paint.stops] == [1.0, pytest.approx(0.8)]

    def test_raster_fallback_preserves_three_stop_colors(self):
        """Test raster fallback preserves three-stop gradients."""
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

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"
        assert [stop.rgb for stop in paint.stops] == ["000000", "969696", "FFFFFF"]
        assert [stop.opacity for stop in paint.stops] == [1.0, pytest.approx(0.5), pytest.approx(0.0)]

    def test_uniform_scale_does_not_request_raster(self):
        """Test uniform scale returns radial gradient without raster fallback."""
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
        assert paint.policy_decision == "vector_ok"

    def test_mild_anisotropy_keeps_vector_warning(self):
        """Test mild anisotropy returns radial gradient with warning policy."""
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

    def test_no_transform_keeps_vector_gradient(self):
        """Test no transform returns a native radial gradient."""
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

    def test_severe_anisotropy_mentions_raster_fallback(self, caplog):
        """Test that severe anisotropy log mentions raster fallback."""
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

        # Check that log mentions raster fallback
        assert any("raster fallback requested" in record.message for record in caplog.records)

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
