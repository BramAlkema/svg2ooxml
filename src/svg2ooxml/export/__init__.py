"""Public frame-conversion helpers for library consumers."""

from .converter import (
    ConversionArtifacts,
    FontDiagnostics,
    collect_font_diagnostics,
    render_pptx_for_frames,
    render_pptx_for_frames_parallel,
)
from .models import RequestedFont, SVGFrame

__all__ = [
    "ConversionArtifacts",
    "FontDiagnostics",
    "RequestedFont",
    "SVGFrame",
    "collect_font_diagnostics",
    "render_pptx_for_frames",
    "render_pptx_for_frames_parallel",
]
