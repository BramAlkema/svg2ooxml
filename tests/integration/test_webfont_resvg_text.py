"""Integration tests for web font support with resvg text rendering.

These tests verify that the resvg text pipeline correctly integrates with
the FontService and FontEmbeddingEngine for web font resolution and embedding.
"""

import pytest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import Mock, MagicMock


# Mock structures for integration testing
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
    transform: Optional[object] = None
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


@dataclass
class MockFontMatch:
    """Mock FontMatch for testing."""
    family: str
    path: str
    weight: int
    style: str
    found_via: str
    metadata: dict


@dataclass
class MockEmbeddingResult:
    """Mock FontEmbeddingResult for testing."""
    relationship_id: str
    subset_path: Optional[str]
    glyph_count: int
    bytes_written: int
    permission: str = "installable"
    optimisation: str = "balanced"
    packaging_metadata: dict = None

    def __post_init__(self):
        if self.packaging_metadata is None:
            self.packaging_metadata = {}


class TestWebFontResvgIntegration:
    """Integration tests for web font + resvg text pipeline."""

    def test_text_coordinator_with_font_services(self):
        """Test that TextRenderCoordinator accepts font services."""
        from svg2ooxml.core.resvg.text.text_coordinator import TextRenderCoordinator

        font_service = Mock()
        embedding_engine = Mock()

        coordinator = TextRenderCoordinator(
            font_service=font_service,
            embedding_engine=embedding_engine,
        )

        # Verify services were passed to generator
        assert coordinator._generator._font_service is font_service
        assert coordinator._generator._embedding_engine is embedding_engine

    def test_end_to_end_system_font_resolution(self):
        """Test end-to-end flow with system font resolution."""
        from svg2ooxml.core.resvg.text.text_coordinator import TextRenderCoordinator

        # Create mock font service that returns a system font
        font_service = Mock()
        font_service.find_font = Mock(return_value=MockFontMatch(
            family="Arial",
            path="/System/Library/Fonts/Helvetica.ttc",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        ))

        # Create coordinator with font service
        coordinator = TextRenderCoordinator(font_service=font_service)

        # Create simple text node
        node = MockTextNode(
            text_content="Hello World",
            text_style=MockTextStyle(
                font_families=("Arial",),
                font_size=12.0,
                font_style="normal",
                font_weight="400",
            ),
        )

        # Render (should use native DrawingML)
        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None
        assert "<p:txBody>" in result.content
        assert "Hello World" in result.content

        # Verify font service was available for use (though not called in this test)
        assert coordinator._generator._font_service is not None

    def test_end_to_end_web_font_resolution(self):
        """Test end-to-end flow with web font resolution and embedding."""
        from svg2ooxml.core.resvg.text.text_coordinator import TextRenderCoordinator

        # Create mock font service that returns a web font with loaded data
        font_data = b"fake web font bytes"
        font_service = Mock()
        font_service.find_font = Mock(return_value=MockFontMatch(
            family="CustomWebFont",
            path="https://example.com/fonts/custom.woff2",
            weight=400,
            style="normal",
            found_via="webfont",
            metadata={"font_data": font_data, "loaded": True},
        ))

        # Create mock embedding engine
        embedding_engine = Mock()
        embedding_engine.subset_font = Mock(return_value=MockEmbeddingResult(
            relationship_id="rId123",
            subset_path=None,  # Web fonts use in-memory data
            glyph_count=11,  # "Hello World" has 11 unique chars
            bytes_written=5000,
            packaging_metadata={"font_data": b"subset font bytes"},
        ))

        # Create coordinator with both services
        coordinator = TextRenderCoordinator(
            font_service=font_service,
            embedding_engine=embedding_engine,
        )

        # Create simple text node with custom font
        node = MockTextNode(
            text_content="Hello World",
            text_style=MockTextStyle(
                font_families=("CustomWebFont",),
                font_size=14.0,
                font_style="normal",
                font_weight="400",
            ),
        )

        # Render (should use native DrawingML)
        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None
        assert "<p:txBody>" in result.content
        assert "Hello World" in result.content

        # Now test font resolution and embedding
        generator = coordinator._generator

        # Resolve font
        match = generator.resolve_font(node, fallback_chain=("Arial",))
        assert match is not None
        assert match.family == "CustomWebFont"
        assert match.found_via == "webfont"
        assert "font_data" in match.metadata
        assert match.metadata["font_data"] == font_data

        # Embed font
        embed_result = generator.embed_font(node, match)
        assert embed_result is not None
        assert embed_result.glyph_count == 11
        assert embed_result.bytes_written == 5000
        assert "font_data" in embed_result.packaging_metadata

        # Verify font service was called with correct query
        font_service.find_font.assert_called_once()
        query = font_service.find_font.call_args[0][0]
        assert query.family == "CustomWebFont"
        assert query.weight == 400
        assert query.style == "normal"
        assert query.fallback_chain == ("Arial",)

        # Verify embedding engine was called with font_data
        embedding_engine.subset_font.assert_called_once()
        request = embedding_engine.subset_font.call_args[0][0]
        assert "font_data" in request.metadata
        assert request.metadata["font_data"] == font_data

    def test_font_resolution_with_fallback_chain(self):
        """Test that font resolution uses fallback chain."""
        from svg2ooxml.core.resvg.text.drawingml_generator import DrawingMLTextGenerator

        # Create mock font service
        font_service = Mock()
        font_service.find_font = MagicMock(return_value=MockFontMatch(
            family="Helvetica",  # Fallback was used
            path="/fonts/helvetica.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        ))

        generator = DrawingMLTextGenerator(font_service=font_service)

        node = MockTextNode(
            text_content="Test",
            text_style=MockTextStyle(
                font_families=("NonExistentFont", "Helvetica", "Arial"),
                font_size=12.0,
                font_style="normal",
                font_weight="400",
            ),
        )

        # Resolve with explicit fallback chain
        match = generator.resolve_font(node, fallback_chain=("sans-serif",))

        # Verify font service was called
        font_service.find_font.assert_called_once()
        query = font_service.find_font.call_args[0][0]
        assert query.family == "NonExistentFont"  # First font from families
        assert query.fallback_chain == ("sans-serif",)

    def test_font_embedding_collects_all_characters(self):
        """Test that font embedding collects all unique characters."""
        from svg2ooxml.core.resvg.text.drawingml_generator import DrawingMLTextGenerator

        embedding_engine = Mock()
        embedding_engine.subset_font = MagicMock(return_value=None)

        generator = DrawingMLTextGenerator(embedding_engine=embedding_engine)

        match = MockFontMatch(
            family="TestFont",
            path="/fonts/test.ttf",
            weight=400,
            style="normal",
            found_via="system",
            metadata={},
        )

        # Text with repeated characters
        node = MockTextNode(text_content="aabbcc")

        generator.embed_font(node, match)

        # Verify embedding request contains unique characters
        embedding_engine.subset_font.assert_called_once()
        request = embedding_engine.subset_font.call_args[0][0]
        assert set(request.characters) == {"a", "b", "c"}

    def test_backward_compatibility_without_font_services(self):
        """Test that text rendering works without font services (backward compatibility)."""
        from svg2ooxml.core.resvg.text.text_coordinator import TextRenderCoordinator

        # Create coordinator without font services (like before)
        coordinator = TextRenderCoordinator()

        node = MockTextNode(
            text_content="Simple text",
            text_style=MockTextStyle(
                font_families=("Arial",),
                font_size=12.0,
                font_style="normal",
                font_weight="400",
            ),
        )

        # Should still work, just without font resolution/embedding
        result = coordinator.render(node)

        assert result.strategy == "native"
        assert result.content is not None
        assert "<p:txBody>" in result.content
        assert "Simple text" in result.content


__all__ = ["TestWebFontResvgIntegration"]
