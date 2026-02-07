"""Simplified SVG parser derived from svg2pptx core logic."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.core.conversion_context import (
    ConversionContextBundle,
    build_conversion_context,
    clone_policy_context,
)
from svg2ooxml.performance.metrics import record_metric
from svg2ooxml.services import ConversionServices

from .colors.parsing import parse_color
from .content_cleaner import prepare_svg_content
from .css_font_parser import CSSFontFaceParser
from .dom_loader import ParserOptions, XMLParser
from .normalization import SafeSVGNormalizer
from .preprocess.services import ParserServices
from .reference_collector import collect_references
from .references import collect_namespaces, has_external_references
from .result import ParseResult
from .statistics import compute_statistics
from .style_context import StyleContext as ParserStyleContext
from .style_context import resolve_viewport
from .svg_font_parser import SVGFontParser
from .units import viewbox_to_px
from .validators import has_basic_dimensions


@dataclass(slots=True)
class ParserConfig:
    """Basic parsing configuration flags."""

    remove_comments: bool = False
    strip_whitespace: bool = False
    recover: bool = True
    remove_blank_text: bool = False
    strip_cdata: bool = False
    resolve_entities: bool = True
    apply_normalization: bool = True

    def to_parser_options(self) -> ParserOptions:
        return ParserOptions(
            remove_comments=self.remove_comments,
            remove_blank_text=self.remove_blank_text,
            strip_cdata=self.strip_cdata,
            recover=self.recover,
            resolve_entities=self.resolve_entities,
        )


class SVGParser:
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

        self._style_resolver.collect_css(root)

        # Parse web fonts from @font-face rules
        web_fonts = self._font_parser.parse_stylesheets(root)
        svg_font_result = self._svg_font_parser.parse(root)
        if svg_font_result.font_faces:
            web_fonts = list(web_fonts) + list(svg_font_result.font_faces)

        context = self._context_template.clone()
        services = context.services

        if source_path:
            image_service = getattr(services, "image_service", None)
            if image_service:
                try:
                    from svg2ooxml.services.image_service import FileResolver
                    base_dir = os.path.dirname(source_path)
                    image_service.register_resolver(FileResolver(base_dir), prepend=True)
                except ImportError:
                    self._logger.warning("Could not import FileResolver to handle source_path images.")

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

    def _coerce_context(
        self,
        services: ConversionServices | ParserServices | ConversionContextBundle | None,
    ) -> ConversionContextBundle:
        if services is None:
            return build_conversion_context()
        if isinstance(services, ConversionContextBundle):
            return services.clone()
        if isinstance(services, ParserServices):
            cloned_context = clone_policy_context(services.policy_context)
            if cloned_context is None:
                cloned_context = services.policy_engine.evaluate()
            return build_conversion_context(
                services=services.services,
                policy_engine=services.policy_engine,
                policy_context=cloned_context,
                unit_converter=services.unit_converter,
                style_resolver=services.style_resolver,
            )

        return build_conversion_context(services=services)

    def _strip_whitespace(self, element: etree._Element) -> None:
        """Remove leading/trailing whitespace from text nodes."""
        if element.text:
            element.text = element.text.strip()
        if element.tail:
            element.tail = element.tail.strip()
        for child in element:
            self._strip_whitespace(child)

    @staticmethod
    def _trace(
        tracer: ConversionTracer | None,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
    ) -> None:
        if tracer is None:
            return
        tracer.record_stage_event(stage="parser", action=action, metadata=metadata, subject=subject)

    def _extract_dimensions(
        self, root: etree._Element
    ) -> tuple[float | None, float | None]:
        width_px, height_px = resolve_viewport(
            root,
            self._unit_converter,
            default_width=800.0,
            default_height=600.0,
        )
        viewbox = root.get("viewBox")
        if viewbox is None and root.get("width") is None:
            width_px = None
        if viewbox is None and root.get("height") is None:
            height_px = None
        return width_px, height_px

    def _extract_viewbox_scale(
        self,
        root: etree._Element,
        width_px: float | None,
        height_px: float | None,
    ) -> tuple[float, float] | None:
        viewbox_attr = root.get("viewBox")
        if not viewbox_attr or width_px is None or height_px is None:
            return None
        viewbox = self._parse_viewbox(viewbox_attr)
        if viewbox is None:
            return None
        return viewbox_to_px(viewbox, width_px, height_px)

    def _extract_root_color(
        self, root: etree._Element
    ) -> tuple[float, float, float, float] | None:
        color_attr = root.get("color")
        if not color_attr:
            return None
        return parse_color(color_attr)

    def _parse_viewbox(self, value: str) -> tuple[float, float, float, float] | None:
        parts = value.replace(",", " ").split()
        if len(parts) != 4:
            return None
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return None
        return (numbers[0], numbers[1], numbers[2], numbers[3])

    def _build_style_context(
        self,
        width_px: float | None,
        height_px: float | None,
    ) -> ParserStyleContext | None:
        if width_px is None or height_px is None:
            return None
        conversion = self._unit_converter.create_context(
            width=width_px,
            height=height_px,
            font_size=12.0,
            parent_width=width_px,
            parent_height=height_px,
        )
        return ParserStyleContext(
            conversion=conversion,
            viewport_width=width_px,
            viewport_height=height_px,
        )

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

    @staticmethod
    def _summarize_preparse(report: dict[str, object] | None) -> dict[str, object] | None:
        if not report:
            return None
        summary: dict[str, object] = {}
        for key in (
            "removed_bom",
            "encoding_replacements",
            "added_xml_declaration",
            "error",
        ):
            if key in report:
                summary[key] = report[key]

        by_char = report.get("encoding_replacements_by_char")
        if isinstance(by_char, dict) and by_char:
            summary["encoding_replacements_by_char"] = by_char

        return summary or None

    @staticmethod
    def _summarize_normalization(
        changes: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not changes:
            return None

        summary: dict[str, object] = {}
        if "namespaces_fixed" in changes:
            summary["namespaces_fixed"] = bool(changes["namespaces_fixed"])

        attributes_added = changes.get("attributes_added")
        if isinstance(attributes_added, list) and attributes_added:
            summary["attributes_added"] = len(attributes_added)

        structure_fixes = changes.get("structure_fixes")
        if isinstance(structure_fixes, list) and structure_fixes:
            summary["structure_fixes"] = len(structure_fixes)

        summary["whitespace_normalized"] = bool(
            changes.get("whitespace_normalized")
        )
        summary["comments_filtered"] = bool(changes.get("comments_filtered"))

        encoding_fixes = changes.get("encoding_fixes")
        if isinstance(encoding_fixes, list) and encoding_fixes:
            total_encoding_fix = 0
            for entry in encoding_fixes:
                if isinstance(entry, dict):
                    total_encoding_fix += int(entry.get("text_nodes", 0))
                    total_encoding_fix += int(entry.get("tail_nodes", 0))
                    total_encoding_fix += int(entry.get("attributes", 0))
            if total_encoding_fix:
                summary["encoding_fix_nodes"] = total_encoding_fix

        log_entries = changes.get("log")
        if isinstance(log_entries, list) and log_entries:
            action_counts: dict[str, int] = {}
            for entry in log_entries:
                if isinstance(entry, dict):
                    action = entry.get("action")
                    if isinstance(action, str) and action:
                        action_counts[action] = action_counts.get(action, 0) + 1
            if action_counts:
                summary["actions"] = action_counts

        return summary or None


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