"""Simplified SVG parser derived from svg2pptx core logic."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.core.conversion_context import (
    ConversionContextBundle,
)
from svg2ooxml.performance.metrics import record_metric
from svg2ooxml.services import ConversionServices

from .content_cleaner import prepare_svg_content
from .css_font_parser import CSSFontFaceParser
from .dom_loader import XMLParser
from .normalization import SafeSVGNormalizer
from .preprocess.services import ParserServices
from .reference_collector import collect_references
from .references import collect_namespaces, has_external_references
from .result import ParseResult
from .statistics import compute_statistics
from .svg_font_parser import SVGFontParser
from .svg_parser_config import ParserConfig
from .svg_parser_context import SVGParserContextMixin
from .svg_parser_geometry import SVGParserGeometryMixin
from .svg_parser_telemetry import SVGParserTelemetryMixin
from .validators import has_basic_dimensions


class SVGParser(
    SVGParserContextMixin,
    SVGParserGeometryMixin,
    SVGParserTelemetryMixin,
):
    """Parse SVG strings into lxml element trees with light normalization."""

    def __init__(
        self,
        config: ParserConfig | None = None,
        services: ConversionServices | ParserServices | ConversionContextBundle | None = None,
    ) -> None:
        self._config = config or ParserConfig()
        self._logger = logging.getLogger(__name__)
        self._xml_parser = XMLParser(self._config.to_parser_options())
        self._normalizer = SafeSVGNormalizer()
        self._font_parser = CSSFontFaceParser()
        self._svg_font_parser = SVGFontParser()

        context = self._coerce_context(services)
        self._context_template = context
        self._policy_engine = context.policy_engine
        self._unit_converter = context.unit_converter
        self._style_resolver = context.style_resolver

    def parse(
        self,
        svg_content: str,
        *,
        tracer: ConversionTracer | None = None,
        source_path: str | None = None,
    ) -> ParseResult:
        """Parse the provided SVG content into an XML tree."""
        start_time = time.perf_counter()

        prep_report: dict[str, object] = {}

        if not svg_content.strip():
            preparse_error = {"error": "empty_input"}
            failure = ParseResult.failure(
                "SVG content is empty.",
                processing_time_ms=0.0,
            )
            failure.metadata["preparse"] = preparse_error
            self._trace(tracer, "error", metadata=preparse_error, subject="empty_input")
            self._emit_metrics(
                success=False,
                elapsed_ms=0.0,
                preparse=preparse_error,
                normalization=None,
                stats=None,
                error="SVG content is empty.",
            )
            return failure

        stats: dict[str, int] | None = None

        try:
            cleaned = prepare_svg_content(svg_content, report=prep_report)
        except ValueError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            failure = ParseResult.failure(str(exc), processing_time_ms=elapsed_ms)
            if prep_report:
                failure.metadata["preparse"] = prep_report
            self._trace(
                tracer,
                "error",
                metadata={"message": str(exc), "preparse": prep_report},
                subject="preprocess",
            )
            self._emit_metrics(
                success=False,
                elapsed_ms=elapsed_ms,
                preparse=prep_report,
                normalization=None,
                stats=None,
                error=str(exc),
            )
            return failure

        try:
            root = self._xml_parser.parse(cleaned)
        except etree.XMLSyntaxError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            failure = ParseResult.failure(
                f"XML parse error: {exc}",
                processing_time_ms=elapsed_ms,
            )
            failure.metadata["preparse"] = prep_report
            self._trace(
                tracer,
                "error",
                metadata={"message": f"XML parse error: {exc}", "preparse": prep_report},
                subject="xml_syntax",
            )
            self._emit_metrics(
                success=False,
                elapsed_ms=elapsed_ms,
                preparse=prep_report,
                normalization=None,
                stats=None,
                error=f"XML parse error: {exc}",
            )
            return failure

        try:
            self._xml_parser.validate_root(root)
        except ValueError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            failure = ParseResult.failure(str(exc), processing_time_ms=elapsed_ms)
            failure.metadata["preparse"] = prep_report
            self._trace(
                tracer,
                "error",
                metadata={"message": str(exc), "preparse": prep_report},
                subject="validator",
            )
            self._emit_metrics(
                success=False,
                elapsed_ms=elapsed_ms,
                preparse=prep_report,
                normalization=None,
                stats=None,
                error=str(exc),
            )
            return failure

        if self._config.apply_normalization:
            root, normalization_changes = self._normalizer.normalize(root)
        else:
            normalization_changes = {}
            normalization_changes.setdefault("log", [])
        normalization_changes.setdefault("encoding_fixes", [])
        normalization_changes.setdefault("structure_fixes", [])
        normalization_changes.setdefault("attributes_added", [])
        normalization_changes.setdefault("namespaces_fixed", False)
        normalization_changes.setdefault("whitespace_normalized", False)
        normalization_changes.setdefault("comments_filtered", False)
        normalization_changes.setdefault("preparse", prep_report)
        self._trace(tracer, "normalization", metadata=normalization_changes)

        # Parse web fonts from @font-face rules
        web_fonts = self._font_parser.parse_stylesheets(root)
        svg_font_result = self._svg_font_parser.parse(root)
        if svg_font_result.font_faces:
            web_fonts = list(web_fonts) + list(svg_font_result.font_faces)

        context = self._context_template.clone()
        services = context.services

        self._register_source_path_resolver(services, source_path)

        policy_context = context.policy_context
        policy_engine = context.policy_engine

        stats = compute_statistics(root)
        namespaces = collect_namespaces(root)
        external_refs = has_external_references(root)
        references = collect_references(root)
        self._trace(
            tracer,
            "references",
            metadata={
                "masks": len(references.masks),
                "filters": len(references.filters),
                "symbols": len(references.symbols),
                "markers": len(references.markers),
            },
        )
        services.register("masks", references.masks)
        services.register("filters", references.filters)
        services.register("symbols", references.symbols)
        services.register("markers", references.markers)
        width_px, height_px = self._extract_dimensions(root)
        style_context = self._build_style_context(width_px, height_px)
        self._style_resolver.collect_css(
            root,
            viewport_width=width_px,
            viewport_height=height_px,
        )
        if style_context is not None:
            services.register("style_context", style_context)
        root_style = self._style_resolver.compute_text_style(
            root, context=style_context
        )
        masks = references.masks
        symbols = references.symbols
        filters = references.filters
        markers = references.markers
        viewbox_scale = self._extract_viewbox_scale(root, width_px, height_px)
        root_color = self._extract_root_color(root)

        if self._config.strip_whitespace:
            self._strip_whitespace(root)

        # Parse SMIL animations
        from svg2ooxml.core.animation.parser import SMILParser
        animations = SMILParser().parse_svg_animations(root)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._trace(
            tracer,
            "statistics",
            metadata={
                "element_count": stats["element_count"],
                "namespace_count": stats["namespace_count"],
                "processing_time_ms": elapsed_ms,
                "external_references": external_refs,
            },
        )

        if not has_basic_dimensions(root):
            result = ParseResult(
                success=True,
                svg_root=root,
                element_count=stats["element_count"],
                namespace_count=stats["namespace_count"],
                namespaces=namespaces,
                has_external_references=external_refs,
                masks=masks,
                symbols=symbols,
                filters=filters,
                markers=markers,
                root_style=root_style,
                width_px=width_px,
                height_px=height_px,
                animations=animations,
                viewbox_scale=viewbox_scale,
                root_color=root_color,
                normalization_changes=normalization_changes,
                normalization_applied=self._config.apply_normalization,
                processing_time_ms=elapsed_ms,
                services=services,
                policy_engine=policy_engine,
                policy_context=policy_context,
                style_context=style_context,
                web_fonts=web_fonts if web_fonts else None,
                svg_fonts=svg_font_result.inline_fonts if svg_font_result.inline_fonts else None,
                error="SVG element missing width/height or viewBox.",
            )
            self._trace(tracer, "warning", metadata={"reason": "missing_dimensions"})
        else:
            result = ParseResult.success_with(
                root,
                stats["element_count"],
                namespace_count=stats["namespace_count"],
                namespaces=namespaces,
                has_external_references=external_refs,
                masks=masks,
                symbols=symbols,
                filters=filters,
                markers=markers,
                root_style=root_style,
                width_px=width_px,
                height_px=height_px,
                animations=animations,
                viewbox_scale=viewbox_scale,
                root_color=root_color,
                normalization_changes=normalization_changes,
                normalization_applied=self._config.apply_normalization,
                processing_time_ms=elapsed_ms,
                services=services,
                policy_engine=policy_engine,
                policy_context=policy_context,
                style_context=style_context,
                web_fonts=web_fonts if web_fonts else None,
                svg_fonts=svg_font_result.inline_fonts if svg_font_result.inline_fonts else None,
            )

            if source_path:
                result.metadata["source_path"] = source_path

            if self._config.eager_ir:
                try:
                    from svg2ooxml.ir import convert_parser_output

                    ir_scene = convert_parser_output(
                        result,
                        services=services,
                        policy_engine=policy_engine,
                        policy_context=policy_context,
                        logger=self._logger,
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.error("IR conversion failed: %s", exc)
                else:
                    result.metadata["ir_scene"] = ir_scene

        result.metadata["style_context"] = style_context
        result.metadata["policy_context"] = policy_context
        result.metadata["policy_engine"] = policy_engine
        result.metadata["preparse"] = prep_report
        if source_path:
            result.metadata["source_path"] = source_path
        if prep_report:
            self._trace(tracer, "preprocess", metadata=prep_report)
        self._emit_metrics(
            success=True,
            elapsed_ms=elapsed_ms,
            preparse=prep_report,
            normalization=normalization_changes,
            stats=stats,
            error=None,
        )
        self._logger.debug(
            "Parsed SVG in %.2fms (elements=%d, namespaces=%d, normalization=%s)",
            elapsed_ms,
            stats["element_count"],
            stats["namespace_count"],
            "enabled" if self._config.apply_normalization else "disabled",
        )
        return result

    def _emit_metrics(
        self,
        *,
        success: bool,
        elapsed_ms: float,
        preparse: dict[str, object] | None,
        normalization: dict[str, object] | None,
        stats: dict[str, int] | None,
        error: str | None,
    ) -> None:
        payload: dict[str, object] = {
            "success": success,
            "elapsed_ms": round(elapsed_ms, 3),
        }

        if stats:
            payload["element_count"] = stats.get("element_count")
            payload["namespace_count"] = stats.get("namespace_count")

        normalization_summary = self._summarize_normalization(normalization)
        if normalization_summary:
            payload["normalization"] = normalization_summary

        preparse_summary = self._summarize_preparse(preparse)
        if preparse_summary:
            payload["preparse"] = preparse_summary

        if error is not None:
            payload["error"] = error

        try:
            record_metric("parser.run", payload, tags={"component": "svg_parser"})
        except Exception:  # pragma: no cover - metrics should not break parsing
            self._logger.debug("Metric recording failed", exc_info=True)

def parse_svg(
    svg_content: str,
    *,
    config: ParserConfig | None = None,
    services: ConversionServices | ParserServices | ConversionContextBundle | None = None,
    tracer: ConversionTracer | None = None,
    source_path: str | None = None,
) -> ParseResult:
    """Convenience helper that parses ``svg_content`` into a :class:`ParseResult`."""

    parser = SVGParser(config=config, services=services)
    return parser.parse(svg_content, tracer=tracer, source_path=source_path)

__all__ = ["SVGParser", "ParserConfig", "parse_svg"]
if TYPE_CHECKING:  # pragma: no cover - type hints only
    from svg2ooxml.core.tracing import ConversionTracer
