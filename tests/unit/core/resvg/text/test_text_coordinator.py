"""Unit tests for TextRenderCoordinator."""

from dataclasses import dataclass

from svg2ooxml.core.resvg.text.layout_analyzer import TextLayoutComplexity
from svg2ooxml.core.resvg.text.text_coordinator import (
    TextRenderCoordinator,
)
from svg2ooxml.telemetry.render_decisions import RenderTracer


# Mock classes to simulate resvg structures
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

    color: MockColor | None = None
    opacity: float = 1.0
    reference: object | None = None


@dataclass
class MockTextStyle:
    """Mock text style for testing."""

    font_families: tuple[str, ...] = ("Arial",)
    font_size: float | None = 12.0
    font_style: str | None = None
    font_weight: str | None = None
    text_decoration: str | None = None
    letter_spacing: float | None = None


@dataclass
class MockStrokeStyle:
    """Mock stroke style for testing."""

    color: MockColor | None = None
    width: float | None = None
    opacity: float = 1.0


@dataclass
class MockTextNode:
    """Mock TextNode for testing."""

    text_content: str | None = "Hello"
    text_style: MockTextStyle | None = None
    fill: MockFillStyle | None = None
    stroke: MockStrokeStyle | None = None
    transform: MockTransform | None = None
    attributes: dict = None
    children: list = None
    styles: dict = None
    source: object = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
        if self.children is None:
            self.children = []
        if self.styles is None:
            self.styles = {}
        if self.text_style is None:
            self.text_style = MockTextStyle()
        if self.fill is None:
            self.fill = MockFillStyle(color=MockColor())


class TestTextRenderCoordinator:
    """Test suite for TextRenderCoordinator."""

    def test_coordinator_initialization(self):
        """Test coordinator can be initialized with default parameters."""
        coordinator = TextRenderCoordinator()
        assert coordinator is not None

    def test_coordinator_initialization_with_custom_thresholds(self):
        """Test coordinator can be initialized with custom thresholds."""
        coordinator = TextRenderCoordinator(
            max_rotation_deg=30.0, max_skew_deg=3.0, max_scale_ratio=1.5
        )
        assert coordinator is not None

    def test_simple_text_renders_as_native(self):
        """Test that simple horizontal text renders as native DrawingML."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Simple text")

        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None
        assert "<p:txBody>" in result.content
        assert result.complexity == TextLayoutComplexity.SIMPLE

    def test_simple_text_with_telemetry(self):
        """Test that simple text records telemetry."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Simple text")
        tracer = RenderTracer()

        result = coordinator.render(node, tracer=tracer)

        assert result.strategy == "native"
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].element_type == "text"
        assert decisions[0].strategy == "native"
        assert decisions[0].metadata["complexity"] == TextLayoutComplexity.SIMPLE

    def test_text_with_textpath_falls_back_to_emf(self):
        """Test that text with textPath falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Path text", attributes={"textPath": "#myPath"}
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.content is None
        assert result.complexity == TextLayoutComplexity.HAS_TEXT_PATH

    def test_text_with_vertical_mode_falls_back_to_emf(self):
        """Test that vertical text falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Vertical text", attributes={"writing-mode": "tb-rl"}
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.content is None
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_text_with_complex_transform_falls_back_to_emf(self):
        """Test that text with complex transform falls back to EMF."""
        coordinator = TextRenderCoordinator(max_rotation_deg=30.0)
        # Create a transform with 45° rotation (exceeds 30° threshold)
        import math

        angle = math.radians(45.0)
        transform = MockTransform(
            a=math.cos(angle),
            b=math.sin(angle),
            c=-math.sin(angle),
            d=math.cos(angle),
        )
        node = MockTextNode(text_content="Rotated text", transform=transform)

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.content is None
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

    def test_text_with_complex_positioning_falls_back_to_emf(self):
        """Test that text with per-character positioning falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Positioned text",
            attributes={"x": "10 20 30 40"},  # Multiple x positions
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.content is None
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_emf_fallback_records_telemetry(self):
        """Test that EMF fallback records telemetry with correct metadata."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Complex text", attributes={"textPath": "#path"}
        )
        tracer = RenderTracer()

        result = coordinator.render(node, tracer=tracer)

        assert result.strategy == "emf"
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].element_type == "text"
        assert decisions[0].strategy == "emf"
        assert decisions[0].metadata["complexity"] == TextLayoutComplexity.HAS_TEXT_PATH
        assert "Complex text"[:10] in decisions[0].metadata.get("text_preview", "")

    def test_is_simple_layout_helper_for_simple_text(self):
        """Test is_simple_layout() helper method for simple text."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Simple")

        assert coordinator.is_simple_layout(node) is True

    def test_is_simple_layout_helper_for_complex_text(self):
        """Test is_simple_layout() helper method for complex text."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Complex", attributes={"textPath": "#p"})

        assert coordinator.is_simple_layout(node) is False

    def test_empty_text_renders_as_native(self):
        """Test that empty text still renders as native DrawingML."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="")

        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None
        assert "<a:endParaRPr/>" in result.content

    def test_text_with_simple_translation_renders_as_native(self):
        """Test that text with simple translation renders as native."""
        coordinator = TextRenderCoordinator()
        transform = MockTransform(e=100.0, f=50.0)  # Simple translation
        node = MockTextNode(text_content="Translated", transform=transform)

        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None

    def test_text_with_moderate_rotation_renders_as_native(self):
        """Test that text with moderate rotation (within threshold) renders as native."""
        coordinator = TextRenderCoordinator(max_rotation_deg=45.0)
        import math

        angle = math.radians(30.0)  # 30° is within 45° threshold
        transform = MockTransform(
            a=math.cos(angle),
            b=math.sin(angle),
            c=-math.sin(angle),
            d=math.cos(angle),
        )
        node = MockTextNode(text_content="Rotated 30°", transform=transform)

        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None

    def test_telemetry_includes_text_preview(self):
        """Test that telemetry includes text preview (first 50 chars)."""
        coordinator = TextRenderCoordinator()
        long_text = "A" * 100  # 100 character text
        node = MockTextNode(text_content=long_text)
        tracer = RenderTracer()

        coordinator.render(node, tracer=tracer)

        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        preview = decisions[0].metadata.get("text_preview", "")
        assert len(preview) == 50  # Should be truncated to 50 chars
        assert preview == "A" * 50

    def test_telemetry_optional(self):
        """Test that coordinator works without tracer."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Simple")

        # Should not raise even without tracer
        result = coordinator.render(node, tracer=None)

        assert result.strategy == "native"
        assert result.content is not None

    def test_result_contains_complexity_details(self):
        """Test that result contains human-readable complexity details."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(text_content="Complex", attributes={"textPath": "#p"})

        result = coordinator.render(node)

        assert result.details is not None
        assert "textPath" in result.details or "path" in result.details.lower()

    def test_child_span_with_vertical_text_falls_back_to_emf(self):
        """Test that child spans with vertical text trigger EMF fallback."""
        coordinator = TextRenderCoordinator()

        # Create a child span with vertical text
        child_span = MockTextNode(
            text_content="Child", attributes={"writing-mode": "tb"}
        )
        child_span.tag = "tspan"

        parent = MockTextNode(text_content="Parent", children=[child_span])

        result = coordinator.render(parent)

        assert result.strategy == "emf"
        assert (
            result.complexity
            == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT
        )

    def test_child_span_with_complex_positioning_falls_back_to_emf(self):
        """Test that child spans with complex positioning trigger EMF fallback."""
        coordinator = TextRenderCoordinator()

        # Create a child span with per-character positioning
        child_span = MockTextNode(
            text_content="Child", attributes={"x": "10 20 30"}
        )
        child_span.tag = "tspan"

        parent = MockTextNode(text_content="Parent", children=[child_span])

        result = coordinator.render(parent)

        assert result.strategy == "emf"
        assert (
            result.complexity
            == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING
        )


    # -------------------------------------------------------------------
    # WordArt / textPath tests
    # -------------------------------------------------------------------

    def test_textpath_with_path_points_renders_as_wordart(self):
        """Test that textPath with path points triggers WordArt classification."""
        import math

        from svg2ooxml.ir.text_path import PathPoint

        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Wave text", attributes={"textPath": "#wave"}
        )

        # Create wave-like path points (sinusoidal)
        points = []
        for i in range(50):
            t = i / 49.0
            x = t * 200.0
            y = 30.0 * math.sin(t * 2 * math.pi)
            angle = math.atan2(
                30.0 * 2 * math.pi * math.cos(t * 2 * math.pi) / 49.0,
                200.0 / 49.0,
            )
            points.append(PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=t * 200.0))

        result = coordinator.render(
            node,
            path_points=points,
            path_data="M0,0 C50,30 100,-30 200,0",
        )

        assert result.strategy == "wordart"
        assert result.content is not None
        assert "prstTxWarp" in result.content
        assert result.complexity == TextLayoutComplexity.HAS_TEXT_PATH

    def test_textpath_without_path_points_falls_back_to_emf(self):
        """Test that textPath without path points falls back to EMF."""
        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Path text", attributes={"textPath": "#myPath"}
        )

        result = coordinator.render(node)

        assert result.strategy == "emf"
        assert result.content is None

    def test_textpath_with_low_confidence_falls_back_to_emf(self):
        """Test that textPath with low-confidence classification falls back to EMF."""
        from svg2ooxml.ir.text_path import PathPoint

        # Very high threshold so classification won't meet it
        coordinator = TextRenderCoordinator(wordart_confidence_threshold=0.99)
        node = MockTextNode(
            text_content="Text", attributes={"textPath": "#p"}
        )

        # Simple flat line (classified as textPlain with confidence < 0.99)
        points = [
            PathPoint(x=float(i * 10), y=0.0, tangent_angle=0.0, distance_along_path=float(i * 10))
            for i in range(10)
        ]

        result = coordinator.render(node, path_points=points)

        assert result.strategy == "emf"

    def test_textpath_wordart_records_telemetry(self):
        """Test that WordArt rendering records correct telemetry."""
        from svg2ooxml.ir.text_path import PathPoint

        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Flat text", attributes={"textPath": "#flat"}
        )
        tracer = RenderTracer()

        # Flat line → textPlain with high confidence
        points = [
            PathPoint(x=float(i * 10), y=0.0, tangent_angle=0.0, distance_along_path=float(i * 10))
            for i in range(20)
        ]

        result = coordinator.render(node, tracer=tracer, path_points=points)

        assert result.strategy == "wordart"
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].strategy == "wordart"
        assert decisions[0].metadata.get("preset") is not None
        assert decisions[0].metadata.get("confidence") is not None

    def test_textpath_with_arch_path_classifies_correctly(self):
        """Test that arch-shaped path is classified as textArchUp."""
        import math

        from svg2ooxml.ir.text_path import PathPoint

        coordinator = TextRenderCoordinator()
        node = MockTextNode(
            text_content="Arch text", attributes={"textPath": "#arch"}
        )

        # Create arch path (half circle, upward)
        points = []
        for i in range(30):
            t = i / 29.0
            angle = math.pi * t
            x = 100.0 * math.cos(angle) + 100.0
            y = -80.0 * math.sin(angle)
            tangent = angle + math.pi / 2
            points.append(PathPoint(
                x=x, y=y,
                tangent_angle=tangent,
                distance_along_path=t * math.pi * 100.0,
            ))

        result = coordinator.render(
            node,
            path_points=points,
            path_data="M0,0 A100,80 0 0 1 200,0",
        )

        # Should render as wordart (arch classification)
        if result.strategy == "wordart":
            assert result.content is not None
            assert "prstTxWarp" in result.content


__all__ = ["TestTextRenderCoordinator"]
