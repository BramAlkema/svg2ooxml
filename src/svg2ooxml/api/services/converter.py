"""Helpers that drive SVG frame conversion into PPTX artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.core.parser.preprocess.services import build_parser_services
from svg2ooxml.core.parser.batch.coordinator import convert_svg_batch_parallel
from svg2ooxml.core.parser.batch.bundles import new_job_id
from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.services.fonts import FontMatch, FontQuery
from svg2ooxml.services.fonts.providers.directory import DirectoryFontProvider

from ..models import RequestedFont, SVGFrame


@dataclass(frozen=True)
class FontDiagnostics:
    """Information about requested fonts resolved during conversion."""

    embedded_fonts: list[dict[str, str]]
    missing_fonts: list[str]


@dataclass(frozen=True)
class ConversionArtifacts:
    """Artefacts returned after rendering frames to a PPTX package."""

    pptx_path: Path
    slide_count: int
    aggregated_trace: dict[str, object]
    packaging_report: dict[str, object]
    page_titles: list[str]
    font_diagnostics: FontDiagnostics


def render_pptx_for_frames(
    frames: Sequence[SVGFrame],
    output_path: Path,
    *,
    requested_fonts: Sequence[RequestedFont] = (),
    extra_font_directories: Iterable[Path] = (),
) -> ConversionArtifacts:
    """Convert SVG frames into a PPTX located at *output_path*."""

    if not frames:
        raise ValueError("At least one SVG frame is required for conversion.")

    parser_services = build_parser_services()
    services = parser_services.services
    font_service = services.font_service

    # Register any dynamically downloaded font directories.
    registered_dirs: list[Path] = []
    if font_service and extra_font_directories:
        for directory in extra_font_directories:
            normalised = Path(directory).expanduser()
            if not normalised.exists() or not normalised.is_dir():
                continue
            font_service.register_provider(DirectoryFontProvider((normalised,)))
            registered_dirs.append(normalised)
        if registered_dirs:
            font_service.clear_cache()

    parser = SVGParser(ParserConfig(), services=parser_services)
    exporter = SvgToPptxExporter(parser=parser)

    svg_pages: list[SvgPageSource] = []
    for index, frame in enumerate(frames, start=1):
        metadata = {
            "frame": {
                "name": frame.name,
                "width": frame.width,
                "height": frame.height,
                "order": index,
            }
        }
        page_title = frame.name or f"Slide {index}"
        svg_pages.append(
            SvgPageSource(
                svg_text=frame.svg_content,
                title=page_title,
                name=frame.name or page_title,
                metadata=metadata,
            )
        )

    tracer = ConversionTracer()
    pptx_result = exporter.convert_pages(svg_pages, output_path, tracer=tracer)

    diagnostics = collect_font_diagnostics(font_service, requested_fonts)

    page_titles = [page.title or f"Slide {idx}" for idx, page in enumerate(pptx_result.page_results, start=1)]

    return ConversionArtifacts(
        pptx_path=output_path,
        slide_count=pptx_result.slide_count,
        aggregated_trace=pptx_result.aggregated_trace_report,
        packaging_report=pptx_result.packaging_report,
        page_titles=page_titles,
        font_diagnostics=diagnostics,
    )


def render_pptx_for_frames_parallel(
    frames: Sequence[SVGFrame],
    output_path: Path,
    *,
    requested_fonts: Sequence[RequestedFont] = (),
    extra_font_directories: Iterable[Path] = (),
    job_id: str | None = None,
    bundle_dir: Path | None = None,
    openxml_validator: str | None = None,
    openxml_policy: str = "strict",
    openxml_required: bool = False,
    timeout_s: float | None = None,
    bail: bool = True,
) -> ConversionArtifacts:
    """Convert SVG frames into a PPTX using parallel slide bundling."""

    if not frames:
        raise ValueError("At least one SVG frame is required for conversion.")

    parser_services = build_parser_services()
    services = parser_services.services
    font_service = services.font_service

    registered_dirs: list[Path] = []
    if font_service and extra_font_directories:
        for directory in extra_font_directories:
            normalised = Path(directory).expanduser()
            if not normalised.exists() or not normalised.is_dir():
                continue
            font_service.register_provider(DirectoryFontProvider((normalised,)))
            registered_dirs.append(normalised)
        if registered_dirs:
            font_service.clear_cache()

    file_list: list[dict[str, str]] = []
    page_titles: list[str] = []
    for index, frame in enumerate(frames, start=1):
        slide_name = frame.name or f"slide-{index}"
        file_list.append(
            {
                "filename": f"{slide_name}.svg",
                "content": frame.svg_content,
            }
        )
        page_titles.append(frame.name or f"Slide {index}")

    assigned_job_id = job_id or new_job_id("export")
    bundle_root = bundle_dir or (output_path.parent / f"bundles_{assigned_job_id}")
    conversion_options = {
        "bundle_dir": str(bundle_root),
        "font_dirs": [str(path) for path in registered_dirs],
    }

    result = convert_svg_batch_parallel(
        file_list,
        output_path,
        conversion_options=conversion_options,
        job_id=assigned_job_id,
        wait=True,
        timeout_s=timeout_s,
        bail=bail,
        force_inline=False,
        bundle_dir=bundle_root,
        openxml_validator=openxml_validator,
        openxml_policy=openxml_policy,
        openxml_required=openxml_required,
    )

    if not result.get("success"):
        raise ValueError(result.get("error_message") or "Parallel conversion failed")

    diagnostics = collect_font_diagnostics(font_service, requested_fonts)
    packaging_report = {
        "stage_totals": {},
        "openxml_valid": result.get("openxml_valid"),
        "openxml_messages": result.get("openxml_messages"),
    }

    return ConversionArtifacts(
        pptx_path=Path(result.get("output_path") or output_path),
        slide_count=len(frames),
        aggregated_trace={},
        packaging_report=packaging_report,
        page_titles=page_titles,
        font_diagnostics=diagnostics,
    )


def collect_font_diagnostics(
    font_service,
    requested_fonts: Sequence[RequestedFont],
) -> FontDiagnostics:
    """Return information about embedded/missing fonts for the conversion."""

    embedded: list[dict[str, str]] = []
    missing: list[str] = []

    if not requested_fonts:
        return FontDiagnostics(embedded_fonts=embedded, missing_fonts=missing)

    if font_service is None:
        return FontDiagnostics(
            embedded_fonts=embedded,
            missing_fonts=[font.family for font in requested_fonts],
        )

    font_service.clear_cache()

    for font in requested_fonts:
        query = FontQuery(
            family=font.family,
            weight=font.weight or 400,
            style=font.style,
            fallback_chain=tuple(font.fallback or []),
        )
        match: FontMatch | None = font_service.find_font(query)
        if match and match.path:
            embedded.append(
                {
                    "family": match.family,
                    "path": match.path,
                    "found_via": match.found_via,
                    "source": str(match.metadata.get("source", "")),
                }
            )
        else:
            missing.append(font.family)

    return FontDiagnostics(embedded_fonts=embedded, missing_fonts=missing)


__all__ = [
    "ConversionArtifacts",
    "FontDiagnostics",
    "collect_font_diagnostics",
    "render_pptx_for_frames",
    "render_pptx_for_frames_parallel",
]
