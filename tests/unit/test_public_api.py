"""Coverage for the curated public svg2ooxml API."""

from __future__ import annotations

import importlib


def test_public_module_exposes_drawingml_writer_surface() -> None:
    public = importlib.import_module("svg2ooxml.public")

    assert hasattr(public, "DrawingMLWriter")
    assert hasattr(public, "DrawingMLRenderResult")
