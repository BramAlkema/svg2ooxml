"""High-level converter that now wires in the resvg/usvg normalizer."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .pipeline.pipeline import DEFAULT_STAGE_NAMES, ConversionPipeline
from .resvg.normalizer import NormalizationResult, normalize_svg_file
from .resvg.parser.options import Options


@dataclass(frozen=True)
class ConvertResult:
    """Result object capturing the normalized tree and stage bookkeeping."""

    success: bool
    normalized: NormalizationResult | None
    steps_ran: Iterable[str]


class Converter:
    """Converter that parses the SVG and returns a normalized usvg tree."""

    def __init__(self, pipeline: ConversionPipeline | None = None) -> None:
        self._pipeline = pipeline or ConversionPipeline()

    def convert(
        self,
        svg_path: str,
        output_path: str,
        *,
        options: Options | None = None,
    ) -> ConvertResult:
        """Convert an SVG into OOXML artifacts (normalization-only for now)."""
        del output_path  # OOXML emission lands in a later integration pass.

        normalized = normalize_svg_file(svg_path, options=options)

        return ConvertResult(
            success=True,
            normalized=normalized,
            steps_ran=self._pipeline.describe_stage_names(),
        )


__all__ = ["Converter", "ConvertResult", "DEFAULT_STAGE_NAMES"]
