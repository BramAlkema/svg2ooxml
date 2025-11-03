"""Helpers for building PPTX packages from SVG fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.services import configure_services


class VisualBuildError(RuntimeError):
    """Raised when a visual test cannot build the PPTX fixture."""


@dataclass
class PptxBuildResult:
    pptx_path: Path
    slide_count: int


class PptxBuilder:
    """Build PPTX packages from SVG snippets using the svg2ooxml pipeline."""

    def __init__(self, *, filter_strategy: str | None = "resvg") -> None:
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder()
        self._filter_strategy = filter_strategy

    def build_from_svg(self, svg_text: str, output_path: Path) -> PptxBuildResult:
        """Parse *svg_text*, convert to IR, and materialise a PPTX file."""

        parse_result = self._parser.parse(svg_text)
        if not parse_result.success or parse_result.svg_root is None:
            raise VisualBuildError(f"SVG parsing failed: {parse_result.error_message}")

        # Use the parser's services which includes the StyleResolver with loaded CSS rules
        services = parse_result.services
        if services is None:
            services = configure_services(filter_strategy=self._filter_strategy)
        elif self._filter_strategy and services.filter_service is not None:
            services.filter_service.set_strategy(self._filter_strategy)

        if parse_result.width_px is not None:
            setattr(services, "viewport_width", parse_result.width_px)
        if parse_result.height_px is not None:
            setattr(services, "viewport_height", parse_result.height_px)

        scene = convert_parser_output(parse_result, services=services)
        render_result = self._writer.render_scene_from_ir(scene)

        pptx_path = self._builder.build_from_results([render_result], output_path)
        return PptxBuildResult(pptx_path=pptx_path, slide_count=1)


__all__ = ["PptxBuilder", "PptxBuildResult", "VisualBuildError"]
