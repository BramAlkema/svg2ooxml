"""Public result types for the SVG to PPTX exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SvgConversionError(RuntimeError):
    """Raised when the SVG to PPTX conversion fails."""


@dataclass(frozen=True)
class SvgToPptxResult:
    """Result describing the generated PPTX artifact."""

    pptx_path: Path
    slide_count: int
    trace_report: dict[str, Any] | None = None


@dataclass(frozen=True)
class SvgPageSource:
    """Input payload describing a single SVG slide."""

    svg_text: str
    title: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SvgPageResult:
    """Per-page conversion result."""

    title: str | None
    trace_report: dict[str, Any]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SvgToPptxMultiResult:
    """Result describing a multi-slide PPTX conversion."""

    pptx_path: Path
    slide_count: int
    page_results: list[SvgPageResult]
    packaging_report: dict[str, Any]
    aggregated_trace_report: dict[str, Any]


__all__ = [
    "SvgConversionError",
    "SvgPageResult",
    "SvgPageSource",
    "SvgToPptxMultiResult",
    "SvgToPptxResult",
]
