"""Stitch slide bundles into a single PPTX package."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder

from .bundles import load_job_bundles


def stitch_job_bundles(
    job_id: str,
    output_path: str | Path,
    *,
    base_dir: Path | None = None,
    slide_size_mode: str | None = None,
) -> Path:
    render_results = load_job_bundles(job_id, base_dir=base_dir)
    return stitch_render_results(render_results, output_path, slide_size_mode=slide_size_mode)


def stitch_render_results(
    render_results: Iterable[DrawingMLRenderResult],
    output_path: str | Path,
    *,
    slide_size_mode: str | None = None,
) -> Path:
    results = list(render_results)
    if not results:
        raise ValueError("No slide bundles available to stitch.")
    builder = PPTXPackageBuilder(slide_size_mode=slide_size_mode)
    return builder.build_from_results(results, output_path)


__all__ = ["stitch_job_bundles", "stitch_render_results"]
