"""Compatibility re-exports for frame conversion helpers."""

from svg2ooxml.export import (
    ConversionArtifacts,
    FontDiagnostics,
    collect_font_diagnostics,
    render_pptx_for_frames,
    render_pptx_for_frames_parallel,
)

__all__ = [
    "ConversionArtifacts",
    "FontDiagnostics",
    "collect_font_diagnostics",
    "render_pptx_for_frames",
    "render_pptx_for_frames_parallel",
]
