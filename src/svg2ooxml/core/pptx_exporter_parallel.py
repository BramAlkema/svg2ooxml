"""Parallel page rendering support for the PPTX exporter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from svg2ooxml.core.metadata import read_page_render_metadata
from svg2ooxml.core.pptx_exporter_types import (
    SvgConversionError,
    SvgPageResult,
    SvgPageSource,
    SvgToPptxMultiResult,
)
from svg2ooxml.policy.fidelity import PolicyOverrides

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.converter import IRScene
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.drawingml.result import DrawingMLRenderResult


class SvgToPptxParallelMixin:
    """Parallel rendering implementation mixed into the main exporter facade."""

    def _convert_pages_parallel(
        self,
        pages: Sequence[SvgPageSource],
        output_path: Path,
        packaging_tracer: ConversionTracer,
        *,
        max_workers: int | None = None,
        embed_trace_docprops: bool | None = None,
    ) -> SvgToPptxMultiResult:
        """Render pages in parallel, then package sequentially."""
        import os
        from concurrent.futures import ThreadPoolExecutor

        unsupported = getattr(self, "_parallel_unsupported_components", ())
        if unsupported:
            joined = ", ".join(unsupported)
            raise SvgConversionError(
                "parallel page conversion does not support custom render "
                f"components: {joined}"
            )

        workers = max_workers or min(len(pages), os.cpu_count() or 1)

        futures: list[tuple[SvgPageSource, Any]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for page in pages:
                page_metadata = read_page_render_metadata(
                    page.metadata,
                    default_variant_type="base",
                )
                fut = pool.submit(
                    self._render_page_isolated,
                    page.svg_text,
                    filter_strategy=self._filter_strategy,
                    geometry_mode=self._geometry_mode,
                    policy_overrides=page_metadata.policy_overrides,
                    source_path=page_metadata.source_path,
                )
                futures.append((page, fut))

        page_results: list[SvgPageResult] = []
        slide_count = 0

        from svg2ooxml.core.pptx_exporter_pages import build_page_result

        with self._builder.begin_streaming(tracer=packaging_tracer) as stream:
            for index, (page, fut) in enumerate(futures, start=1):
                render_result, scene, report_dict = fut.result()
                page_result = build_page_result(
                    page,
                    scene,
                    report_dict,
                    fallback_title=f"Slide {index}",
                    variant_type="base",
                    include_page_metadata=True,
                )

                stream.add_slide(render_result)
                slide_count += 1
                del render_result
                page_results.append(page_result)

            pptx_path = stream.finalize(output_path)

        packaging_report = packaging_tracer.report().to_dict()
        from svg2ooxml.core.export.variant_expansion import _merge_trace_reports

        aggregate_trace = _merge_trace_reports(
            [result.trace_report for result in page_results] + [packaging_report]
        )
        self._embed_trace_docprops_if_requested(
            pptx_path,
            aggregate_trace,
            embed_trace_docprops,
        )

        return SvgToPptxMultiResult(
            pptx_path=pptx_path,
            slide_count=slide_count,
            page_results=page_results,
            packaging_report=packaging_report,
            aggregated_trace_report=aggregate_trace,
        )

    @staticmethod
    def _render_page_isolated(
        svg_text: str,
        *,
        filter_strategy: str | None,
        geometry_mode: str,
        policy_overrides: PolicyOverrides | None = None,
        source_path: str | None = None,
    ) -> tuple[DrawingMLRenderResult, IRScene, dict[str, Any]]:
        """Thread-safe single-page render with fresh pipeline instances."""
        from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

        exporter = SvgToPptxExporter(
            filter_strategy=filter_strategy,
            geometry_mode=geometry_mode,
        )
        from svg2ooxml.core.tracing import ConversionTracer

        tracer = ConversionTracer()
        render_result, scene = exporter._render_svg(
            svg_text,
            tracer,
            policy_overrides,
            source_path=source_path,
        )
        return render_result, scene, tracer.report().to_dict()


__all__ = ["SvgToPptxParallelMixin"]
