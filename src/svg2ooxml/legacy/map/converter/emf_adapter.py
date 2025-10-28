"""Compatibility shim for the legacy EMF path adapter."""

from __future__ import annotations

from svg2ooxml.drawingml.bridges.emf_path_adapter import (
    EMFPathAdapter,
    EMFPathResult,
    PathStyle,
)

__all__ = ["EMFPathAdapter", "EMFPathResult", "PathStyle"]
