"""Tests for radial gradient transform telemetry serialization.

This test suite verifies Phase 2 telemetry serialization for radial gradients
with transform classification data.
"""

from __future__ import annotations

import pytest

# Skip if resvg not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import radial_gradient_to_paint
from svg2ooxml.core.traversal.hooks import TraversalHooksMixin


class MockConverter(TraversalHooksMixin):
    """Mock converter for testing telemetry serialization."""

    def __init__(self):
        self._policy_context = None

    def _serialize_matrix(self, matrix):
        """Serialize matrix to dict."""
        if matrix is None:
            return None
        if hasattr(matrix, "tolist"):
            return matrix.tolist()
        return {
            "a": matrix.a,
            "b": matrix.b,
            "c": matrix.c,
            "d": matrix.d,
            "e": matrix.e,
            "f": matrix.f,
        }


class TestGradientTransformTelemetry:
    """Test telemetry serialization for gradient transforms."""

    def test_radial_gradient_no_transform_telemetry(self):
        """Test radial gradient without transform has no telemetry fields."""
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
        converter = MockConverter()
        result = converter._serialize_paint(paint)

        assert result["type"] == "radialGradient"
        assert "had_transform" not in result
        assert "policy_decision" not in result
        assert "transform_class" not in result

    def test_radial_gradient_uniform_scale_telemetry(self):
        """Test radial gradient with uniform scale includes telemetry."""
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
        converter = MockConverter()
        result = converter._serialize_paint(paint)

        assert result["type"] == "radialGradient"
        assert result["had_transform"] is True
        assert result["policy_decision"] == "vector_ok"
        assert result["gradient_transform"] == {
            "a": 2.0, "b": 0.0, "c": 0.0, "d": 2.0, "e": 0.0, "f": 0.0
        }
        assert result["transform_class"]["non_uniform"] is False
        assert result["transform_class"]["has_shear"] is False
        assert result["transform_class"]["s1"] == pytest.approx(2.0)
        assert result["transform_class"]["s2"] == pytest.approx(2.0)
        assert result["transform_class"]["ratio"] == pytest.approx(1.0)

    def test_radial_gradient_mild_anisotropy_telemetry(self):
        """Test radial gradient with mild anisotropy includes warning in telemetry."""
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
        converter = MockConverter()
        result = converter._serialize_paint(paint)

        assert result["type"] == "radialGradient"
        assert result["had_transform"] is True
        assert result["policy_decision"] == "vector_warn_mild_anisotropy"
        assert result["transform_class"]["non_uniform"] is True
        assert result["transform_class"]["has_shear"] is False
        assert result["transform_class"]["ratio"] == pytest.approx(1.015, abs=0.001)

    def test_radial_gradient_severe_anisotropy_telemetry(self):
        """Test radial gradient with severe anisotropy requests raster fallback (Phase 3)."""
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
        converter = MockConverter()
        result = converter._serialize_paint(paint)

        assert result["type"] == "radialGradient"
        assert result["had_transform"] is True
        assert result["policy_decision"] == "rasterize_nonuniform"
        assert result["transform"] == [
            [2.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]

    def test_radial_gradient_skew_telemetry(self):
        """Test radial gradient with skew requests raster fallback (Phase 3)."""
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
        converter = MockConverter()
        result = converter._serialize_paint(paint)

        assert result["type"] == "radialGradient"
        assert result["had_transform"] is True
        assert result["policy_decision"] == "rasterize_nonuniform"
        assert result["transform"] == [
            [1.0, 0.577, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]


class TestLoggingOutput:
    """Test logging output for gradient transform warnings."""

    def test_mild_anisotropy_debug_log(self, caplog):
        """Test that mild anisotropy emits debug log."""
        import logging
        caplog.set_level(logging.DEBUG)

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

        radial_gradient_to_paint(gradient)

        # Check that debug log was emitted
        assert any("mild anisotropy" in record.message for record in caplog.records)
        assert any("ratio=1.015" in record.message for record in caplog.records)

    def test_severe_anisotropy_info_log(self, caplog):
        """Test that severe anisotropy emits info log."""
        import logging
        caplog.set_level(logging.INFO)

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

        radial_gradient_to_paint(gradient)

        # Check that info log was emitted (Phase 3: raster fallback request)
        assert any("non-uniform scale" in record.message for record in caplog.records)
        assert any("raster fallback requested" in record.message for record in caplog.records)

    def test_skew_info_log(self, caplog):
        """Test that skew transform emits info log mentioning shear."""
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

        # Check that info log mentions shear
        assert any("shear" in record.message for record in caplog.records)
