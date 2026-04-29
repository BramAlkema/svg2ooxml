"""Multi-page conversion support for the PPTX exporter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.core.metadata import read_page_render_metadata
from svg2ooxml.core.pptx_exporter_types import (
    SvgConversionError,
    SvgPageResult,
    SvgPageSource,
    SvgToPptxMultiResult,
)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer


class SvgToPptxPagesMixin:
    """Sequential multi-page conversion and variant expansion."""

    def convert_pages(
        self,
        pages: Sequence[SvgPageSource],
        output_path: Path,
        *,
        tracer: ConversionTracer | None = None,
        split_fallback_variants: bool = False,
        render_tiers: bool = False,
        parallel: bool = False,
        max_workers: int | None = None,
        embed_trace_docprops: bool | None = None,
    ) -> SvgToPptxMultiResult:
        """Convert multiple SVG payloads into a multi-slide PPTX."""

        if not pages:
            raise SvgConversionError(
                "At least one SVG page is required for multi-slide conversion."
            )

        from svg2ooxml.core.tracing import ConversionTracer

        packaging_tracer = tracer or ConversionTracer()

        if parallel and not render_tiers and not split_fallback_variants:
            return self._convert_pages_parallel(
                pages,
                output_path,
                packaging_tracer,
                max_workers=max_workers,
                embed_trace_docprops=embed_trace_docprops,
            )

        from svg2ooxml.core.pptx_exporter_pages import build_page_result

        page_results: list[SvgPageResult] = []
        slide_count = 0

        with self._builder.begin_streaming(tracer=packaging_tracer) as stream:
            for index, page in enumerate(pages, start=1):
                if render_tiers:
                    from svg2ooxml.core import pptx_exporter as exporter_api

                    tier_variants = exporter_api.build_fidelity_tier_variants()
                    page_seed = page
                    if not page.title and not page.name:
                        page_seed = SvgPageSource(
                            svg_text=page.svg_text,
                            title=f"Slide {index}",
                            name=page.name,
                            metadata=page.metadata,
                        )
                    variant_pages = exporter_api.expand_page_with_variants(
                        page_seed, tier_variants
                    )
                    for variant_page in variant_pages:
                        variant_metadata = read_page_render_metadata(
                            variant_page.metadata
                        )
                        variant_tracer = ConversionTracer()
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_metadata.policy_overrides,
                            source_path=variant_metadata.source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()
                        page_result = build_page_result(
                            variant_page,
                            variant_scene,
                            variant_report,
                            fallback_title=f"Slide {index}",
                            variant_type=variant_metadata.variant_type,
                        )

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(page_result)
                    continue

                page_metadata = read_page_render_metadata(
                    page.metadata,
                    default_variant_type="base",
                )
                base_tracer = ConversionTracer()
                render_result, scene = self._render_svg(
                    page.svg_text,
                    base_tracer,
                    page_metadata.policy_overrides,
                    source_path=page_metadata.source_path,
                )
                report_dict = base_tracer.report().to_dict()
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

                if split_fallback_variants:
                    from svg2ooxml.core import pptx_exporter as exporter_api

                    variants = exporter_api.derive_variants_from_trace(
                        report_dict, enable_split=True
                    )
                    variant_pages = exporter_api.expand_page_with_variants(
                        page, variants
                    )
                    for variant_page in variant_pages:
                        variant_metadata = read_page_render_metadata(
                            variant_page.metadata
                        )
                        variant_tracer = ConversionTracer()
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_metadata.policy_overrides,
                            source_path=variant_metadata.source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()
                        variant_page_result = build_page_result(
                            variant_page,
                            variant_scene,
                            variant_report,
                            fallback_title=(
                                f"{page_result.title} "
                                f"({variant_metadata.variant_type})"
                            ),
                            variant_type=variant_metadata.variant_type,
                        )

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(variant_page_result)

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


__all__ = ["SvgToPptxPagesMixin"]
