"""Tests for Phase 4: Gradient units and spread method tracking.

This test suite verifies that gradient_units and spread_method fields
are properly preserved from resvg gradients to IR paint objects.
"""

from __future__ import annotations

import pytest

# Skip if resvg not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.painting.gradients import (
    GradientStop,
    LinearGradient,
    RadialGradient,
)
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    linear_gradient_to_paint,
    radial_gradient_to_paint,
)


class TestLinearGradientUnitsSpread:
    """Test units and spread_method tracking for linear gradients."""

    def test_userspaceonuse_pad(self):
        """Test userSpaceOnUse units with pad spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = LinearGradient(
            x1=0.0, y1=0.0, x2=100.0, y2=0.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = linear_gradient_to_paint(gradient)

        assert paint.gradient_units == "userSpaceOnUse"
        assert paint.spread_method == "pad"

    def test_objectboundingbox_reflect(self):
        """Test objectBoundingBox units with reflect spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=100, g=150, b=200, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=200, g=100, b=50, a=1.0)),
        ]

        gradient = LinearGradient(
            x1=0.0, y1=0.0, x2=1.0, y2=0.0,
            units="objectBoundingBox",
            spread_method="reflect",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = linear_gradient_to_paint(gradient)

        assert paint.gradient_units == "objectBoundingBox"
        assert paint.spread_method == "reflect"

    def test_userspaceonuse_repeat(self):
        """Test userSpaceOnUse units with repeat spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=0, g=255, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = LinearGradient(
            x1=0.0, y1=0.0, x2=50.0, y2=50.0,
            units="userSpaceOnUse",
            spread_method="repeat",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = linear_gradient_to_paint(gradient)

        assert paint.gradient_units == "userSpaceOnUse"
        assert paint.spread_method == "repeat"

    def test_with_transform(self):
        """Test that units and spread are preserved even with transforms."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        transform = Matrix(a=2.0, b=0.0, c=0.0, d=2.0, e=10.0, f=20.0)
        gradient = LinearGradient(
            x1=0.0, y1=0.0, x2=100.0, y2=0.0,
            units="objectBoundingBox",
            spread_method="reflect",
            transform=transform,
            stops=stops,
            href=None,
        )

        paint = linear_gradient_to_paint(gradient)

        # Units and spread should be preserved despite transform being applied
        assert paint.gradient_units == "objectBoundingBox"
        assert paint.spread_method == "reflect"
        # Transform should be baked in (set to None)
        assert paint.transform is None


class TestRadialGradientUnitsSpread:
    """Test units and spread_method tracking for radial gradients."""

    def test_userspaceonuse_pad(self):
        """Test userSpaceOnUse units with pad spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert paint.gradient_units == "userSpaceOnUse"
        assert paint.spread_method == "pad"

    def test_objectboundingbox_reflect(self):
        """Test objectBoundingBox units with reflect spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=100, g=150, b=200, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=200, g=100, b=50, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=0.5, cy=0.5, r=0.5,
            fx=0.5, fy=0.5,
            units="objectBoundingBox",
            spread_method="reflect",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert paint.gradient_units == "objectBoundingBox"
        assert paint.spread_method == "reflect"

    def test_userspaceonuse_repeat(self):
        """Test userSpaceOnUse units with repeat spread method."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=0, g=255, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=25.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            spread_method="repeat",
            transform=None,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert paint.gradient_units == "userSpaceOnUse"
        assert paint.spread_method == "repeat"

    def test_with_uniform_transform(self):
        """Test that units and spread are preserved with uniform transforms."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        transform = Matrix(a=2.0, b=0.0, c=0.0, d=2.0, e=10.0, f=20.0)
        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="objectBoundingBox",
            spread_method="reflect",
            transform=transform,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        # Units and spread should be preserved despite transform being applied
        assert paint.gradient_units == "objectBoundingBox"
        assert paint.spread_method == "reflect"
        # Transform should be baked in (set to None)
        assert paint.transform is None

    def test_severe_transform_raster_fallback_preserves_metadata(self):
        """Test that severe transforms request raster fallback and keep units/spread."""
        from svg2ooxml.ir.paint import RadialGradientPaint

        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        # Severe non-uniform transform → solid color fallback
        transform = Matrix(a=3.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert isinstance(paint, RadialGradientPaint)
        assert paint.policy_decision == "rasterize_nonuniform"
        assert paint.gradient_units == "userSpaceOnUse"
        assert paint.spread_method == "pad"
        assert paint.transform is not None


class TestGradientUnitsSpreadCombinations:
    """Test various combinations of units and spread methods."""

    @pytest.mark.parametrize("units", ["userSpaceOnUse", "objectBoundingBox"])
    @pytest.mark.parametrize("spread", ["pad", "reflect", "repeat"])
    def test_linear_all_combinations(self, units, spread):
        """Test all combinations of units and spread for linear gradients."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = LinearGradient(
            x1=0.0, y1=0.0, x2=100.0, y2=0.0,
            units=units,
            spread_method=spread,
            transform=None,
            stops=stops,
            href=None,
        )

        paint = linear_gradient_to_paint(gradient)

        assert paint.gradient_units == units
        assert paint.spread_method == spread

    @pytest.mark.parametrize("units", ["userSpaceOnUse", "objectBoundingBox"])
    @pytest.mark.parametrize("spread", ["pad", "reflect", "repeat"])
    def test_radial_all_combinations(self, units, spread):
        """Test all combinations of units and spread for radial gradients."""
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            units=units,
            spread_method=spread,
            transform=None,
            stops=stops,
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        assert paint.gradient_units == units
        assert paint.spread_method == spread
