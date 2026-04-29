"""Convert SVG documents to PPTX."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import click

from svg2ooxml.core.pptx_exporter import (
    SvgConversionError,
    SvgPageSource,
    SvgToPptxExporter,
)
from svg2ooxml.core.tracing import ConversionTracer

from ._convert_sources import derive_default_output, load_source, looks_like_uri
from ._convert_sources import (
    split_pages as split_svg_pages,
)


@click.command()
@click.argument("input_source", type=str)
@click.argument("output_file", type=click.Path(path_type=Path), required=False)
@click.option(
    "--slide",
    "extra_slides",
    multiple=True,
    help="Additional SVG sources (path or URI) to append as slides.",
)
@click.option(
    "--split-pages/--no-split-pages",
    default=True,
    help="Automatically split the primary SVG into multiple slides when multipage markers are detected.",
)
@click.option(
    "--split-fallback-slides/--no-split-fallback-slides",
    default=False,
    help="Duplicate slides to showcase fallback renderings (e.g., native vs EMF/bitmap).",
)
@click.option(
    "--render-tiers/--no-render-tiers",
    default=False,
    help="Render four fidelity tiers per slide (direct, mimic, EMF fallback, bitmap fallback).",
)
@click.option(
    "--parallel/--no-parallel",
    default=False,
    help="Render slides in parallel using a thread pool.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Emit debug logs and write a conversion trace report alongside the PPTX.",
)
@click.option(
    "--embed-trace-docprops/--no-embed-trace-docprops",
    default=False,
    help="Embed conversion trace JSON in PPTX docProps/custom.xml.",
)
def convert(  # noqa: PLR0913  (CLI surface)
    input_source: str,
    output_file: Path | None,
    extra_slides: tuple[str, ...],
    split_pages: bool,
    split_fallback_slides: bool,
    render_tiers: bool,
    parallel: bool,
    verbose: bool,
    embed_trace_docprops: bool,
) -> None:
    """Convert INPUT_SOURCE (SVG) to a PPTX."""

    exporter = SvgToPptxExporter()
    tracer: ConversionTracer | None = None
    if verbose or embed_trace_docprops:
        logging.basicConfig(level=logging.DEBUG)
        tracer = ConversionTracer(
            logger=logging.getLogger("svg2ooxml.map"), collect_events=True
        )

    primary_svg, primary_title, primary_path = load_source(input_source)
    primary_uri = input_source if looks_like_uri(input_source) else None

    slides: list[SvgPageSource] = []
    if split_pages:
        split_results = split_svg_pages(primary_svg, primary_title)
        if split_results:
            slides.extend(split_results)
        else:
            slides.append(
                SvgPageSource(
                    svg_text=primary_svg, title=primary_title, name=primary_title
                )
            )
    else:
        slides.append(
            SvgPageSource(svg_text=primary_svg, title=primary_title, name=primary_title)
        )
    for extra in extra_slides:
        svg_text, slide_title, _ = load_source(extra)
        slides.append(
            SvgPageSource(
                svg_text=svg_text,
                title=slide_title,
                name=slide_title,
                metadata={"source": extra},
            )
        )

    target_path = output_file or derive_default_output(primary_path, primary_uri)

    click.echo(f"📄 Converting: {input_source}")
    if extra_slides:
        click.echo(f"➕ Additional slides: {len(extra_slides)}")
    if split_pages and len(slides) > 1:
        click.echo(f"🧩 Detected {len(slides)} page(s) in the primary SVG")
    click.echo(f"📦 Output: {target_path}")

    try:
        if (
            len(slides) == 1
            and not extra_slides
            and not split_fallback_slides
            and not render_tiers
        ):
            result = exporter.convert_string(
                slides[0].svg_text,
                target_path,
                tracer=tracer,
                embed_trace_docprops=embed_trace_docprops,
            )
            slide_count = result.slide_count
            trace_payload: dict[str, Any] | None = result.trace_report
        else:
            multi_result = exporter.convert_pages(
                slides,
                target_path,
                tracer=tracer,
                split_fallback_variants=split_fallback_slides,
                render_tiers=render_tiers,
                parallel=parallel,
                embed_trace_docprops=embed_trace_docprops,
            )
            slide_count = multi_result.slide_count
            trace_payload = {
                "aggregated": multi_result.aggregated_trace_report,
                "packaging": multi_result.packaging_report,
                "pages": [
                    {"title": page.title, "trace_report": page.trace_report}
                    for page in multi_result.page_results
                ],
            }
    except SvgConversionError as exc:
        click.echo(f"❌ Conversion failed: {exc}", err=True)
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure
        click.echo(f"❌ Unexpected error: {exc}", err=True)
        raise SystemExit(1) from exc

    pptx_path = target_path
    click.echo(
        f"✅ Conversion complete: {pptx_path} ({slide_count} slide{'s' if slide_count != 1 else ''})"
    )

    if verbose and trace_payload:
        trace_path = target_path.with_suffix(target_path.suffix + ".trace.json")
        trace_path.write_text(json.dumps(trace_payload, indent=2), encoding="utf-8")
        click.echo(f"📝 Trace report written to: {trace_path}")


__all__ = ["convert"]
