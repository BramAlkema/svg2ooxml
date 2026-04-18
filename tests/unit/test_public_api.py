"""Coverage for the curated public svg2ooxml API."""

from __future__ import annotations

import importlib


def test_public_module_exposes_drawingml_writer_surface() -> None:
    public = importlib.import_module("svg2ooxml.public")

    assert hasattr(public, "DrawingMLWriter")
    assert hasattr(public, "DrawingMLRenderResult")


def test_top_level_package_keeps_api_compat_namespace_lazy_import() -> None:
    svg2ooxml = importlib.import_module("svg2ooxml")

    api = svg2ooxml.api

    assert api.__name__ == "svg2ooxml.api"
