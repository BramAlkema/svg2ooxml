"""Tests for resvg routing infrastructure in shape converters.

This module verifies that:
1. Shape converters check geometry_mode policy
2. Routing correctly delegates to resvg adapters when enabled
3. Legacy path is used when resvg mode is disabled or unavailable
4. Resvg-only mode returns None when conversion fails
"""

from unittest.mock import Mock, patch

from lxml import etree

from svg2ooxml.core.ir.shape_converters import ShapeConversionMixin
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.scene import Path


class MockConverter(ShapeConversionMixin):
    """Mock converter with necessary attributes for testing."""

    def __init__(self):
        self._logger = Mock()
        self._resvg_tree = None
        self._resvg_element_lookup = {}

    def _policy_options(self, category):
        """Mock policy options method."""
        if category == "geometry":
            return getattr(self, "_geometry_policy", {})
        return {}

    def _bitmap_fallback_limits(self, options):
        return (None, None)

    def _resolve_clip_ref(self, element):
        return None

    def _resolve_mask_ref(self, element):
        return (None, None)

    def _attach_policy_metadata(self, metadata, category, extra=None):
        pass

    def _process_mask_metadata(self, ir_object):
        pass

    def _trace_geometry_decision(self, element, decision, metadata):
        pass

    def _apply_marker_metadata(self, element, metadata):
        pass

    def _build_marker_shapes(self, element, path_object):
        return []

    @staticmethod
    def _normalize_href_reference(href):
        if not href:
            return None
        token = href.strip()
        return token[1:] if token.startswith("#") else token


class TestResvgRouting:
    """Test resvg routing infrastructure."""

    def test_can_use_resvg_ignores_geometry_mode(self):
        """Test that _can_use_resvg ignores geometry_mode when resvg data exists."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "legacy"}
        converter._resvg_tree = Mock()
        element = etree.Element("circle")
        converter._resvg_element_lookup[element] = Mock()

        assert converter._can_use_resvg(element) is True

    def test_can_use_resvg_returns_false_when_no_resvg_tree(self):
        """Test that _can_use_resvg returns False when resvg tree is None."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = None
        element = etree.Element("circle")

        assert converter._can_use_resvg(element) is False

    def test_can_use_resvg_returns_false_when_element_not_in_lookup(self):
        """Test that _can_use_resvg returns False when element not in lookup."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()
        element = etree.Element("circle")
        # Element not in lookup

        assert converter._can_use_resvg(element) is False

    def test_can_use_resvg_returns_true_when_all_conditions_met(self):
        """Test that _can_use_resvg returns True when all conditions are met."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()
        element = etree.Element("circle")
        converter._resvg_element_lookup[element] = Mock()

        assert converter._can_use_resvg(element) is True

    def test_convert_circle_returns_none_when_resvg_disabled(self):
        """Test that _convert_circle returns None when resvg is disabled."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "legacy"}

        element = etree.Element("circle")
        element.set("cx", "50")
        element.set("cy", "50")
        element.set("r", "25")

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            result = converter._convert_circle(element=element, coord_space=coord_space)
            assert result is None

    def test_convert_circle_tries_resvg_when_enabled(self):
        """Test that _convert_circle tries resvg path when enabled."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("circle")
        element.set("cx", "50")
        element.set("cy", "50")
        element.set("r", "25")

        # Create mock resvg node
        mock_node = Mock()
        mock_node.__class__.__name__ = "CircleNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_circle_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 10))
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_circle(element=element, coord_space=coord_space)

                # Should have tried resvg adapter (called with GlobalTransformProxy wrapping mock_node)
                mock_adapter.from_circle_node.assert_called_once()
                # Result should be a Path from resvg
                assert isinstance(result, Path)

    def test_convert_circle_returns_none_when_resvg_fails(self):
        """Test that _convert_circle returns None when resvg conversion fails."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("circle")
        element.set("cx", "50")
        element.set("cy", "50")
        element.set("r", "25")

        # Create mock resvg node
        mock_node = Mock()
        mock_node.__class__.__name__ = "CircleNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                # Make resvg adapter raise exception
                mock_adapter.from_circle_node.side_effect = Exception("Resvg failed")
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_circle(element=element, coord_space=coord_space)

                # Should have tried resvg adapter
                mock_adapter.from_circle_node.assert_called_once()
                # Resvg-only mode returns None on failure
                assert result is None

    def test_convert_ellipse_routing(self):
        """Test that _convert_ellipse routing works similarly to circle."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("ellipse")
        element.set("cx", "50")
        element.set("cy", "50")
        element.set("rx", "30")
        element.set("ry", "20")

        mock_node = Mock()
        mock_node.__class__.__name__ = "EllipseNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_ellipse_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 10))
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_ellipse(element=element, coord_space=coord_space)

                mock_adapter.from_ellipse_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_rect_routing(self):
        """Test that _convert_rect routing works for rectangles."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("rect")
        element.set("x", "10")
        element.set("y", "10")
        element.set("width", "50")
        element.set("height", "30")

        mock_node = Mock()
        mock_node.__class__.__name__ = "RectNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_rect_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 10))
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_rect(element=element, coord_space=coord_space)

                mock_adapter.from_rect_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_path_routing(self):
        """Test that _convert_path routing works for paths."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("path")
        element.set("d", "M 10 10 L 20 20")

        mock_node = Mock()
        mock_node.__class__.__name__ = "PathNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_path_node.return_value = [
                    LineSegment(Point(10, 10), Point(20, 20))
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_path(element=element, coord_space=coord_space)

                mock_adapter.from_path_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_line_uses_resvg_when_resvg_only(self):
        """Test that _convert_line routes to resvg in resvg-only mode."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("line")
        element.set("x1", "0")
        element.set("y1", "0")
        element.set("x2", "10")
        element.set("y2", "5")

        mock_node = Mock()
        mock_node.__class__.__name__ = "LineNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_line_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 5))
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_line(element=element, coord_space=coord_space)

                mock_adapter.from_line_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_polyline_uses_resvg_when_resvg_only(self):
        """Test that _convert_polyline routes to resvg in resvg-only mode."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("polyline")
        element.set("points", "0,0 10,0 10,5")

        mock_node = Mock()
        mock_node.__class__.__name__ = "PolyNode"
        mock_node.tag = "polyline"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_poly_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 0)),
                    LineSegment(Point(10, 0), Point(10, 5)),
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_polyline(element=element, coord_space=coord_space)

                mock_adapter.from_poly_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_polygon_uses_resvg_when_resvg_only(self):
        """Test that _convert_polygon routes to resvg in resvg-only mode."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("polygon")
        element.set("points", "0,0 10,0 10,10 0,10")

        mock_node = Mock()
        mock_node.__class__.__name__ = "PolyNode"
        mock_node.tag = "polygon"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch(
                "svg2ooxml.drawingml.bridges.resvg_shape_adapter.ResvgShapeAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.from_poly_node.return_value = [
                    LineSegment(Point(0, 0), Point(10, 0)),
                    LineSegment(Point(10, 0), Point(10, 10)),
                    LineSegment(Point(10, 10), Point(0, 10)),
                    LineSegment(Point(0, 10), Point(0, 0)),
                ]
                mock_adapter_class.return_value = mock_adapter

                result = converter._convert_polygon(element=element, coord_space=coord_space)

                mock_adapter.from_poly_node.assert_called_once()
                assert isinstance(result, Path)

    def test_convert_via_resvg_returns_none_for_unsupported_node_type(self):
        """Test that _convert_via_resvg returns None for unsupported node types."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg"}
        converter._resvg_tree = Mock()

        element = etree.Element("polygon")

        # Mock unsupported node type
        mock_node = Mock()
        mock_node.__class__.__name__ = "UnsupportedNode"
        mock_node.fill = None
        mock_node.stroke = None
        mock_node.use_source = None
        mock_node.source = None
        converter._resvg_element_lookup[element] = mock_node

        coord_space = CoordinateSpace()

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            result = converter._convert_via_resvg(element, coord_space)

            assert result is None

    def test_convert_degenerate_primitives_fallback_to_path_when_resvg_fails(self):
        """Degenerate primitives should fall back to minimal native paths."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        coord_space = CoordinateSpace()
        cases = [
            ("rect", {"x": "1", "y": "2", "width": "0", "height": "0"}, "_convert_rect"),
            ("circle", {"cx": "3", "cy": "4", "r": "0"}, "_convert_circle"),
            ("ellipse", {"cx": "5", "cy": "6", "rx": "0", "ry": "0"}, "_convert_ellipse"),
            ("line", {"x1": "7", "y1": "8", "x2": "7", "y2": "8"}, "_convert_line"),
        ]

        with patch("svg2ooxml.core.ir.shape_converters.styles_runtime") as mock_styles:
            mock_style = Mock()
            mock_style.fill = None
            mock_style.stroke = None
            mock_style.opacity = 1.0
            mock_style.effects = []
            mock_style.metadata = {}
            mock_styles.extract_style.return_value = mock_style

            with patch.object(converter, "_convert_via_resvg", return_value=None):
                for tag, attrs, method_name in cases:
                    element = etree.Element(tag)
                    for key, value in attrs.items():
                        element.set(key, value)
                    converter._resvg_element_lookup[element] = Mock()

                    result = getattr(converter, method_name)(element=element, coord_space=coord_space)

                    assert isinstance(result, Path), f"{tag} should emit Path fallback"
                    assert len(result.segments) == 1

    def test_convert_use_falls_back_to_expand_use_when_image_target_resvg_conversion_fails(self):
        """<use> should expand image targets when mapped resvg node cannot be converted."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("use")
        element.set("href", "#img-target")
        converter._element_index = {"img-target": etree.Element("image")}
        converter._resvg_element_lookup[element] = Mock()
        converter.expand_use = Mock(return_value=["expanded-child"])

        with patch.object(converter, "_convert_via_resvg", return_value=None):
            with patch.object(converter, "_trace_resvg_only_miss") as mock_trace:
                result = converter._convert_use(
                    element=element,
                    coord_space=CoordinateSpace(),
                    current_navigation=None,
                    traverse_callback=lambda *_: [],
                )

        assert result == ["expanded-child"]
        converter.expand_use.assert_called_once()
        mock_trace.assert_not_called()

    def test_convert_use_traces_miss_when_image_target_resvg_and_expansion_both_fail(self):
        """<use> should still trace a miss when all conversion paths fail."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("use")
        element.set("href", "#img-target")
        converter._element_index = {"img-target": etree.Element("image")}
        converter._resvg_element_lookup[element] = Mock()
        converter.expand_use = Mock(return_value=[])

        with patch.object(converter, "_convert_via_resvg", return_value=None):
            with patch.object(converter, "_trace_resvg_only_miss") as mock_trace:
                result = converter._convert_use(
                    element=element,
                    coord_space=CoordinateSpace(),
                    current_navigation=None,
                    traverse_callback=lambda *_: [],
                )

        assert result is None
        mock_trace.assert_called_once_with(element, "resvg_conversion_failed")

    def test_convert_use_non_image_target_does_not_expand_fallback(self):
        """Only image targets should use expansion fallback in resvg-only mode."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "resvg-only"}
        converter._resvg_tree = Mock()

        element = etree.Element("use")
        element.set("href", "#rect-target")
        converter._element_index = {"rect-target": etree.Element("rect")}
        converter._resvg_element_lookup[element] = Mock()
        converter.expand_use = Mock(return_value=["expanded-child"])

        with patch.object(converter, "_convert_via_resvg", return_value=None):
            with patch.object(converter, "_trace_resvg_only_miss") as mock_trace:
                result = converter._convert_use(
                    element=element,
                    coord_space=CoordinateSpace(),
                    current_navigation=None,
                    traverse_callback=lambda *_: [],
                )

        assert result is None
        converter.expand_use.assert_not_called()
        mock_trace.assert_called_once_with(element, "resvg_conversion_failed")
