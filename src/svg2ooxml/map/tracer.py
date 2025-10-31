"""Tracer compatibility surface forwarding to the core tracing module."""

from __future__ import annotations

from svg2ooxml.core.tracing.conversion import (
    ConversionTracer,
    GeometryTrace,
    PaintTrace,
    StageTrace,
    TraceReport,
)

__all__ = [
    "ConversionTracer",
    "TraceReport",
    "GeometryTrace",
    "PaintTrace",
    "StageTrace",
]
