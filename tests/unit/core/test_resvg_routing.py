"""Tests for resvg routing infrastructure in shape converters.

This module verifies that:
1. Shape converters check geometry_mode policy
2. Routing correctly delegates to resvg adapters when enabled
3. Legacy path is used when resvg mode is disabled or unavailable
4. Fallback to legacy works when resvg conversion fails
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from lxml import etree

from svg2ooxml.core.ir.shape_converters import ShapeConversionMixin
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point, LineSegment
from svg2ooxml.ir.scene import Path
from svg2ooxml.common.geometry import Matrix2D


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


class TestResvgRouting:
    """Test resvg routing infrastructure."""

    def test_can_use_resvg_returns_false_when_mode_is_legacy(self):
        """Test that _can_use_resvg returns False when geometry_mode is legacy."""
        converter = MockConverter()
        converter._geometry_policy = {"geometry_mode": "legacy"}
        converter._resvg_tree = Mock()
        element = etree.Element("circle")
        converter._resvg_element_lookup[element] = Mock()

        assert converter._can_use_resvg(element) is False

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

    def test_convert_circle_uses_legacy_when_resvg_disabled(self):
        """Test that _convert_circle uses legacy path when resvg is disabled."""
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

            # Should produce a Circle or Path (legacy behavior)
            assert result is not None

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

                # Should have tried resvg adapter
                mock_adapter.from_circle_node.assert_called_once_with(mock_node)
                # Result should be a Path from resvg
                assert isinstance(result, Path)

    def test_convert_circle_falls_back_to_legacy_when_resvg_fails(self):
        """Test that _convert_circle falls back to legacy when resvg conversion fails."""
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
                # Should have fallen back to legacy and still produced result
                assert result is not None

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

                mock_adapter.from_ellipse_node.assert_called_once_with(mock_node)
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

                mock_adapter.from_rect_node.assert_called_once_with(mock_node)
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

                mock_adapter.from_path_node.assert_called_once_with(mock_node)
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
