"""High-level helpers that convert SVG snippets into PPTX packages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from svg2ooxml.core.pptx_exporter_multipage import SvgToPptxPagesMixin
from svg2ooxml.core.pptx_exporter_parallel import SvgToPptxParallelMixin
from svg2ooxml.core.pptx_exporter_render import SvgToPptxRenderMixin
from svg2ooxml.core.pptx_exporter_types import (
    SvgConversionError,
    SvgPageResult,
    SvgPageSource,
    SvgToPptxMultiResult,
    SvgToPptxResult,
)
from svg2ooxml.policy.fidelity import PolicyOverrides

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.animation import (
        SMILParser,
        TimelineSampler,
        TimelineSamplingConfig,
    )
    from svg2ooxml.core.parser import SVGParser
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.drawingml.writer import DrawingMLWriter
    from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder


class SvgToPptxExporter(
    SvgToPptxPagesMixin,
    SvgToPptxParallelMixin,
    SvgToPptxRenderMixin,
):
    """Facade around the parsing and packaging pipeline used by the CLI."""

    def __init__(
        self,
        parser: SVGParser | None = None,
        writer: DrawingMLWriter | None = None,
        builder: PPTXPackageBuilder | None = None,
        *,
        animation_parser_factory: type[SMILParser] | None = None,
        timeline_sampler: TimelineSampler | None = None,
        timeline_config: TimelineSamplingConfig | None = None,
        filter_strategy: str | None = None,
        geometry_mode: str | None = None,
        slide_size_mode: str | None = None,
        embed_trace_docprops: bool = False,
    ) -> None:
        """Initialize the SVG to PPTX exporter.

        Args:
            parser: Optional custom SVG parser
            writer: Optional custom DrawingML writer
            builder: Optional custom PPTX builder
            animation_parser_factory: Optional animation parser factory
            timeline_sampler: Optional timeline sampler
            timeline_config: Optional timeline config
            filter_strategy: Optional filter strategy
            geometry_mode: Geometry extraction mode: "legacy", "resvg", or "resvg-only".
                          Defaults to "resvg-only". Can also be set via
                          SVG2OOXML_GEOMETRY_MODE environment variable.
        """
        import os

        custom_parallel_components = []
        if parser is not None:
            custom_parallel_components.append("parser")
        if writer is not None:
            custom_parallel_components.append("writer")
        if animation_parser_factory is not None:
            custom_parallel_components.append("animation_parser_factory")
        if timeline_sampler is not None:
            custom_parallel_components.append("timeline_sampler")
        if timeline_config is not None:
            custom_parallel_components.append("timeline_config")
        self._parallel_unsupported_components = tuple(custom_parallel_components)

        if parser is None:
            from svg2ooxml.core.parser import ParserConfig, SVGParser

            parser = SVGParser(ParserConfig())
        if writer is None:
            from svg2ooxml.drawingml.writer import DrawingMLWriter

            writer = DrawingMLWriter()
        if animation_parser_factory is None:
            from svg2ooxml.core.animation import SMILParser

            animation_parser_factory = SMILParser

        self._parser = parser
        self._writer = writer
        self._animation_parser_factory = animation_parser_factory
        if timeline_sampler is not None:
            self._timeline_sampler = timeline_sampler
        else:
            from svg2ooxml.core.animation import TimelineSampler

            self._timeline_sampler = TimelineSampler(timeline_config)
        self._filter_strategy = filter_strategy

        # Geometry mode: check parameter, then env var, then default to "resvg-only"
        if geometry_mode is not None:
            self._geometry_mode = geometry_mode
        else:
            self._geometry_mode = os.environ.get(
                "SVG2OOXML_GEOMETRY_MODE", "resvg-only"
            )

        # Validate geometry_mode
        if self._geometry_mode not in ("legacy", "resvg", "resvg-only"):
            raise ValueError(
                f"Invalid geometry_mode: {self._geometry_mode!r}. "
                f"Must be 'legacy', 'resvg', or 'resvg-only'."
            )

        env_slide_mode = os.environ.get("SVG2OOXML_SLIDE_SIZE_MODE")
        mode = slide_size_mode or env_slide_mode or "same"
        from svg2ooxml.io.pptx_package_constants import ALLOWED_SLIDE_SIZE_MODES

        if mode not in ALLOWED_SLIDE_SIZE_MODES:
            raise ValueError(
                f"Invalid slide_size_mode: {mode!r}. "
                f"Must be one of {sorted(ALLOWED_SLIDE_SIZE_MODES)}."
            )
        self._slide_size_mode = mode

        if builder is None:
            from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder

            builder = PPTXPackageBuilder(slide_size_mode=self._slide_size_mode)
        self._builder = builder
        self._embed_trace_docprops = bool(embed_trace_docprops)

    # ------------------------------------------------------------------
    # Single document conversion
    # ------------------------------------------------------------------

    def convert_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        tracer: ConversionTracer | None = None,
        policy_overrides: PolicyOverrides | None = None,
        embed_trace_docprops: bool | None = None,
    ) -> SvgToPptxResult:
        """Convert the SVG located at *input_path* into a PPTX package."""

        if not input_path.exists():
            raise SvgConversionError(f"Input file does not exist: {input_path}")

        svg_text = input_path.read_text(encoding="utf-8")
        target_path = output_path or input_path.with_suffix(".pptx")
        return self.convert_string(
            svg_text,
            target_path,
            tracer=tracer,
            source_path=str(input_path),
            policy_overrides=policy_overrides,
            embed_trace_docprops=embed_trace_docprops,
        )

    def convert_string(
        self,
        svg_text: str,
        output_path: Path,
        *,
        tracer: ConversionTracer | None = None,
        source_path: str | None = None,
        policy_overrides: PolicyOverrides | None = None,
        embed_trace_docprops: bool | None = None,
    ) -> SvgToPptxResult:
        """Convert an SVG payload into a PPTX written to *output_path*."""

        from svg2ooxml.core.tracing import ConversionTracer

        active_tracer = tracer or ConversionTracer()
        render_result, scene = self._render_svg(
            svg_text,
            active_tracer,
            source_path=source_path,
            policy_overrides=policy_overrides,
        )
        pptx_path = self._builder.build_from_results(
            [render_result],
            output_path,
            tracer=active_tracer,
            slide_size_mode=self._slide_size_mode,
        )

        report_dict = active_tracer.report().to_dict()
        if isinstance(scene.metadata, dict):
            scene.metadata["trace_report"] = report_dict
        self._embed_trace_docprops_if_requested(
            pptx_path,
            report_dict,
            embed_trace_docprops,
        )

        return SvgToPptxResult(
            pptx_path=pptx_path, slide_count=1, trace_report=report_dict
        )

    def _should_embed_trace_docprops(self, override: bool | None) -> bool:
        return self._embed_trace_docprops if override is None else bool(override)

    def _embed_trace_docprops_if_requested(
        self,
        pptx_path: Path,
        trace_report: dict[str, Any],
        override: bool | None,
    ) -> None:
        if not self._should_embed_trace_docprops(override):
            return
        from svg2ooxml.io.pptx_docprops import embed_trace_docprops as _embed

        _embed(pptx_path, trace_report)


def _apply_immediate_motion_starts(*args: Any, **kwargs: Any):
    from svg2ooxml.core.export.motion_geometry import _apply_immediate_motion_starts

    return _apply_immediate_motion_starts(*args, **kwargs)


def _coalesce_simple_position_motions(*args: Any, **kwargs: Any):
    from svg2ooxml.core.export.variant_expansion import (
        _coalesce_simple_position_motions,
    )

    return _coalesce_simple_position_motions(*args, **kwargs)


def _compose_sampled_center_motions(*args: Any, **kwargs: Any):
    from svg2ooxml.core.export.animation_processor import (
        _compose_sampled_center_motions,
    )

    return _compose_sampled_center_motions(*args, **kwargs)


def _compose_simple_line_endpoint_animations(*args: Any, **kwargs: Any):
    from svg2ooxml.core.export.variant_expansion import (
        _compose_simple_line_endpoint_animations,
    )

    return _compose_simple_line_endpoint_animations(*args, **kwargs)


def _enrich_animations_with_element_centers(*args: Any, **kwargs: Any):
    from svg2ooxml.core.export.animation_processor import (
        _enrich_animations_with_element_centers,
    )

    return _enrich_animations_with_element_centers(*args, **kwargs)


def build_fidelity_tier_variants(*args: Any, **kwargs: Any):
    from svg2ooxml.core.slide_orchestrator import build_fidelity_tier_variants

    return build_fidelity_tier_variants(*args, **kwargs)


def derive_variants_from_trace(*args: Any, **kwargs: Any):
    from svg2ooxml.core.slide_orchestrator import derive_variants_from_trace

    return derive_variants_from_trace(*args, **kwargs)


def expand_page_with_variants(*args: Any, **kwargs: Any):
    from svg2ooxml.core.slide_orchestrator import expand_page_with_variants

    return expand_page_with_variants(*args, **kwargs)


__all__ = [
    "SvgConversionError",
    "SvgToPptxExporter",
    "SvgToPptxResult",
    "SvgToPptxMultiResult",
    "SvgPageSource",
    "SvgPageResult",
]
