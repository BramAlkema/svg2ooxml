"""Integration tests for text EMF fallback scenarios.

These tests verify that the TextRenderCoordinator correctly identifies
complex text layouts and triggers EMF fallback in end-to-end scenarios.
"""

import pytest
from dataclasses import dataclass
from typing import Optional
import math

from svg2ooxml.core.resvg.text.text_coordinator import (
    TextRenderCoordinator,
    TextRenderResult,
)
from svg2ooxml.core.resvg.text.layout_analyzer import TextLayoutComplexity
from svg2ooxml.telemetry.render_decisions import RenderTracer


# Mock structures for integration testing
@dataclass
class MockTransform:
    """Mock transform for testing."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0


@dataclass
class MockColor:
    """Mock color for testing."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0


@dataclass
class MockFillStyle:
    """Mock fill style for testing."""

    color: Optional[MockColor] = None
    opacity: float = 1.0
    reference: Optional[object] = None


@dataclass
class MockTextStyle:
    """Mock text style for testing."""

    font_families: tuple[str, ...] = ("Arial",)
    font_size: Optional[float] = 12.0
    font_style: Optional[str] = None
    font_weight: Optional[str] = None


@dataclass
class MockTextNode:
    """Mock TextNode for testing."""

    text_content: Optional[str] = "Test"
    text_style: Optional[MockTextStyle] = None
    fill: Optional[MockFillStyle] = None
    transform: Optional[MockTransform] = None
    attributes: dict = None
    children: list = None
    tag: str = "text"

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
        if self.children is None:
            self.children = []
        if self.text_style is None:
            self.text_style = MockTextStyle()
        if self.fill is None:
            self.fill = MockFillStyle(color=MockColor())


class TestTextPathFallback:
    """Test EMF fallback for textPath scenarios."""

    def test_text_on_path_falls_back(self):
        """Test that text following a path falls back to EMF."""
        coordinator = TextRenderCoordinator()
        tracer = RenderTracer()

        node = MockTextNode(
            text_content="Text on path",
            attributes={"textPath": "#myPath"},
        )

        result = coordinator.render(node, tracer=tracer)

        # Verify EMF fallback
        assert result.strategy == "emf"
        assert result.content is None
        assert result.complexity == TextLayoutComplexity.HAS_TEXT_PATH

        # Verify telemetry
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].strategy == "emf"
        assert "textPath" in decisions[0].reason.lower() or "path" in decisions[0].reason.lower()

    def test_text_with_href_reference_falls_back(self):
        """Test that text with href reference to path falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Referenced path",
            attributes={"href": "#circlePath"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_TEXT_PATH


class TestVerticalTextFallback:
    """Test EMF fallback for vertical text scenarios."""

    def test_vertical_rl_falls_back(self):
        """Test that vertical right-to-left text falls back to EMF."""
        coordinator = TextRenderCoordinator()
        tracer = RenderTracer()

        node = MockTextNode(
            text_content="縦書き",
            attributes={"writing-mode": "vertical-rl"},
        )

        result = coordinator.render(node, tracer=tracer)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT

        # Verify telemetry captures vertical text
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert "vertical" in decisions[0].reason.lower()

    def test_vertical_lr_falls_back(self):
        """Test that vertical left-to-right text falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Vertical LR",
            attributes={"writing-mode": "vertical-lr"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_tb_rl_falls_back(self):
        """Test that tb-rl writing mode falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="TB-RL text",
            attributes={"writing-mode": "tb-rl"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_text_orientation_upright_falls_back(self):
        """Test that upright text orientation falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Upright",
            attributes={"text-orientation": "upright"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT


class TestComplexTransformFallback:
    """Test EMF fallback for complex transform scenarios."""

    def test_extreme_rotation_falls_back(self):
        """Test that text rotated > 45° falls back to EMF."""
        coordinator = TextRenderCoordinator(max_rotation_deg=45.0)
        tracer = RenderTracer()

        # 60° rotation exceeds threshold
        angle = math.radians(60.0)
        transform = MockTransform(
            a=math.cos(angle),
            b=math.sin(angle),
            c=-math.sin(angle),
            d=math.cos(angle),
        )

        node = MockTextNode(
            text_content="Rotated 60°",
            transform=transform,
        )

        result = coordinator.render(node, tracer=tracer)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

        # Verify telemetry mentions rotation
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert "rotation" in decisions[0].reason.lower() or "transform" in decisions[0].reason.lower()

    def test_high_skew_falls_back(self):
        """Test that text with high skew falls back to EMF."""
        coordinator = TextRenderCoordinator(max_skew_deg=5.0)

        # Create skewed transform (10° skew exceeds 5° threshold)
        skew_angle = math.radians(10.0)
        transform = MockTransform(
            a=1.0,
            b=0.0,
            c=math.tan(skew_angle),
            d=1.0,
        )

        node = MockTextNode(
            text_content="Skewed text",
            transform=transform,
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

    def test_extreme_scale_ratio_falls_back(self):
        """Test that text with extreme scale ratio falls back to EMF."""
        coordinator = TextRenderCoordinator(max_scale_ratio=2.0)

        # 3x horizontal, 1x vertical = ratio of 3.0 (exceeds 2.0 threshold)
        transform = MockTransform(
            a=3.0,
            d=1.0,
        )

        node = MockTextNode(
            text_content="Stretched text",
            transform=transform,
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM


class TestComplexPositioningFallback:
    """Test EMF fallback for complex positioning scenarios."""

    def test_per_character_x_positions_fall_back(self):
        """Test that per-character x positioning falls back to EMF."""
        coordinator = TextRenderCoordinator()
        tracer = RenderTracer()

        node = MockTextNode(
            text_content="SPACED",
            attributes={"x": "10 20 30 40 50 60"},  # One x per character
        )

        result = coordinator.render(node, tracer=tracer)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

        # Verify telemetry
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert "positioning" in decisions[0].reason.lower()

    def test_per_character_y_positions_fall_back(self):
        """Test that per-character y positioning falls back to EMF."""
        coordinator = TextRenderCoordinator()

        node = MockTextNode(
            text_content="WAVE",
            attributes={"y": "10 5 10 5"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_per_character_dx_offsets_fall_back(self):
        """Test that per-character dx offsets fall back to EMF."""
        coordinator = TextRenderCoordinator()

        node = MockTextNode(
            text_content="TEXT",
            attributes={"dx": "0 5 10 15"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_rotate_attribute_falls_back(self):
        """Test that per-character rotate attribute falls back to EMF."""
        coordinator = TextRenderCoordinator()

        node = MockTextNode(
            text_content="SPIN",
            attributes={"rotate": "0 90 180 270"},
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_POSITIONING


class TestChildSpanFallback:
    """Test EMF fallback for complex child span scenarios."""

    def test_child_span_with_vertical_text_falls_back(self):
        """Test that child tspan with vertical text triggers fallback."""
        coordinator = TextRenderCoordinator()
        tracer = RenderTracer()

        child = MockTextNode(
            text_content="Vertical child",
            attributes={"writing-mode": "tb"},
        )
        child.tag = "tspan"

        parent = MockTextNode(
            text_content="Parent with child",
            children=[child],
        )

        result = coordinator.render(parent, tracer=tracer)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT

        # Verify telemetry
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert "child" in decisions[0].reason.lower() or "span" in decisions[0].reason.lower()

    def test_child_span_with_complex_positioning_falls_back(self):
        """Test that child tspan with complex positioning triggers fallback."""
        coordinator = TextRenderCoordinator()

        child = MockTextNode(
            text_content="ABC",
            attributes={"x": "10 20 30"},
        )
        child.tag = "tspan"

        parent = MockTextNode(
            text_content="Parent text",
            children=[child],
        )

        result = coordinator.render(parent)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING

    def test_nested_child_spans_fall_back(self):
        """Test that deeply nested child spans with complexity trigger fallback."""
        coordinator = TextRenderCoordinator()

        # Grandchild with vertical text
        grandchild = MockTextNode(
            text_content="Deep",
            attributes={"writing-mode": "vertical-rl"},
        )
        grandchild.tag = "tspan"

        # Child containing grandchild
        child = MockTextNode(
            text_content="Middle",
            children=[grandchild],
        )
        child.tag = "tspan"

        # Parent containing child
        parent = MockTextNode(
            text_content="Top",
            children=[child],
        )

        result = coordinator.render(parent)

        assert result.strategy == "emf"
        assert result.complexity == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT


class TestMixedScenarios:
    """Test mixed scenarios with multiple complexity factors."""

    def test_textpath_with_vertical_text_falls_back(self):
        """Test that textPath + vertical text falls back (first detected wins)."""
        coordinator = TextRenderCoordinator()

        node = MockTextNode(
            text_content="Complex",
            attributes={
                "textPath": "#path",
                "writing-mode": "vertical-rl",
            },
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        # Either complexity is acceptable (textPath checked first)
        assert result.complexity in [
            TextLayoutComplexity.HAS_TEXT_PATH,
            TextLayoutComplexity.HAS_VERTICAL_TEXT,
        ]

    def test_telemetry_aggregation_across_multiple_texts(self):
        """Test that telemetry correctly aggregates decisions across multiple text elements."""
        coordinator = TextRenderCoordinator()
        tracer = RenderTracer()

        # Simple text (native)
        simple = MockTextNode(text_content="Simple")
        result1 = coordinator.render(simple, tracer=tracer)
        assert result1.strategy == "native"

        # Complex text (EMF)
        complex_node = MockTextNode(
            text_content="Complex",
            attributes={"textPath": "#p"},
        )
        result2 = coordinator.render(complex_node, tracer=tracer)
        assert result2.strategy == "emf"

        # Another simple text (native)
        simple2 = MockTextNode(text_content="Another simple")
        result3 = coordinator.render(simple2, tracer=tracer)
        assert result3.strategy == "native"

        # Verify telemetry captured all 3 decisions
        decisions = tracer.get_decisions()
        assert len(decisions) == 3
        assert decisions[0].strategy == "native"
        assert decisions[1].strategy == "emf"
        assert decisions[2].strategy == "native"

        # Verify summary statistics
        json_data = tracer.to_json()
        assert "summary" in json_data
        assert '"native_count": 2' in json_data or '"native_count":2' in json_data
        assert '"emf_count": 1' in json_data or '"emf_count":1' in json_data


__all__ = [
    "TestTextPathFallback",
    "TestVerticalTextFallback",
    "TestComplexTransformFallback",
    "TestComplexPositioningFallback",
    "TestChildSpanFallback",
    "TestMixedScenarios",
]
