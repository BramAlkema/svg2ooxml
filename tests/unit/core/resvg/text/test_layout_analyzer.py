"""Unit tests for TextLayoutAnalyzer."""

import math
from dataclasses import dataclass, field

from svg2ooxml.core.resvg.text.layout_analyzer import (
    LayoutAnalysisResult,
    TextLayoutAnalyzer,
    TextLayoutComplexity,
)


# Mock classes to simulate resvg structures
@dataclass
class MockMatrix:
    """Mock Matrix for testing transforms."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @staticmethod
    def identity():
        return MockMatrix()

    @staticmethod
    def translate(tx: float, ty: float):
        return MockMatrix(e=tx, f=ty)

    @staticmethod
    def rotate(degrees: float):
        rad = math.radians(degrees)
        return MockMatrix(
            a=math.cos(rad),
            b=math.sin(rad),
            c=-math.sin(rad),
            d=math.cos(rad),
        )

    @staticmethod
    def scale(sx: float, sy: float):
        return MockMatrix(a=sx, d=sy)

    @staticmethod
    def skew_x(degrees: float):
        return MockMatrix(c=math.tan(math.radians(degrees)))


@dataclass
class MockTextNode:
    """Mock TextNode for testing."""

    tag: str = "text"
    id: str | None = None
    text_content: str | None = None
    attributes: dict = field(default_factory=dict)
    styles: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    transform: MockMatrix | None = None


class TestTextLayoutAnalyzer:
    """Test suite for TextLayoutAnalyzer."""

    def test_simple_text_is_plain(self):
        """Test that simple horizontal text is detected as plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(text_content="Hello World")

        assert analyzer.is_plain_text_layout(node) is True
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.SIMPLE

    def test_text_with_identity_transform_is_plain(self):
        """Test that text with identity transform is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.identity(),
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_translation_is_plain(self):
        """Test that text with simple translation is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.translate(100, 50),
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_small_rotation_is_plain(self):
        """Test that text with small rotation (< 45°) is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.rotate(30),  # 30° is within threshold
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_large_rotation_is_complex(self):
        """Test that text with large rotation (> 45°) is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.rotate(60),  # 60° exceeds threshold
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

    def test_text_with_uniform_scale_is_plain(self):
        """Test that text with uniform scale is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.scale(2.0, 2.0),  # Uniform scale
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_non_uniform_scale_is_complex(self):
        """Test that text with non-uniform scale is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.scale(3.0, 1.0),  # Ratio = 3.0, exceeds threshold 2.0
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

    def test_text_with_moderate_scale_ratio_is_plain(self):
        """Test that text with moderate non-uniform scale is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.scale(1.8, 1.0),  # Ratio = 1.8, within threshold 2.0
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_skew_is_complex(self):
        """Test that text with skew is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.skew_x(15),  # 15° skew exceeds threshold
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM

    def test_text_path_is_complex(self):
        """Test that textPath is detected as complex."""
        analyzer = TextLayoutAnalyzer()

        # Mock child node with textPath tag
        @dataclass
        class MockTextPathNode:
            tag: str = "textPath"

        node = MockTextNode(
            text_content="Hello",
            children=[MockTextPathNode()],
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_TEXT_PATH

    def test_text_path_via_attribute_is_complex(self):
        """Test that textPath via attributes is detected as complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"textPath": "#somePath"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_TEXT_PATH

    def test_vertical_text_tb_is_complex(self):
        """Test that vertical text (tb writing mode) is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"writing-mode": "tb"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_vertical_text_tb_rl_is_complex(self):
        """Test that vertical text (tb-rl writing mode) is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"writing-mode": "tb-rl"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_vertical_text_via_orientation_is_complex(self):
        """Test that vertical text via text-orientation is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"text-orientation": "upright"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_text_with_rotate_attribute_is_complex(self):
        """Test that text with rotate attribute is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"rotate": "0 30 60 90"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_text_with_multiple_x_positions_is_complex(self):
        """Test that text with per-character x positions is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"x": "10 20 30 40 50"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_text_with_single_x_position_is_plain(self):
        """Test that text with single x position is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"x": "10"},
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_text_with_multiple_y_positions_is_complex(self):
        """Test that text with per-character y positions is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"y": "10 20 30 40 50"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_text_with_multiple_dx_offsets_is_complex(self):
        """Test that text with per-character dx offsets is complex."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"dx": "1 2 3 4 5"},
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_COMPLEX_POSITIONING

    def test_text_with_single_dx_offset_is_plain(self):
        """Test that text with single dx offset is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"dx": "5"},
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_custom_rotation_threshold(self):
        """Test that custom rotation threshold works."""
        analyzer = TextLayoutAnalyzer(max_rotation_deg=30.0)
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.rotate(40),  # 40° exceeds custom threshold
        )

        assert analyzer.is_plain_text_layout(node) is False

    def test_custom_scale_ratio_threshold(self):
        """Test that custom scale ratio threshold works."""
        analyzer = TextLayoutAnalyzer(max_scale_ratio=1.5)
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.scale(2.0, 1.0),  # Ratio 2.0 exceeds custom threshold 1.5
        )

        assert analyzer.is_plain_text_layout(node) is False

    def test_custom_skew_threshold(self):
        """Test that custom skew threshold works."""
        analyzer = TextLayoutAnalyzer(max_skew_deg=10.0)
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.skew_x(3),  # 3° within custom threshold 10°
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_has_kerning_detects_font_feature(self):
        """Test that kerning detection flags explicit kerning settings."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(text_content="Hello", styles={"font-feature-settings": "'kern' 1"})

        assert analyzer._has_kerning(node) is True

    def test_has_ligatures_detects_variant(self):
        """Test that ligature detection flags font-variant-ligatures."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(text_content="Hello", attributes={"font-variant-ligatures": "discretionary-ligatures"})

        assert analyzer._has_ligatures(node) is True

    def test_has_glyph_reuse_detects_feature_settings(self):
        """Test that advanced font feature settings are detected."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(text_content="Hello", styles={"font-feature-settings": "'calt' 1"})

        assert analyzer._has_glyph_reuse(node) is True

    def test_empty_attributes_is_plain(self):
        """Test that text with no attributes is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={},
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_none_transform_is_plain(self):
        """Test that text with None transform is plain."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            transform=None,
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_case_insensitive_writing_mode_detection(self):
        """Test that writing-mode detection is case-insensitive."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"writing-mode": "TB-RL"},  # Uppercase
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_VERTICAL_TEXT

    def test_child_span_with_vertical_text_is_complex(self):
        """Test that child tspan with vertical text is detected as complex."""
        analyzer = TextLayoutAnalyzer()

        # Create child tspan with vertical writing mode
        child_span = MockTextNode(
            tag="tspan",
            text_content="World",
            attributes={"writing-mode": "vertical-rl"},
        )

        # Parent node is simple, but child has complexity
        node = MockTextNode(
            text_content="Hello ",
            children=[child_span],
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT

    def test_child_span_with_complex_positioning_is_complex(self):
        """Test that child tspan with complex positioning is detected."""
        analyzer = TextLayoutAnalyzer()

        # Create child tspan with per-character positioning
        child_span = MockTextNode(
            tag="tspan",
            text_content="World",
            attributes={"x": "10 20 30 40 50"},
        )

        node = MockTextNode(
            text_content="Hello ",
            children=[child_span],
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING

    def test_nested_child_spans_detected_recursively(self):
        """Test that nested child spans are checked recursively."""
        analyzer = TextLayoutAnalyzer()

        # Create deeply nested span with complexity
        grandchild_span = MockTextNode(
            tag="tspan",
            text_content="!",
            attributes={"rotate": "45 90"},  # varying rotation = complex
        )

        child_span = MockTextNode(
            tag="tspan",
            text_content="World",
            children=[grandchild_span],
        )

        node = MockTextNode(
            text_content="Hello ",
            children=[child_span],
        )

        assert analyzer.is_plain_text_layout(node) is False
        assert analyzer.get_complexity_reason(node) == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING

    def test_child_span_with_simple_attributes_is_plain(self):
        """Test that child tspan with simple attributes is plain."""
        analyzer = TextLayoutAnalyzer()

        # Create child tspan with only single x/y (not per-character)
        child_span = MockTextNode(
            tag="tspan",
            text_content="World",
            attributes={"x": "50", "y": "100"},
        )

        node = MockTextNode(
            text_content="Hello ",
            children=[child_span],
        )

        assert analyzer.is_plain_text_layout(node) is True

    def test_analyze_returns_structured_result_for_simple_text(self):
        """Test that analyze() returns LayoutAnalysisResult for simple text."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(text_content="Hello World")

        result = analyzer.analyze(node)

        assert isinstance(result, LayoutAnalysisResult)
        assert result.is_plain is True
        assert result.complexity == TextLayoutComplexity.SIMPLE
        assert result.details is None

    def test_analyze_returns_structured_result_for_complex_text(self):
        """Test that analyze() returns detailed result for complex text."""
        analyzer = TextLayoutAnalyzer()
        node = MockTextNode(
            text_content="Hello",
            attributes={"writing-mode": "vertical-rl"},
        )

        result = analyzer.analyze(node)

        assert isinstance(result, LayoutAnalysisResult)
        assert result.is_plain is False
        assert result.complexity == TextLayoutComplexity.HAS_VERTICAL_TEXT
        assert result.details == "Text uses vertical writing mode"

    def test_analyze_includes_threshold_values_in_transform_details(self):
        """Test that analyze() includes threshold values in details."""
        analyzer = TextLayoutAnalyzer(
            max_rotation_deg=30.0,
            max_skew_deg=3.0,
            max_scale_ratio=1.5,
        )
        node = MockTextNode(
            text_content="Hello",
            transform=MockMatrix.rotate(40),  # Exceeds 30° threshold
        )

        result = analyzer.analyze(node)

        assert result.is_plain is False
        assert result.complexity == TextLayoutComplexity.HAS_COMPLEX_TRANSFORM
        assert "rotation>30.0°" in result.details
        assert "skew>3.0°" in result.details
        assert "scale_ratio>1.5" in result.details

    def test_analyze_provides_telemetry_friendly_output(self):
        """Test that analyze() can be used for telemetry/logging."""
        analyzer = TextLayoutAnalyzer()

        # Create child span with complexity
        child_span = MockTextNode(
            tag="tspan",
            text_content="World",
            attributes={"dx": "1 2 3 4 5"},
        )

        node = MockTextNode(
            text_content="Hello ",
            children=[child_span],
        )

        result = analyzer.analyze(node)

        # Should provide both machine-readable and human-readable output
        assert result.is_plain is False
        assert result.complexity == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING
        assert "Child span" in result.details
        assert "per-character positioning" in result.details

    def test_non_text_children_ignored_in_span_checking(self):
        """Test that non-text children are ignored during span checking."""
        analyzer = TextLayoutAnalyzer()

        # Create non-text child (e.g., metadata)
        @dataclass
        class MockMetadataNode:
            tag: str = "metadata"

        metadata_child = MockMetadataNode()

        node = MockTextNode(
            text_content="Hello",
            children=[metadata_child],
        )

        # Should be plain since non-text children are ignored
        assert analyzer.is_plain_text_layout(node) is True
