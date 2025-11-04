"""Unit tests for DrawingMLTextGenerator."""

import pytest
from dataclasses import dataclass, field
from typing import Optional

from svg2ooxml.core.resvg.text.drawingml_generator import (
    DrawingMLTextGenerator,
    _parse_font_weight,
    _map_font_weight,
    _map_font_style,
    _color_to_hex,
    _font_size_pt_to_drawingml,
    DRAWINGML_HUNDREDTHS_PER_POINT,
)
from svg2ooxml.common.units.scalars import EMU_PER_POINT
from svg2ooxml.color.models import Color as CentralizedColor


# Mock classes to simulate resvg structures
@dataclass
class MockColor:
    """Mock Color for testing."""

    r: float
    g: float
    b: float
    a: float = 1.0


@dataclass
class MockTextStyle:
    """Mock TextStyle for testing."""

    font_families: tuple[str, ...]
    font_size: Optional[float]
    font_style: Optional[str]
    font_weight: Optional[str]


@dataclass
class MockFillStyle:
    """Mock FillStyle for testing."""

    color: Optional[MockColor]
    opacity: float = 1.0
    reference: Optional[object] = None


@dataclass
class MockTextNode:
    """Mock TextNode for testing."""

    tag: str = "text"
    text_content: Optional[str] = None
    text_style: Optional[MockTextStyle] = None
    fill: Optional[MockFillStyle] = None
    attributes: dict = field(default_factory=dict)


class TestHelperFunctions:
    """Test suite for helper functions."""

    def test_centralized_color_integration(self):
        """Test that color conversion uses centralized Color model.

        This verifies that _color_to_hex() properly converts resvg Colors
        to centralized Colors and uses the centralized to_hex() method for
        consistent color handling across the codebase.
        """
        # Test that centralized Color has the to_hex method
        centralized = CentralizedColor(r=1.0, g=0.0, b=0.0)
        assert hasattr(centralized, "to_hex")

        # Test that the hex output is correct (with rounding and clamping)
        hex_output = centralized.to_hex(include_alpha=False)
        assert hex_output == "#ff0000"  # Lowercase with hash prefix

        # Test that our _color_to_hex removes hash and uppercases
        mock_color = MockColor(r=1.0, g=0.0, b=0.0)
        assert _color_to_hex(mock_color) == "FF0000"

    def test_font_size_pt_to_drawingml_twelve(self):
        """Test 12pt converts to 1200."""
        assert _font_size_pt_to_drawingml(12.0) == 1200

    def test_font_size_pt_to_drawingml_fractional(self):
        """Test fractional point size."""
        # 10.5pt = 1050
        assert _font_size_pt_to_drawingml(10.5) == 1050

    def test_font_size_pt_to_drawingml_rounding(self):
        """Test that font size uses rounding."""
        # 12.999 * 100 = 1299.9, rounds to 1300
        assert _font_size_pt_to_drawingml(12.999) == 1300

    def test_font_size_pt_to_drawingml_minimum(self):
        """Test minimum font size of 1."""
        # Very small size rounds to 0, but clamped to 1
        assert _font_size_pt_to_drawingml(0.001) == 1

    def test_font_size_pt_to_drawingml_zero_raises(self):
        """Test that zero font size raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            _font_size_pt_to_drawingml(0.0)

    def test_font_size_pt_to_drawingml_negative_raises(self):
        """Test that negative font size raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            _font_size_pt_to_drawingml(-10.0)

    def test_constants_defined(self):
        """Test that conversion constants are properly defined."""
        assert DRAWINGML_HUNDREDTHS_PER_POINT == 100

    def test_unit_conversion_relationship(self):
        """Test the relationship between DrawingML hundredths and EMU_PER_POINT.

        This verifies that the DrawingML constant is properly related to the
        centralized unit conversion system:
        - 1 point = 100 hundredths (DrawingML spec)
        - 1 point = 12,700 EMUs (centralized constant)
        """
        # Verify EMU_PER_POINT constant
        assert EMU_PER_POINT == 12_700

        # Verify DrawingML constant
        assert DRAWINGML_HUNDREDTHS_PER_POINT == 100

        # Verify relationship: 100 hundredths = 12,700 EMUs (both represent 1 point)
        # This means 1 hundredth = 127 EMUs
        emu_per_hundredth = EMU_PER_POINT / DRAWINGML_HUNDREDTHS_PER_POINT
        assert emu_per_hundredth == 127.0

    def test_map_font_weight_bold(self):
        """Test that 'bold' maps to True."""
        assert _map_font_weight("bold") is True
        assert _map_font_weight("BOLD") is True
        assert _map_font_weight("  bold  ") is True

    def test_map_font_weight_bolder(self):
        """Test that 'bolder' maps to True."""
        assert _map_font_weight("bolder") is True

    def test_map_font_weight_normal(self):
        """Test that 'normal' maps to False."""
        assert _map_font_weight("normal") is False
        assert _map_font_weight("lighter") is False

    def test_map_font_weight_numeric_bold(self):
        """Test that numeric weights >= 700 map to True."""
        assert _map_font_weight("700") is True
        assert _map_font_weight("800") is True
        assert _map_font_weight("900") is True

    def test_map_font_weight_numeric_normal(self):
        """Test that numeric weights < 700 map to False."""
        assert _map_font_weight("400") is False
        assert _map_font_weight("100") is False
        assert _map_font_weight("600") is False

    def test_map_font_weight_none(self):
        """Test that None maps to False."""
        assert _map_font_weight(None) is False

    def test_map_font_weight_invalid(self):
        """Test that invalid values map to False."""
        assert _map_font_weight("invalid") is False
        assert _map_font_weight("") is False

    def test_map_font_style_italic(self):
        """Test that 'italic' maps to True."""
        assert _map_font_style("italic") is True
        assert _map_font_style("ITALIC") is True

    def test_map_font_style_oblique(self):
        """Test that 'oblique' maps to True."""
        assert _map_font_style("oblique") is True

    def test_map_font_style_normal(self):
        """Test that 'normal' maps to False."""
        assert _map_font_style("normal") is False

    def test_map_font_style_none(self):
        """Test that None maps to False."""
        assert _map_font_style(None) is False

    def test_color_to_hex_red(self):
        """Test red color conversion."""
        color = MockColor(r=1.0, g=0.0, b=0.0)
        assert _color_to_hex(color) == "FF0000"

    def test_color_to_hex_green(self):
        """Test green color conversion."""
        color = MockColor(r=0.0, g=1.0, b=0.0)
        assert _color_to_hex(color) == "00FF00"

    def test_color_to_hex_blue(self):
        """Test blue color conversion."""
        color = MockColor(r=0.0, g=0.0, b=1.0)
        assert _color_to_hex(color) == "0000FF"

    def test_color_to_hex_gray(self):
        """Test gray color conversion."""
        color = MockColor(r=0.5, g=0.5, b=0.5)
        # 0.5 × 255 = 127.5, rounds to 128 (0x80)
        assert _color_to_hex(color) == "808080"

    def test_color_to_hex_none(self):
        """Test None color returns black."""
        assert _color_to_hex(None) == "000000"

    def test_color_to_hex_clamping(self):
        """Test that out-of-range values are clamped."""
        color = MockColor(r=1.5, g=-0.5, b=0.5)
        # r clamped to 255, g clamped to 0, b rounded to 128
        assert _color_to_hex(color) == "FF0080"

    def test_color_to_hex_rounding_fidelity(self):
        """Test that rounding preserves color fidelity."""
        # 0.999 should round to 255 (0xFF), not floor to 254 (0xFE)
        color = MockColor(r=0.999, g=0.999, b=0.999)
        assert _color_to_hex(color) == "FFFFFF"

        # 0.996 → 254 (rounds to 254.18)
        color = MockColor(r=0.996, g=0.996, b=0.996)
        assert _color_to_hex(color) == "FEFEFE"

        # Test rounding boundary: 0.5/255 = 0.00196
        # Values >= 0.00196 round up to 1
        color = MockColor(r=0.002, g=0.002, b=0.002)
        assert _color_to_hex(color) == "010101"


class TestDrawingMLTextGenerator:
    """Test suite for DrawingMLTextGenerator."""

    def test_generate_empty_text(self):
        """Test generating DrawingML for empty text."""
        generator = DrawingMLTextGenerator()
        node = MockTextNode(text_content="")

        xml = generator.generate_text_body(node)

        assert "<p:txBody>" in xml
        assert "<a:bodyPr/>" in xml
        assert "<a:lstStyle/>" in xml
        assert "<a:p>" in xml
        assert "<a:endParaRPr/>" in xml
        assert "</a:p>" in xml
        assert "</p:txBody>" in xml

    def test_generate_simple_text(self):
        """Test generating DrawingML for simple unstyled text."""
        generator = DrawingMLTextGenerator()
        node = MockTextNode(text_content="Hello World")

        xml = generator.generate_text_body(node)

        assert "<p:txBody>" in xml
        assert "<a:r>" in xml
        assert "<a:t>Hello World</a:t>" in xml
        assert "</a:r>" in xml

    def test_generate_text_with_font_family(self):
        """Test font family mapping."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Arial", "Helvetica"),
            font_size=None,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        assert '<a:latin typeface="Arial"/>' in xml

    def test_generate_text_with_font_size(self):
        """Test font size mapping (points × 100)."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=12.0,  # 12 points
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # 12 points = 1200 hundredths
        assert 'sz="1200"' in xml

    def test_generate_text_with_large_font_size(self):
        """Test large font size (24pt)."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=24.0,  # 24 points
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # 24 points = 2400 hundredths
        assert 'sz="2400"' in xml

    def test_generate_text_with_bold(self):
        """Test bold font weight mapping."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=None,
            font_style=None,
            font_weight="bold",
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        assert 'b="1"' in xml

    def test_generate_text_with_italic(self):
        """Test italic font style mapping."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=None,
            font_style="italic",
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        assert 'i="1"' in xml

    def test_generate_text_with_color(self):
        """Test text color mapping."""
        generator = DrawingMLTextGenerator()
        color = MockColor(r=1.0, g=0.0, b=0.0)  # Red
        fill_style = MockFillStyle(color=color)
        node = MockTextNode(
            text_content="Hello",
            fill=fill_style,
        )

        xml = generator.generate_text_body(node)

        assert '<a:solidFill>' in xml
        assert '<a:srgbClr val="FF0000"/>' in xml
        assert '</a:solidFill>' in xml

    def test_generate_text_with_all_properties(self):
        """Test text with all properties combined."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Arial",),
            font_size=14.0,
            font_style="italic",
            font_weight="bold",
        )
        color = MockColor(r=0.2, g=0.4, b=0.6)  # Blue-gray
        fill_style = MockFillStyle(color=color)
        node = MockTextNode(
            text_content="Styled Text",
            text_style=text_style,
            fill=fill_style,
        )

        xml = generator.generate_text_body(node)

        # Check all properties are present
        assert 'sz="1400"' in xml  # 14pt
        assert 'b="1"' in xml  # Bold
        assert 'i="1"' in xml  # Italic
        assert '<a:latin typeface="Arial"/>' in xml
        assert '<a:solidFill>' in xml
        assert '<a:srgbClr val="336699"/>' in xml  # Hex color

    def test_generate_text_escapes_special_characters(self):
        """Test that special XML characters are escaped."""
        generator = DrawingMLTextGenerator()
        node = MockTextNode(text_content="A < B & C > D")

        xml = generator.generate_text_body(node)

        assert "<a:t>A &lt; B &amp; C &gt; D</a:t>" in xml

    def test_generate_text_with_no_style(self):
        """Test text with no style information."""
        generator = DrawingMLTextGenerator()
        node = MockTextNode(
            text_content="Plain",
            text_style=None,
            fill=None,
        )

        xml = generator.generate_text_body(node)

        # Should have empty properties
        assert "<a:rPr/>" in xml
        assert "<a:t>Plain</a:t>" in xml

    def test_generate_text_with_numeric_font_weight(self):
        """Test numeric font weight (700)."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=None,
            font_style=None,
            font_weight="700",
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        assert 'b="1"' in xml

    def test_generate_text_with_light_font_weight(self):
        """Test light font weight (300) does not set bold."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=None,
            font_style=None,
            font_weight="300",
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should not have bold flag
        assert 'b="1"' not in xml

    def test_generate_multiple_font_families_uses_first(self):
        """Test that multiple font families use the first one."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Arial", "Helvetica", "sans-serif"),
            font_size=None,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should use first family only
        assert '<a:latin typeface="Arial"/>' in xml
        assert "Helvetica" not in xml

    def test_generate_text_validates_structure(self):
        """Test that generated XML has correct structure."""
        generator = DrawingMLTextGenerator()
        node = MockTextNode(text_content="Test")

        xml = generator.generate_text_body(node)

        # Validate proper nesting
        assert xml.startswith("<p:txBody>")
        assert xml.endswith("</p:txBody>")
        assert xml.count("<p:txBody>") == 1
        assert xml.count("</p:txBody>") == 1
        assert xml.count("<a:p>") == 1
        assert xml.count("</a:p>") == 1

    def test_generate_text_with_fractional_font_size(self):
        """Test fractional font size (10.5pt)."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=10.5,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # 10.5 points = 1050 hundredths
        assert 'sz="1050"' in xml

    def test_generate_text_with_font_size_rounding(self):
        """Test that font size uses rounding for fidelity."""
        generator = DrawingMLTextGenerator()
        # 12.999pt should round to 1300 hundredths, not floor to 1299
        text_style = MockTextStyle(
            font_families=(),
            font_size=12.999,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # 12.999 × 100 = 1299.9, rounds to 1300
        assert 'sz="1300"' in xml

    def test_generate_text_with_zero_font_size_ignored(self):
        """Test that zero font size is ignored."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=0.0,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should not have sz attribute
        assert 'sz=' not in xml

    def test_generate_text_with_negative_font_size_ignored(self):
        """Test that negative font size is ignored."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=(),
            font_size=-10.0,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should not have sz attribute
        assert 'sz=' not in xml

    def test_generate_text_with_font_family_containing_ampersand(self):
        """Test that font family with ampersand is properly escaped."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Rock & Roll",),
            font_size=None,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should escape ampersand in attribute value
        # quoteattr produces "Rock &amp; Roll" or 'Rock &amp; Roll'
        assert "Rock &amp; Roll" in xml
        assert '<a:latin typeface=' in xml

    def test_generate_text_with_font_family_containing_quotes(self):
        """Test that font family with quotes is properly escaped."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=('Font "Name"',),
            font_size=None,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should escape quotes in attribute value
        # quoteattr will use single quotes when value contains double quotes
        assert '<a:latin typeface=' in xml
        # The escaped version should be present
        assert "&quot;" in xml or "'" in xml

    def test_generate_text_with_font_family_containing_less_than(self):
        """Test that font family with < is properly escaped."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Font<Name>",),
            font_size=None,
            font_style=None,
            font_weight=None,
        )
        node = MockTextNode(
            text_content="Hello",
            text_style=text_style,
        )

        xml = generator.generate_text_body(node)

        # Should escape < and > in attribute value
        assert "&lt;" in xml
        assert "&gt;" in xml
        assert '<a:latin typeface=' in xml


class TestParseFontWeight:
    """Test suite for _parse_font_weight helper function."""

    def test_parse_normal_weight(self):
        """Test that 'normal' returns 400."""
        assert _parse_font_weight("normal") == 400

    def test_parse_bold_weight(self):
        """Test that 'bold' returns 700."""
        assert _parse_font_weight("bold") == 700

    def test_parse_bolder_weight(self):
        """Test that 'bolder' returns 700."""
        assert _parse_font_weight("bolder") == 700

    def test_parse_lighter_weight(self):
        """Test that 'lighter' returns 300."""
        assert _parse_font_weight("lighter") == 300

    def test_parse_numeric_weight_400(self):
        """Test parsing numeric weight 400."""
        assert _parse_font_weight("400") == 400

    def test_parse_numeric_weight_700(self):
        """Test parsing numeric weight 700."""
        assert _parse_font_weight("700") == 700

    def test_parse_numeric_weight_100(self):
        """Test parsing numeric weight 100."""
        assert _parse_font_weight("100") == 100

    def test_parse_numeric_weight_900(self):
        """Test parsing numeric weight 900."""
        assert _parse_font_weight("900") == 900

    def test_parse_numeric_weight_clamping_high(self):
        """Test that weights > 900 are clamped to 900."""
        assert _parse_font_weight("1000") == 900

    def test_parse_numeric_weight_clamping_low(self):
        """Test that weights < 100 are clamped to 100."""
        assert _parse_font_weight("50") == 100

    def test_parse_none_weight(self):
        """Test that None returns 400 (normal)."""
        assert _parse_font_weight(None) == 400

    def test_parse_invalid_weight(self):
        """Test that invalid weight returns 400 (normal)."""
        assert _parse_font_weight("invalid") == 400

    def test_parse_weight_with_whitespace(self):
        """Test that weight with whitespace is handled."""
        assert _parse_font_weight("  bold  ") == 700
        assert _parse_font_weight("  700  ") == 700


class TestFontServiceIntegration:
    """Test suite for font service integration."""

    def test_generator_initialization_without_services(self):
        """Test that generator can be initialized without services."""
        generator = DrawingMLTextGenerator()
        assert generator._font_service is None
        assert generator._embedding_engine is None

    def test_generator_initialization_with_services(self):
        """Test that generator accepts font services."""
        from unittest.mock import Mock

        font_service = Mock()
        embedding_engine = Mock()

        generator = DrawingMLTextGenerator(
            font_service=font_service,
            embedding_engine=embedding_engine,
        )

        assert generator._font_service is font_service
        assert generator._embedding_engine is embedding_engine

    def test_resolve_font_without_service(self):
        """Test that resolve_font returns None without font service."""
        generator = DrawingMLTextGenerator()
        text_style = MockTextStyle(
            font_families=("Arial",),
            font_size=12.0,
            font_style="normal",
            font_weight="400",
        )
        node = MockTextNode(text_content="Test", text_style=text_style)

        result = generator.resolve_font(node)
        assert result is None

    def test_resolve_font_without_text_style(self):
        """Test that resolve_font returns None without text style."""
        from unittest.mock import Mock

        font_service = Mock()
        generator = DrawingMLTextGenerator(font_service=font_service)
        node = MockTextNode(text_content="Test", text_style=None)

        result = generator.resolve_font(node)
        assert result is None

    def test_resolve_font_builds_correct_query(self):
        """Test that resolve_font builds correct FontQuery."""
        from unittest.mock import Mock, MagicMock

        font_service = Mock()
        font_service.find_font = MagicMock(return_value=None)

        generator = DrawingMLTextGenerator(font_service=font_service)

        text_style = MockTextStyle(
            font_families=("Arial", "sans-serif"),
            font_size=12.0,
            font_style="italic",
            font_weight="bold",
        )
        node = MockTextNode(text_content="Test", text_style=text_style)

        generator.resolve_font(node, fallback_chain=("Helvetica",))

        # Verify find_font was called
        assert font_service.find_font.called
        query = font_service.find_font.call_args[0][0]

        # Verify query properties
        assert query.family == "Arial"  # First family
        assert query.weight == 700  # bold
        assert query.style == "italic"
        assert query.fallback_chain == ("Helvetica",)

    def test_resolve_font_returns_match(self):
        """Test that resolve_font returns FontMatch from service."""
        from unittest.mock import Mock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        mock_match = MockFontMatch(
            family="Arial",
            path="/fonts/arial.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )

        font_service = Mock()
        font_service.find_font = Mock(return_value=mock_match)

        generator = DrawingMLTextGenerator(font_service=font_service)

        text_style = MockTextStyle(
            font_families=("Arial",),
            font_size=12.0,
            font_style="normal",
            font_weight="400",
        )
        node = MockTextNode(text_content="Test", text_style=text_style)

        result = generator.resolve_font(node)
        assert result is mock_match
        assert result.family == "Arial"

    def test_embed_font_without_engine(self):
        """Test that embed_font returns None without embedding engine."""
        from unittest.mock import Mock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        generator = DrawingMLTextGenerator()
        match = MockFontMatch(
            family="Arial",
            path="/fonts/arial.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )
        node = MockTextNode(text_content="Test")

        result = generator.embed_font(node, match)
        assert result is None

    def test_embed_font_without_text_content(self):
        """Test that embed_font returns None without text content."""
        from unittest.mock import Mock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        embedding_engine = Mock()
        generator = DrawingMLTextGenerator(embedding_engine=embedding_engine)

        match = MockFontMatch(
            family="Arial",
            path="/fonts/arial.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )
        node = MockTextNode(text_content="")  # Empty text

        result = generator.embed_font(node, match)
        assert result is None

    def test_embed_font_builds_correct_request(self):
        """Test that embed_font builds correct FontEmbeddingRequest."""
        from unittest.mock import Mock, MagicMock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        embedding_engine = Mock()
        embedding_engine.subset_font = MagicMock(return_value=None)

        generator = DrawingMLTextGenerator(embedding_engine=embedding_engine)

        match = MockFontMatch(
            family="Arial",
            path="/fonts/arial.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )
        node = MockTextNode(text_content="Hello")

        generator.embed_font(node, match)

        # Verify subset_font was called
        assert embedding_engine.subset_font.called
        request = embedding_engine.subset_font.call_args[0][0]

        # Verify request properties
        assert request.font_path == "/fonts/arial.ttf"
        assert set(request.characters) == {"H", "e", "l", "o"}
        assert request.preserve_hinting is True
        assert request.subset_strategy == "glyph"

    def test_embed_font_passes_web_font_data(self):
        """Test that embed_font passes through web font data."""
        from unittest.mock import Mock, MagicMock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        embedding_engine = Mock()
        embedding_engine.subset_font = MagicMock(return_value=None)

        generator = DrawingMLTextGenerator(embedding_engine=embedding_engine)

        font_data = b"fake font bytes"
        match = MockFontMatch(
            family="CustomFont",
            path="data:font/woff2;base64,...",
            weight=400,
            style="normal",
            found_via="webfont",
            metadata={"font_data": font_data},
        )
        node = MockTextNode(text_content="Test")

        generator.embed_font(node, match)

        # Verify font_data was passed through in metadata
        request = embedding_engine.subset_font.call_args[0][0]
        assert "font_data" in request.metadata
        assert request.metadata["font_data"] is font_data

    def test_embed_font_returns_result(self):
        """Test that embed_font returns FontEmbeddingResult from engine."""
        from unittest.mock import Mock
        from dataclasses import dataclass

        @dataclass
        class MockFontMatch:
            family: str
            path: str
            weight: int
            style: str
            found_via: str
            metadata: dict

        @dataclass
        class MockEmbeddingResult:
            relationship_id: str
            subset_path: str
            glyph_count: int
            bytes_written: int
            packaging_metadata: dict

        mock_result = MockEmbeddingResult(
            relationship_id="rId123",
            subset_path="/tmp/subset.ttf",
            glyph_count=5,
            bytes_written=12345,
            packaging_metadata={"font_data": b"subset font bytes"},
        )

        embedding_engine = Mock()
        embedding_engine.subset_font = Mock(return_value=mock_result)

        generator = DrawingMLTextGenerator(embedding_engine=embedding_engine)

        match = MockFontMatch(
            family="Arial",
            path="/fonts/arial.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )
        node = MockTextNode(text_content="Test")

        result = generator.embed_font(node, match)
        assert result is mock_result
        assert result.glyph_count == 5
        assert result.bytes_written == 12345
