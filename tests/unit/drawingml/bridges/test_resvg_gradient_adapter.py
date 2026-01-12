"""Unit tests for resvg gradient adapter."""

from __future__ import annotations

import pytest

# Skip entire module if resvg is not available
pytest.importorskip("svg2ooxml.core.resvg.painting.gradients")

from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    linear_gradient_to_paint,
    radial_gradient_to_paint,
)
from svg2ooxml.core.resvg.painting.gradients import LinearGradient, RadialGradient, GradientStop
from svg2ooxml.core.resvg.painting.paint import Color
from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint


class TestLinearGradientConversion:
    """Test linear gradient conversion from resvg to IR."""

    def test_simple_linear_gradient(self):
        """Test basic linear gradient conversion."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        assert isinstance(paint, LinearGradientPaint)
        assert paint.start == (0.0, 0.0)
        assert paint.end == (1.0, 0.0)
        assert len(paint.stops) == 2

        # Check first stop (red)
        assert paint.stops[0].offset == 0.0
        assert paint.stops[0].rgb == "FF0000"
        assert paint.stops[0].opacity == 1.0

        # Check second stop (blue)
        assert paint.stops[1].offset == 1.0
        assert paint.stops[1].rgb == "0000FF"
        assert paint.stops[1].opacity == 1.0

    def test_linear_gradient_with_opacity(self):
        """Test linear gradient with semi-transparent colors."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=1.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=255, b=255, a=0.5)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=0, a=0.25)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        assert paint.stops[0].opacity == 0.5
        assert paint.stops[1].opacity == 0.25

    def test_linear_gradient_diagonal(self):
        """Test diagonal linear gradient."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=100.0,
            y2=100.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=255, g=255, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=255, g=0, b=0, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        assert paint.start == (0.0, 0.0)
        assert paint.end == (100.0, 100.0)
        assert len(paint.stops) == 3

        # Green → Yellow → Red
        assert paint.stops[0].rgb == "00FF00"
        assert paint.stops[1].rgb == "FFFF00"
        assert paint.stops[2].rgb == "FF0000"

    def test_linear_gradient_single_stop_duplicated(self):
        """Test that single stop is duplicated to meet IR requirement."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(GradientStop(offset=0.5, color=Color(r=128, g=128, b=128, a=1.0)),),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Should have 2 stops (duplicated)
        assert len(paint.stops) == 2
        assert paint.stops[0].rgb == paint.stops[1].rgb == "808080"

    def test_linear_gradient_no_stops_defaults(self):
        """Test that empty stops get default black-to-white gradient."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Should have 2 default stops
        assert len(paint.stops) == 2
        assert paint.stops[0].rgb == "000000"  # Black
        assert paint.stops[1].rgb == "FFFFFF"  # White

    def test_linear_gradient_stops_clamped_below_zero(self):
        """Test that stop offsets < 0 are clamped to 0."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="repeat",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=-0.5, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Negative offset should be clamped to 0.0
        assert paint.stops[0].offset == 0.0
        assert paint.stops[1].offset == 0.5
        assert paint.stops[2].offset == 1.0

    def test_linear_gradient_stops_clamped_above_one(self):
        """Test that stop offsets > 1 are clamped to 1."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="repeat",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=1.5, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Offset > 1 should be clamped to 1.0
        assert paint.stops[0].offset == 0.0
        assert paint.stops[1].offset == 0.5
        assert paint.stops[2].offset == 1.0

    def test_linear_gradient_empty_href_normalized(self):
        """Test that empty href is normalized to None."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="",  # Empty href
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Empty href should be normalized to None
        assert paint.gradient_id is None

    def test_linear_gradient_whitespace_href_normalized(self):
        """Test that whitespace-only href is normalized to None."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="   ",  # Whitespace href
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Whitespace href should be normalized to None
        assert paint.gradient_id is None

    def test_linear_gradient_valid_href_preserved(self):
        """Test that valid href is preserved."""
        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="#otherGradient",
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Valid href should be preserved
        assert paint.gradient_id == "#otherGradient"


class TestRadialGradientConversion:
    """Test radial gradient conversion from resvg to IR."""

    def test_simple_radial_gradient(self):
        """Test basic radial gradient conversion."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=255, b=255, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=0, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        assert isinstance(paint, RadialGradientPaint)
        assert paint.center == (0.5, 0.5)
        assert paint.radius == 0.5
        assert paint.focal_point is None  # Same as center, so None
        assert len(paint.stops) == 2

        # White to black
        assert paint.stops[0].rgb == "FFFFFF"
        assert paint.stops[1].rgb == "000000"

    def test_radial_gradient_with_focal_point(self):
        """Test radial gradient with different focal point."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.3,  # Focal point offset
            fy=0.3,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        assert paint.center == (0.5, 0.5)
        assert paint.focal_point == (0.3, 0.3)  # Different from center

    def test_radial_gradient_in_user_space(self):
        """Test radial gradient in userSpaceOnUse."""
        resvg_gradient = RadialGradient(
            cx=100.0,
            cy=100.0,
            r=50.0,
            fx=100.0,
            fy=100.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=255, g=255, b=0, a=0.5)),
                GradientStop(offset=1.0, color=Color(r=255, g=0, b=0, a=0.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        assert paint.center == (100.0, 100.0)
        assert paint.radius == 50.0
        assert len(paint.stops) == 3

        # Check opacities
        assert paint.stops[0].opacity == 1.0
        assert paint.stops[1].opacity == 0.5
        assert paint.stops[2].opacity == 0.0

    def test_radial_gradient_single_stop_duplicated(self):
        """Test that single stop is duplicated to meet IR requirement."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(GradientStop(offset=0.5, color=Color(r=100, g=150, b=200, a=1.0)),),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Should have 2 stops (duplicated)
        assert len(paint.stops) == 2
        assert paint.stops[0].rgb == paint.stops[1].rgb == "6496C8"

    def test_radial_gradient_no_stops_defaults(self):
        """Test that empty stops get default black-to-white gradient."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Should have 2 default stops
        assert len(paint.stops) == 2
        assert paint.stops[0].rgb == "000000"
        assert paint.stops[1].rgb == "FFFFFF"

    def test_radial_gradient_stops_clamped_below_zero(self):
        """Test that stop offsets < 0 are clamped to 0."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="repeat",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=-0.3, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Negative offset should be clamped to 0.0
        assert paint.stops[0].offset == 0.0
        assert paint.stops[1].offset == 0.5
        assert paint.stops[2].offset == 1.0

    def test_radial_gradient_stops_clamped_above_one(self):
        """Test that stop offsets > 1 are clamped to 1."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="repeat",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=0.5, color=Color(r=0, g=255, b=0, a=1.0)),
                GradientStop(offset=2.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Offset > 1 should be clamped to 1.0
        assert paint.stops[0].offset == 0.0
        assert paint.stops[1].offset == 0.5
        assert paint.stops[2].offset == 1.0

    def test_radial_gradient_empty_href_normalized(self):
        """Test that empty href is normalized to None."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="",  # Empty href
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Empty href should be normalized to None
        assert paint.gradient_id is None

    def test_radial_gradient_whitespace_href_normalized(self):
        """Test that whitespace-only href is normalized to None."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="  \t  ",  # Whitespace href
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Whitespace href should be normalized to None
        assert paint.gradient_id is None

    def test_radial_gradient_valid_href_preserved(self):
        """Test that valid href is preserved."""
        resvg_gradient = RadialGradient(
            cx=0.5,
            cy=0.5,
            r=0.5,
            fx=0.5,
            fy=0.5,
            units="objectBoundingBox",
            spread_method="pad",
            transform=Matrix.identity(),
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
            href="#baseGradient",
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Valid href should be preserved
        assert paint.gradient_id == "#baseGradient"


class TestGradientTransformApplication:
    """Test that gradient transforms are properly applied to coordinates."""

    def test_linear_gradient_with_translation(self):
        """Test linear gradient with translation transform."""
        import math

        # Translation: move gradient by (100, 200)
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=100.0, f=200.0)

        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=50.0,
            y2=0.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Start and end should be translated
        assert paint.start == (100.0, 200.0)  # (0, 0) + (100, 200)
        assert paint.end == (150.0, 200.0)    # (50, 0) + (100, 200)
        assert paint.transform is None  # Transform baked into coordinates

    def test_linear_gradient_with_rotation(self):
        """Test linear gradient with 90-degree rotation."""
        import math

        # 90-degree rotation: cos(90°)=0, sin(90°)=1
        transform = Matrix(a=0.0, b=1.0, c=-1.0, d=0.0, e=0.0, f=0.0)

        resvg_gradient = LinearGradient(
            x1=10.0,
            y1=0.0,
            x2=10.0,
            y2=50.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # After 90° rotation: (x, y) → (-y, x)
        assert paint.start == pytest.approx((0.0, 10.0))   # (-0, 10)
        assert paint.end == pytest.approx((-50.0, 10.0))   # (-50, 10)
        assert paint.transform is None

    def test_linear_gradient_with_scale(self):
        """Test linear gradient with scale transform."""
        # Scale by 2x in X, 3x in Y
        transform = Matrix(a=2.0, b=0.0, c=0.0, d=3.0, e=0.0, f=0.0)

        resvg_gradient = LinearGradient(
            x1=10.0,
            y1=10.0,
            x2=20.0,
            y2=30.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Coordinates should be scaled
        assert paint.start == (20.0, 30.0)   # (10*2, 10*3)
        assert paint.end == (40.0, 90.0)     # (20*2, 30*3)
        assert paint.transform is None

    def test_radial_gradient_with_translation(self):
        """Test radial gradient with translation transform."""
        # Translation: move gradient by (50, 100)
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=50.0, f=100.0)

        resvg_gradient = RadialGradient(
            cx=25.0,
            cy=25.0,
            r=10.0,
            fx=25.0,
            fy=25.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Center should be translated
        assert paint.center == (75.0, 125.0)  # (25, 25) + (50, 100)
        # Radius should be unchanged (translation doesn't scale)
        assert paint.radius == pytest.approx(10.0)
        assert paint.transform is None

    def test_radial_gradient_with_scale(self):
        """Test radial gradient with uniform scale transform."""
        # Uniform scale by 2x
        transform = Matrix(a=2.0, b=0.0, c=0.0, d=2.0, e=0.0, f=0.0)

        resvg_gradient = RadialGradient(
            cx=50.0,
            cy=50.0,
            r=25.0,
            fx=50.0,
            fy=50.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Center should be scaled
        assert paint.center == (100.0, 100.0)  # (50*2, 50*2)
        # Radius should be scaled
        assert paint.radius == pytest.approx(50.0)  # 25*2
        assert paint.transform is None

    def test_radial_gradient_with_non_uniform_scale(self):
        """Test radial gradient with non-uniform scale (ellipse effect)."""
        # Scale by 2x in X, 3x in Y
        transform = Matrix(a=2.0, b=0.0, c=0.0, d=3.0, e=0.0, f=0.0)

        resvg_gradient = RadialGradient(
            cx=10.0,
            cy=10.0,
            r=10.0,
            fx=10.0,
            fy=10.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Severe anisotropy keeps the gradient for raster fallback.
        assert isinstance(paint, RadialGradientPaint)
        assert paint.center == (10.0, 10.0)
        assert paint.radius == pytest.approx(10.0)
        assert paint.transform is not None
        assert paint.policy_decision == "rasterize_nonuniform"

    def test_radial_gradient_with_focal_point_transform(self):
        """Test that focal point is transformed along with center."""
        # Translation by (100, 200)
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=100.0, f=200.0)

        resvg_gradient = RadialGradient(
            cx=50.0,
            cy=50.0,
            r=25.0,
            fx=55.0,  # Focal point offset from center
            fy=55.0,
            units="userSpaceOnUse",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = radial_gradient_to_paint(resvg_gradient)

        # Both center and focal point should be translated
        assert paint.center == (150.0, 250.0)
        assert paint.focal_point == (155.0, 255.0)
        assert paint.transform is None


class TestMatrixConversion:
    """Test Matrix to numpy conversion."""

    def test_identity_matrix_to_numpy(self):
        """Test identity matrix conversion."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _matrix_to_numpy

        # Identity matrix should convert to 3x3 identity
        result = _matrix_to_numpy(Matrix.identity())

        assert result is not None
        assert result.shape == (3, 3)
        assert result[0, 0] == 1.0  # a
        assert result[0, 1] == 0.0  # c
        assert result[0, 2] == 0.0  # e
        assert result[1, 0] == 0.0  # b
        assert result[1, 1] == 1.0  # d
        assert result[1, 2] == 0.0  # f
        assert result[2, 0] == 0.0
        assert result[2, 1] == 0.0
        assert result[2, 2] == 1.0

    def test_translation_matrix_to_numpy(self):
        """Test translation matrix conversion."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _matrix_to_numpy

        # Translation matrix: translate(10, 20)
        matrix = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=10.0, f=20.0)
        result = _matrix_to_numpy(matrix)

        assert result is not None
        assert result[0, 2] == 10.0  # e (tx)
        assert result[1, 2] == 20.0  # f (ty)

    def test_scale_matrix_to_numpy(self):
        """Test scale matrix conversion."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _matrix_to_numpy

        # Scale matrix: scale(2, 3)
        matrix = Matrix(a=2.0, b=0.0, c=0.0, d=3.0, e=0.0, f=0.0)
        result = _matrix_to_numpy(matrix)

        assert result is not None
        assert result[0, 0] == 2.0  # a (sx)
        assert result[1, 1] == 3.0  # d (sy)

    def test_none_matrix_to_numpy(self):
        """Test that None matrix returns None."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _matrix_to_numpy

        result = _matrix_to_numpy(None)
        assert result is None

    def test_gradient_with_transform_applies_to_coordinates(self):
        """Test that gradient with transform applies it to coordinates."""
        # Translation transform
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=50.0, f=100.0)

        resvg_gradient = LinearGradient(
            x1=0.0,
            y1=0.0,
            x2=1.0,
            y2=0.0,
            units="objectBoundingBox",
            spread_method="pad",
            transform=transform,
            stops=(
                GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
                GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
            ),
        )

        paint = linear_gradient_to_paint(resvg_gradient)

        # Transform should be applied to coordinates, so transform field is None
        assert paint.transform is None
        # Coordinates should be transformed
        assert paint.start == (50.0, 100.0)  # (0, 0) + (50, 100)
        assert paint.end == (51.0, 100.0)    # (1, 0) + (50, 100)


class TestColorConversion:
    """Test color conversion helpers."""

    def test_color_hex_conversion(self):
        """Test various color values convert correctly to hex."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _color_to_hex

        # Red
        assert _color_to_hex(Color(r=255, g=0, b=0, a=1.0)) == "FF0000"

        # Green
        assert _color_to_hex(Color(r=0, g=255, b=0, a=1.0)) == "00FF00"

        # Blue
        assert _color_to_hex(Color(r=0, g=0, b=255, a=1.0)) == "0000FF"

        # Gray
        assert _color_to_hex(Color(r=128, g=128, b=128, a=1.0)) == "808080"

        # White
        assert _color_to_hex(Color(r=255, g=255, b=255, a=1.0)) == "FFFFFF"

        # Black
        assert _color_to_hex(Color(r=0, g=0, b=0, a=1.0)) == "000000"

    def test_color_clamping(self):
        """Test that out-of-range colors are clamped."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import _color_to_hex

        # Values > 255 should be clamped
        assert _color_to_hex(Color(r=300, g=0, b=0, a=1.0)) == "FF0000"

        # Negative values should be clamped to 0
        assert _color_to_hex(Color(r=-10, g=0, b=0, a=1.0)) == "000000"
