"""Helpers for building PPTX packages from SVG fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder
from svg2ooxml.map import convert_parser_output
from svg2ooxml.parser.svg_parser import ParserConfig, SVGParser


class VisualBuildError(RuntimeError):
    """Raised when a visual test cannot build the PPTX fixture."""


@dataclass
class PptxBuildResult:
    pptx_path: Path
    slide_count: int


class PptxBuilder:
    """Build PPTX packages from SVG snippets using the svg2ooxml pipeline."""

    def __init__(self) -> None:
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder()

    def build_from_svg(self, svg_text: str, output_path: Path) -> PptxBuildResult:
        """Parse *svg_text*, convert to IR, and materialise a PPTX file."""

        parse_result = self._parser.parse(svg_text)
        if not parse_result.success or parse_result.svg_root is None:
            raise VisualBuildError(f"SVG parsing failed: {parse_result.error_message}")

        scene = convert_parser_output(parse_result)
        render_result = self._writer.render_scene_from_ir(scene)

        pptx_path = self._builder.build_from_results([render_result], output_path)
        return PptxBuildResult(pptx_path=pptx_path, slide_count=1)


__all__ = ["PptxBuilder", "PptxBuildResult", "VisualBuildError"]
