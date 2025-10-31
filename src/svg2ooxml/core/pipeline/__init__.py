"""Minimal metadata describing the conversion pipeline stages.

The svg2ooxml project orchestrates conversions through the service graph
materialised by :class:`svg2ooxml.services.ConversionServices` and the higher
level :class:`svg2ooxml.core.pptx_exporter.SvgToPptxExporter`.  This module does
not execute the pipeline; it simply captures the canonical stage order so tools
that need to introspect or display the sequence (CLI status, progress bars,
logging) have a source of truth.

Consumers that actually need to run conversions should continue to wire up
``SvgToPptxExporter`` (or the service registry) rather than attempting to call
into this module.
"""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_STAGE_NAMES: tuple[str, ...] = (
    "parse_svg",      # DOM load, preprocessing, CSS cascade, statistics.
    "map_shapes",     # Build the IR, resolve paints, fonts, clip/mask geometry.
    "apply_policy",   # Apply policy overrides (animation, colour, compatibility).
    "write_package",  # Emit DrawingML, package into PPTX.
)


class ConversionPipeline:
    """Simple placeholder exposing the canonical stage order.

    This class intentionally does not attempt to run the stages.  It exists so
    downstream tools can display or reason about the sequence while still using
    :class:`svg2ooxml.core.pptx_exporter.SvgToPptxExporter` (or the services
    API) for real work.
    """

    def __init__(self, stage_names: Iterable[str] | None = None) -> None:
        self._stage_names: tuple[str, ...] = tuple(stage_names or DEFAULT_STAGE_NAMES)

    @property
    def stages(self) -> tuple[str, ...]:
        """Return the configured stage names (read-only)."""
        return self._stage_names

    def describe_stage_names(self) -> tuple[str, ...]:
        """Return the ordered list of stage identifiers."""
        return self._stage_names


__all__ = ["ConversionPipeline", "DEFAULT_STAGE_NAMES"]
