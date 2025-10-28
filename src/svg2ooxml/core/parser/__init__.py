"""Parser utilities for svg2ooxml."""

from .dom_loader import ParserOptions, XMLParser, load_dom
from .content_cleaner import XML_DECLARATION, fix_encoding_issues, prepare_svg_content
from .colors.parsing import parse_color, register_palette
from .normalization import NormalizationSettings, SafeSVGNormalizer
from .statistics import compute_statistics
from .switch_evaluator import SwitchEvaluator
from .style_context import StyleContext, build_style_context, resolve_viewport
from .references import collect_namespaces, has_external_references
from .reference_collector import ParserReferences, collect_references
from .preprocess.services import ParserServices, build_parser_services
from .units import viewbox_to_px, ConversionContext, UnitConverter
from .result import ParseResult
from .svg_parser import ParserConfig, SVGParser

__all__ = [
    "ParserOptions",
    "XMLParser",
    "load_dom",
    "NormalizationSettings",
    "SafeSVGNormalizer",
    "compute_statistics",
    "SwitchEvaluator",
    "StyleContext",
    "build_style_context",
    "resolve_viewport",
    "collect_namespaces",
    "has_external_references",
    "ParserReferences",
    "collect_references",
    "ParserServices",
    "build_parser_services",
    "ConversionContext",
    "UnitConverter",
    "viewbox_to_px",
    "ParseResult",
    "parse_color",
    "register_palette",
    "XML_DECLARATION",
    "prepare_svg_content",
    "fix_encoding_issues",
    "ParserConfig",
    "SVGParser",
]
