"""Curated public API surface for svg2ooxml."""

from __future__ import annotations

from svg2ooxml.core.parser.result import ParseResult
from svg2ooxml.core.parser.svg_parser import ParserConfig, SVGParser
from svg2ooxml.core.pptx_exporter import (
    SvgConversionError,
    SvgPageResult,
    SvgPageSource,
    SvgToPptxExporter,
    SvgToPptxMultiResult,
    SvgToPptxResult,
)
from svg2ooxml.core.tracing.conversion import ConversionTracer
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder, write_pptx
from svg2ooxml.ir.entrypoints import IRScene, convert_parser_output

__all__ = [
    "ConversionTracer",
    "IRScene",
    "PPTXPackageBuilder",
    "ParseResult",
    "ParserConfig",
    "SVGParser",
    "SvgConversionError",
    "SvgPageResult",
    "SvgPageSource",
    "SvgToPptxExporter",
    "SvgToPptxMultiResult",
    "SvgToPptxResult",
    "convert_parser_output",
    "write_pptx",
]
