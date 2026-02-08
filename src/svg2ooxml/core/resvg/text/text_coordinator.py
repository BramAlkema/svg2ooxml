"""Coordinates text rendering with DrawingML or EMF fallback.

This module determines the rendering strategy for SVG text elements:
- Simple layouts: Native DrawingML via DrawingMLTextGenerator
- Complex layouts: EMF/raster fallback

Uses TextLayoutAnalyzer to detect complexity and RenderTracer for telemetry.
Optionally integrates with FontService for font resolution and embedding.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import TextNode
    from svg2ooxml.ir.text_path import PathPoint
    from svg2ooxml.services.fonts.embedding import FontEmbeddingEngine
    from svg2ooxml.services.fonts.service import FontService
    from svg2ooxml.telemetry.render_decisions import RenderTracer

from .drawingml_generator import DrawingMLTextGenerator
from .layout_analyzer import TextLayoutAnalyzer, TextLayoutComplexity


@dataclass
class TextRenderResult:
    """Result of text rendering decision.

    Attributes:
        strategy: Rendering strategy chosen ("native" or "emf")
        content: DrawingML XML if native, None if EMF (caller handles EMF generation)
        complexity: Complexity reason from TextLayoutAnalyzer
        details: Human-readable explanation
    """

    strategy: Literal["native", "emf", "wordart"]
    content: str | None
    complexity: str
    details: str | None = None


class TextRenderCoordinator:
    """Coordinates text rendering with complexity detection and fallback.

    This class determines whether SVG text can be rendered as native DrawingML
    or requires EMF fallback based on layout complexity analysis.

    Optionally integrates with FontService for font resolution and
    FontEmbeddingEngine for font subsetting/embedding.

    Usage:
        # Basic usage
        coordinator = TextRenderCoordinator()
        result = coordinator.render(text_node, tracer=my_tracer)
        if result.strategy == "native":
            # Use result.content (DrawingML XML)
        else:
            # Generate EMF fallback

        # With font services
        coordinator = TextRenderCoordinator(
            font_service=font_service,
            embedding_engine=embedding_engine
        )
        result = coordinator.render(text_node)
    """

    def __init__(
        self,
        max_rotation_deg: float = 45.0,
        max_skew_deg: float = 5.0,
        max_scale_ratio: float = 2.0,
        font_service: FontService | None = None,
        embedding_engine: FontEmbeddingEngine | None = None,
        paint_resolver: object | None = None,
        wordart_confidence_threshold: float = 0.55,
    ) -> None:
        """Initialize text rendering coordinator.

        Args:
            max_rotation_deg: Maximum rotation for DrawingML (default: 45°)
            max_skew_deg: Maximum skew for DrawingML (default: 5°)
            max_scale_ratio: Maximum scale ratio for DrawingML (default: 2.0)
            font_service: Optional FontService for font resolution
            embedding_engine: Optional FontEmbeddingEngine for font subsetting
            paint_resolver: Optional callback to resolve PaintReference to IR Paint
            wordart_confidence_threshold: Minimum confidence for WordArt (default: 0.55)
        """
        self._analyzer = TextLayoutAnalyzer(
            max_rotation_deg=max_rotation_deg,
            max_skew_deg=max_skew_deg,
            max_scale_ratio=max_scale_ratio,
        )
        self._generator = DrawingMLTextGenerator(
            font_service=font_service,
            embedding_engine=embedding_engine,
            paint_resolver=paint_resolver,
        )
        self._wordart_threshold = wordart_confidence_threshold

    def render(
        self,
        node: TextNode,
        tracer: RenderTracer | None = None,
        *,
        path_points: Sequence[PathPoint] | None = None,
        path_data: str | None = None,
    ) -> TextRenderResult:
        """Determine rendering strategy and generate content if native.

        Args:
            node: TextNode from resvg tree
            tracer: Optional RenderTracer for telemetry
            path_points: Optional pre-sampled path points for textPath WordArt
            path_data: Optional SVG path d-attribute for textPath WordArt

        Returns:
            TextRenderResult with strategy, content, and complexity info
        """
        # Analyze text layout complexity
        analysis = self._analyzer.analyze(node)

        if analysis.is_plain:
            # Simple text: render as native DrawingML
            try:
                content = self._generator.generate_text_body(node)
                result = TextRenderResult(
                    strategy="native",
                    content=content,
                    complexity=TextLayoutComplexity.SIMPLE,
                    details="Simple text layout, using native DrawingML",
                )

                # Record telemetry: successful native rendering
                if tracer:
                    tracer.record_decision(
                        element_type="text",
                        strategy="native",
                        reason="Simple text layout (no complex transforms/positioning)",
                        metadata={
                            "complexity": TextLayoutComplexity.SIMPLE,
                            "text_preview": (node.text_content or "")[:50],
                        },
                    )

                return result

            except Exception as e:
                # DrawingML generation failed, fall back to EMF
                result = TextRenderResult(
                    strategy="emf",
                    content=None,
                    complexity="generation_error",
                    details=f"DrawingML generation failed: {str(e)}",
                )

                # Record telemetry: fallback due to generation error
                if tracer:
                    tracer.record_decision(
                        element_type="text",
                        strategy="emf",
                        reason=f"DrawingML generation error: {str(e)}",
                        metadata={
                            "complexity": "generation_error",
                            "error_type": type(e).__name__,
                        },
                    )

                return result

        # textPath detected: try WordArt classification before EMF fallback
        if analysis.complexity == TextLayoutComplexity.HAS_TEXT_PATH and path_points:
            wordart_result = self._try_wordart(node, path_points, path_data, tracer)
            if wordart_result is not None:
                return wordart_result

        # Complex text: use EMF fallback
        result = TextRenderResult(
            strategy="emf",
            content=None,
            complexity=analysis.complexity,
            details=analysis.details or f"Complex layout: {analysis.complexity}",
        )

        # Record telemetry: fallback due to complexity
        if tracer:
            tracer.record_decision(
                element_type="text",
                strategy="emf",
                reason=analysis.details or f"Complex text layout: {analysis.complexity}",
                metadata={
                    "complexity": analysis.complexity,
                    "text_preview": (node.text_content or "")[:50],
                },
            )

        return result

    def _try_wordart(
        self,
        node: TextNode,
        path_points: Sequence[PathPoint],
        path_data: str | None,
        tracer: RenderTracer | None,
    ) -> TextRenderResult | None:
        """Attempt WordArt classification and rendering for textPath text."""
        from svg2ooxml.common.geometry.algorithms import classify_text_path_warp
        from svg2ooxml.ir.text import Run
        from svg2ooxml.ir.text_path import TextPathFrame

        text_content = node.text_content or ""
        if not text_content.strip():
            return None

        try:
            runs = [Run(text=text_content, font_family="Arial", font_size_pt=12.0)]
            text_path_frame = TextPathFrame(
                runs=runs,
                path_reference="detected-path",
                path_points=list(path_points),
            )
            classification = classify_text_path_warp(
                text_path_frame,
                list(path_points),
                path_data=path_data,
            )
        except Exception:
            return None

        if classification is None or classification.confidence < self._wordart_threshold:
            return None

        try:
            content = self._generator.generate_wordart_text_body(
                node, classification.preset
            )
            result = TextRenderResult(
                strategy="wordart",
                content=content,
                complexity=TextLayoutComplexity.HAS_TEXT_PATH,
                details=f"TextPath classified as {classification.preset} "
                f"(confidence={classification.confidence:.2f})",
            )

            if tracer:
                tracer.record_decision(
                    element_type="text",
                    strategy="wordart",
                    reason=f"TextPath matched WordArt preset: {classification.preset}",
                    metadata={
                        "complexity": TextLayoutComplexity.HAS_TEXT_PATH,
                        "preset": classification.preset,
                        "confidence": classification.confidence,
                        "text_preview": text_content[:50],
                    },
                )

            return result

        except Exception:
            return None

    def is_simple_layout(self, node: TextNode) -> bool:
        """Quick check if text layout is simple (for external callers).

        Args:
            node: TextNode from resvg tree

        Returns:
            True if layout is simple enough for DrawingML
        """
        return self._analyzer.is_plain_text_layout(node)


__all__ = ["TextRenderCoordinator", "TextRenderResult"]
