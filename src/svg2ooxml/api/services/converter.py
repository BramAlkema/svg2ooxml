"""Helpers that drive SVG frame conversion into PPTX artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter
from svg2ooxml.map.tracer import ConversionTracer
from svg2ooxml.parser.svg_parser import ParserConfig, SVGParser
from svg2ooxml.parser.preprocess.services import build_parser_services
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


__all__ = ["ConversionArtifacts", "FontDiagnostics", "collect_font_diagnostics", "render_pptx_for_frames"]
