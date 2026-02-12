"""Unit tests for ResvgShapeAdapter."""

from __future__ import annotations

import pytest

# Skip entire module if resvg is not available
pytest.importorskip("svg2ooxml.core.resvg.usvg_tree")

from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.geometry.path_normalizer import NormalizedPath, PathCommand
from svg2ooxml.core.resvg.parser.presentation import Presentation
from svg2ooxml.core.resvg.usvg_tree import (
    CircleNode,
    EllipseNode,
    GroupNode,
    LineNode,
    PathNode,
    PolyNode,
    RectNode,
)
from svg2ooxml.drawingml.bridges.resvg_shape_adapter import (
    ResvgShapeAdapter,
    ResvgShapeAdapterError,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment


def default_presentation() -> Presentation:
    """Create a default Presentation object for testing."""
    return Presentation(
        fill=None,
        stroke=None,
        stroke_width=None,
        stroke_dasharray=None,
        stroke_dashoffset=None,
        stroke_linecap=None,
        stroke_linejoin=None,
        stroke_miterlimit=None,
        fill_opacity=None,
        stroke_opacity=None,
        opacity=None,
        transform=None,
        font_family=None,
        font_size=None,
        font_style=None,
        font_weight=None,
    )


class TestResvgShapeAdapterRect:
    """Test rectangle conversion."""

    def test_simple_rect(self):
        """Test basic rectangle with no rounding."""
        adapter = ResvgShapeAdapter()
        rect = RectNode(
            tag="rect",
            id="test-rect",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=10.0,
            y=20.0,
            width=100.0,
            height=50.0,
            rx=0.0,
            ry=0.0,
        )

        segments = adapter.from_rect_node(rect)

        # Should produce 4 segments: 4 lines forming a closed rectangle
        assert len(segments) == 4
        assert all(isinstance(seg, LineSegment) for seg in segments)

        # Check corners (top-left → top-right → bottom-right → bottom-left → top-left)
        assert segments[0].start.x == 10.0
        assert segments[0].start.y == 20.0
        assert segments[0].end.x == 110.0  # x + width
        assert segments[0].end.y == 20.0

        assert segments[1].start.x == 110.0
        assert segments[1].start.y == 20.0
        assert segments[1].end.x == 110.0
        assert segments[1].end.y == 70.0  # y + height

        assert segments[2].start.x == 110.0
        assert segments[2].start.y == 70.0
        assert segments[2].end.x == 10.0
        assert segments[2].end.y == 70.0

        assert segments[3].start.x == 10.0
        assert segments[3].start.y == 70.0
        assert segments[3].end.x == 10.0
        assert segments[3].end.y == 20.0  # Close

    def test_zero_size_rect(self):
        """Test that zero-size rectangles produce no segments."""
        adapter = ResvgShapeAdapter()
        rect = RectNode(
            tag="rect",
            id="empty",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=0.0,
            y=0.0,
            width=0.0,
            height=0.0,
        )

        segments = adapter.from_rect_node(rect)
        assert len(segments) == 0

    def test_rounded_rect(self):
        """Test rounded rectangle (currently approximated with lines)."""
        adapter = ResvgShapeAdapter()
        rect = RectNode(
            tag="rect",
            id="rounded",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=0.0,
            y=0.0,
            width=100.0,
            height=50.0,
            rx=10.0,
            ry=10.0,
        )

        segments = adapter.from_rect_node(rect)

        # Should produce rounded corners with Bezier arcs (4 lines + 4 Beziers)
        assert len(segments) == 8

        # Should have 4 line segments (straight edges)
        line_segments = [seg for seg in segments if isinstance(seg, LineSegment)]
        assert len(line_segments) == 4

        # Should have 4 Bezier segments (rounded corners)
        bezier_segments = [seg for seg in segments if isinstance(seg, BezierSegment)]
        assert len(bezier_segments) == 4


class TestResvgShapeAdapterCircle:
    """Test circle conversion."""

    def test_simple_circle(self):
        """Test basic circle."""
        adapter = ResvgShapeAdapter()
        circle = CircleNode(
            tag="circle",
            id="test-circle",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=50.0,
            cy=50.0,
            r=25.0,
        )

        segments = adapter.from_circle_node(circle)

        # Should produce 4 segments: 4 cubic Beziers (one per quadrant)
        assert len(segments) == 4
        assert all(isinstance(seg, BezierSegment) for seg in segments)

        # First segment should start at rightmost position (3 o'clock)
        assert segments[0].start.x == pytest.approx(75.0)  # cx + r
        assert segments[0].start.y == pytest.approx(50.0)  # cy

    def test_zero_radius_circle(self):
        """Test that zero-radius circles produce no segments."""
        adapter = ResvgShapeAdapter()
        circle = CircleNode(
            tag="circle",
            id="empty",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=50.0,
            cy=50.0,
            r=0.0,
        )

        segments = adapter.from_circle_node(circle)
        assert len(segments) == 0


class TestResvgShapeAdapterEllipse:
    """Test ellipse conversion."""

    def test_simple_ellipse(self):
        """Test basic ellipse."""
        adapter = ResvgShapeAdapter()
        ellipse = EllipseNode(
            tag="ellipse",
            id="test-ellipse",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=50.0,
            cy=50.0,
            rx=40.0,
            ry=20.0,
        )

        segments = adapter.from_ellipse_node(ellipse)

        # Should produce 4 segments: 4 cubic Beziers
        assert len(segments) == 4
        assert all(isinstance(seg, BezierSegment) for seg in segments)

        # First segment should start at rightmost position
        assert segments[0].start.x == pytest.approx(90.0)  # cx + rx
        assert segments[0].start.y == pytest.approx(50.0)  # cy

    def test_zero_radius_ellipse(self):
        """Test that zero-radius ellipses produce no segments."""
        adapter = ResvgShapeAdapter()
        ellipse = EllipseNode(
            tag="ellipse",
            id="empty",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=50.0,
            cy=50.0,
            rx=0.0,
            ry=10.0,
        )

        segments = adapter.from_ellipse_node(ellipse)
        assert len(segments) == 0


class TestResvgShapeAdapterLine:
    """Test line conversion."""

    def test_simple_line(self):
        """Test basic line."""
        adapter = ResvgShapeAdapter()
        line = LineNode(
            tag="line",
            id="test-line",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x1=0.0,
            y1=0.0,
            x2=10.0,
            y2=5.0,
        )

        segments = adapter.from_line_node(line)

        assert len(segments) == 1
        assert isinstance(segments[0], LineSegment)
        assert segments[0].start.x == 0.0
        assert segments[0].start.y == 0.0
        assert segments[0].end.x == 10.0
        assert segments[0].end.y == 5.0

    def test_zero_length_line(self):
        """Test that zero-length lines produce no segments."""
        adapter = ResvgShapeAdapter()
        line = LineNode(
            tag="line",
            id="empty-line",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x1=1.0,
            y1=1.0,
            x2=1.0,
            y2=1.0,
        )

        segments = adapter.from_line_node(line)
        assert len(segments) == 0


class TestResvgShapeAdapterPoly:
    """Test polyline/polygon conversion."""

    def test_polyline(self):
        """Test polyline segments are not closed."""
        adapter = ResvgShapeAdapter()
        polyline = PolyNode(
            tag="polyline",
            id="test-polyline",
            presentation=default_presentation(),
            attributes={},
            styles={},
            points=(0.0, 0.0, 10.0, 0.0, 10.0, 5.0),
        )

        segments = adapter.from_poly_node(polyline)

        assert len(segments) == 2
        assert segments[0].start.x == 0.0
        assert segments[0].start.y == 0.0
        assert segments[0].end.x == 10.0
        assert segments[0].end.y == 0.0
        assert segments[1].start.x == 10.0
        assert segments[1].start.y == 0.0
        assert segments[1].end.x == 10.0
        assert segments[1].end.y == 5.0

    def test_polygon(self):
        """Test polygon segments are closed."""
        adapter = ResvgShapeAdapter()
        polygon = PolyNode(
            tag="polygon",
            id="test-polygon",
            presentation=default_presentation(),
            attributes={},
            styles={},
            points=(0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0),
        )

        segments = adapter.from_poly_node(polygon)

        assert len(segments) == 4
        assert segments[0].start.x == 0.0
        assert segments[0].start.y == 0.0
        assert segments[-1].end.x == 0.0
        assert segments[-1].end.y == 0.0


class TestResvgShapeAdapterPath:
    """Test path conversion."""

    def test_simple_path(self):
        """Test path with basic commands."""
        adapter = ResvgShapeAdapter()

        # Create simple path: M 10 10 L 50 10 L 50 50 Z
        commands = (
            PathCommand(command="M", points=(10.0, 10.0)),
            PathCommand(command="L", points=(50.0, 10.0)),
            PathCommand(command="L", points=(50.0, 50.0)),
            PathCommand(command="Z", points=()),
        )
        normalized = NormalizedPath(
            commands=commands,
            transform=Matrix.identity(),
            stroke_width=None,
        )

        path = PathNode(
            tag="path",
            id="test-path",
            presentation=default_presentation(),
            attributes={},
            styles={},
            d="M 10 10 L 50 10 L 50 50 Z",
            geometry=normalized,
        )

        segments = adapter.from_path_node(path)

        # Should have at least one segment (MoveTo doesn't create segments)
        assert len(segments) > 0
        # First should be LineSegment (from first LineTo primitive)
        assert isinstance(segments[0], LineSegment)
        # Should start from MoveTo position
        assert segments[0].start.x == 10.0
        assert segments[0].start.y == 10.0

    def test_path_without_geometry(self):
        """Test that paths without geometry raise error."""
        adapter = ResvgShapeAdapter()
        path = PathNode(
            tag="path",
            id="no-geom",
            presentation=default_presentation(),
            attributes={},
            styles={},
            d="M 0 0 L 10 10",
            geometry=None,  # No normalized geometry
        )

        with pytest.raises(ResvgShapeAdapterError, match="has no geometry"):
            adapter.from_path_node(path)


class TestResvgShapeAdapterGeneric:
    """Test generic from_node dispatcher."""

    def test_from_node_rect(self):
        """Test generic dispatcher with RectNode."""
        adapter = ResvgShapeAdapter()
        rect = RectNode(
            tag="rect",
            id="test",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=0.0,
            y=0.0,
            width=50.0,
            height=50.0,
        )

        segments = adapter.from_node(rect)
        assert len(segments) > 0

    def test_from_node_circle(self):
        """Test generic dispatcher with CircleNode."""
        adapter = ResvgShapeAdapter()
        circle = CircleNode(
            tag="circle",
            id="test",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=25.0,
            cy=25.0,
            r=10.0,
        )

        segments = adapter.from_node(circle)
        assert len(segments) > 0

    def test_from_node_unsupported(self):
        """Test that unsupported node types raise error."""
        adapter = ResvgShapeAdapter()
        group = GroupNode(
            tag="g",
            id="group",
            presentation=default_presentation(),
            attributes={},
            styles={},
        )

        with pytest.raises(ResvgShapeAdapterError, match="Unsupported node type: GroupNode"):
            adapter.from_node(group)


class TestResvgShapeAdapterPrimitives:
    """Test low-level primitive conversion."""

    def test_primitives_moveto_lineto(self):
        """Test MoveTo and LineTo primitive conversion."""
        from svg2ooxml.core.resvg.geometry.primitives import LineTo, MoveTo

        adapter = ResvgShapeAdapter()
        primitives = (
            MoveTo(10.0, 20.0),
            LineTo(30.0, 40.0),
            LineTo(50.0, 20.0),
        )

        segments = adapter._primitives_to_segments(primitives)

        # MoveTo doesn't create a segment, just sets current position
        # So we expect only 2 segments (the two LineTo commands)
        assert len(segments) == 2

        # First LineTo should start from MoveTo position (10, 20)
        assert isinstance(segments[0], LineSegment)
        assert segments[0].start.x == 10.0
        assert segments[0].start.y == 20.0
        assert segments[0].end.x == 30.0
        assert segments[0].end.y == 40.0

        # Second LineTo should start from previous end
        assert isinstance(segments[1], LineSegment)
        assert segments[1].start.x == 30.0
        assert segments[1].start.y == 40.0
        assert segments[1].end.x == 50.0
        assert segments[1].end.y == 20.0

    def test_primitives_cubic_curve(self):
        """Test CubicCurve primitive conversion."""
        from svg2ooxml.core.resvg.geometry.primitives import CubicCurve, MoveTo

        adapter = ResvgShapeAdapter()
        primitives = (
            MoveTo(0.0, 0.0),
            CubicCurve(10.0, 20.0, 30.0, 40.0, 50.0, 50.0),
        )

        segments = adapter._primitives_to_segments(primitives)

        # MoveTo doesn't create segment, only CubicCurve does
        assert len(segments) == 1
        assert isinstance(segments[0], BezierSegment)

        # Check Bezier control points and start position (from MoveTo)
        bezier = segments[0]
        assert bezier.start.x == 0.0
        assert bezier.start.y == 0.0
        assert bezier.control1.x == 10.0
        assert bezier.control1.y == 20.0
        assert bezier.control2.x == 30.0
        assert bezier.control2.y == 40.0
        assert bezier.end.x == 50.0
        assert bezier.end.y == 50.0

    def test_primitives_close_path(self):
        """ClosePath now yields an explicit closing segment."""
        from svg2ooxml.core.resvg.geometry.primitives import ClosePath, LineTo, MoveTo

        adapter = ResvgShapeAdapter()
        primitives = (
            MoveTo(0.0, 0.0),
            LineTo(10.0, 0.0),
            LineTo(10.0, 10.0),
            ClosePath(),
        )

        segments = adapter._primitives_to_segments(primitives)

        # ClosePath now produces a closing segment back to the MoveTo origin
        assert len(segments) == 3
        assert isinstance(segments[-1], LineSegment)
        assert segments[-1].start.x == 10.0
        assert segments[-1].start.y == 10.0
        assert segments[-1].end.x == 0.0
        assert segments[-1].end.y == 0.0


class TestResvgShapeAdapterTransforms:
    """Test transform application for all shape types."""

    def test_rect_with_translation(self):
        """Test rectangle with translation transform."""
        adapter = ResvgShapeAdapter()
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=50.0, f=100.0)

        rect = RectNode(
            tag="rect",
            id="rect-translate",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=10.0,
            y=20.0,
            width=80.0,
            height=60.0,
            rx=0.0,
            ry=0.0,
            transform=transform,
        )

        segments = adapter.from_rect_node(rect)

        # Rectangle should be translated by (50, 100)
        # Original top-left: (10, 20) → (60, 120)
        assert len(segments) == 4
        assert segments[0].start.x == pytest.approx(60.0)
        assert segments[0].start.y == pytest.approx(120.0)
        # Top-right: (90, 20) → (140, 120)
        assert segments[0].end.x == pytest.approx(140.0)
        assert segments[0].end.y == pytest.approx(120.0)

    def test_rect_with_rotation(self):
        """Test rectangle with 90-degree rotation."""
        adapter = ResvgShapeAdapter()
        # 90-degree rotation: cos(90°)=0, sin(90°)=1
        transform = Matrix(a=0.0, b=1.0, c=-1.0, d=0.0, e=0.0, f=0.0)

        rect = RectNode(
            tag="rect",
            id="rect-rotate",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=0.0,
            y=0.0,
            width=10.0,
            height=20.0,
            rx=0.0,
            ry=0.0,
            transform=transform,
        )

        segments = adapter.from_rect_node(rect)

        # After 90° rotation: (x, y) → (-y, x)
        # Top-left (0, 0) → (0, 0)
        assert len(segments) == 4
        assert segments[0].start.x == pytest.approx(0.0)
        assert segments[0].start.y == pytest.approx(0.0)
        # Top-right (10, 0) → (0, 10)
        assert segments[0].end.x == pytest.approx(0.0)
        assert segments[0].end.y == pytest.approx(10.0)

    def test_rect_with_scale(self):
        """Test rectangle with uniform scale."""
        adapter = ResvgShapeAdapter()
        # Scale by 2x
        transform = Matrix(a=2.0, b=0.0, c=0.0, d=2.0, e=0.0, f=0.0)

        rect = RectNode(
            tag="rect",
            id="rect-scale",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=10.0,
            y=20.0,
            width=30.0,
            height=40.0,
            rx=0.0,
            ry=0.0,
            transform=transform,
        )

        segments = adapter.from_rect_node(rect)

        # All coordinates should be scaled by 2
        # Top-left: (10, 20) → (20, 40)
        assert len(segments) == 4
        assert segments[0].start.x == pytest.approx(20.0)
        assert segments[0].start.y == pytest.approx(40.0)
        # Top-right: (40, 20) → (80, 40)
        assert segments[0].end.x == pytest.approx(80.0)
        assert segments[0].end.y == pytest.approx(40.0)

    def test_circle_with_translation(self):
        """Test circle with translation transform."""
        adapter = ResvgShapeAdapter()
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=100.0, f=200.0)

        circle = CircleNode(
            tag="circle",
            id="circle-translate",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=50.0,
            cy=50.0,
            r=25.0,
            transform=transform,
        )

        segments = adapter.from_circle_node(circle)

        # Circle should be translated by (100, 200)
        # Original rightmost point: (75, 50) → (175, 250)
        assert len(segments) == 4
        # First segment starts at rightmost point (3 o'clock)
        assert segments[0].start.x == pytest.approx(175.0)
        assert segments[0].start.y == pytest.approx(250.0)

    def test_ellipse_with_scale(self):
        """Test ellipse with non-uniform scale."""
        adapter = ResvgShapeAdapter()
        # Scale by 2x in X, 3x in Y
        transform = Matrix(a=2.0, b=0.0, c=0.0, d=3.0, e=0.0, f=0.0)

        ellipse = EllipseNode(
            tag="ellipse",
            id="ellipse-scale",
            presentation=default_presentation(),
            attributes={},
            styles={},
            cx=10.0,
            cy=20.0,
            rx=5.0,
            ry=10.0,
            transform=transform,
        )

        segments = adapter.from_ellipse_node(ellipse)

        # Center: (10, 20) → (20, 60)
        # Rightmost point: (15, 20) → (30, 60)
        assert len(segments) == 4
        assert segments[0].start.x == pytest.approx(30.0)
        assert segments[0].start.y == pytest.approx(60.0)

    def test_path_with_transform(self):
        """Test path with transform applied to all coordinates."""
        adapter = ResvgShapeAdapter()
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=50.0, f=100.0)

        # Create a simple geometry
        commands = (
            PathCommand(command="M", points=(0.0, 0.0)),
            PathCommand(command="L", points=(10.0, 0.0)),
            PathCommand(command="L", points=(10.0, 10.0)),
            PathCommand(command="Z", points=()),
        )
        geometry = NormalizedPath(
            commands=commands,
            transform=Matrix.identity(),
            stroke_width=None,
        )

        # Create path node with transform
        path_node = PathNode(
            tag="path",
            id="path-transform",
            presentation=default_presentation(),
            attributes={},
            styles={},
            d="M 0 0 L 10 0 L 10 10 Z",
            geometry=geometry,
            transform=transform,
        )

        segments = adapter.from_path_node(path_node)

        # All points should be translated by (50, 100)
        # First line: (0, 0) → (10, 0) becomes (50, 100) → (60, 100)
        assert len(segments) == 3
        assert segments[0].start.x == pytest.approx(50.0)
        assert segments[0].start.y == pytest.approx(100.0)
        assert segments[0].end.x == pytest.approx(60.0)
        assert segments[0].end.y == pytest.approx(100.0)
        # Closing segment returns to the origin of the subpath (translated)
        assert segments[-1].start.x == pytest.approx(60.0)
        assert segments[-1].start.y == pytest.approx(110.0)
        assert segments[-1].end.x == pytest.approx(50.0)
        assert segments[-1].end.y == pytest.approx(100.0)

    def test_identity_transform_not_applied(self):
        """Test that identity transform is skipped (optimization)."""
        adapter = ResvgShapeAdapter()
        # Identity transform
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)

        rect = RectNode(
            tag="rect",
            id="rect-identity",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=10.0,
            y=20.0,
            width=30.0,
            height=40.0,
            rx=0.0,
            ry=0.0,
            transform=transform,
        )

        segments = adapter.from_rect_node(rect)

        # Coordinates should be unchanged
        assert len(segments) == 4
        assert segments[0].start.x == 10.0
        assert segments[0].start.y == 20.0

    def test_no_transform_attribute(self):
        """Test that shapes without transform attribute work correctly."""
        adapter = ResvgShapeAdapter()

        rect = RectNode(
            tag="rect",
            id="rect-notransform",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=10.0,
            y=20.0,
            width=30.0,
            height=40.0,
            rx=0.0,
            ry=0.0,
            transform=None,
        )

        segments = adapter.from_rect_node(rect)

        # Should work without transform
        assert len(segments) == 4
        assert segments[0].start.x == 10.0
        assert segments[0].start.y == 20.0

    def test_bezier_segment_transform(self):
        """Test that BezierSegment control points are transformed."""
        adapter = ResvgShapeAdapter()
        # Translation
        transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=10.0, f=20.0)

        # Create a rounded rectangle to test Bezier segments
        rect = RectNode(
            tag="rect",
            id="rect-rounded-transform",
            presentation=default_presentation(),
            attributes={},
            styles={},
            x=0.0,
            y=0.0,
            width=100.0,
            height=100.0,
            rx=20.0,
            ry=20.0,
            transform=transform,
        )

        segments = adapter.from_rect_node(rect)

        # Should have some BezierSegments for rounded corners
        bezier_segments = [s for s in segments if isinstance(s, BezierSegment)]
        assert len(bezier_segments) > 0

        # Check that all control points are translated
        for seg in bezier_segments:
            # All coordinates should be shifted by (10, 20)
            assert seg.start.x >= 10.0
            assert seg.start.y >= 20.0
            assert seg.control1.x >= 10.0
            assert seg.control1.y >= 20.0
            assert seg.control2.x >= 10.0
            assert seg.control2.y >= 20.0
            assert seg.end.x >= 10.0
            assert seg.end.y >= 20.0
