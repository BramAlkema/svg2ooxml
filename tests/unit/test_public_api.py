"""Coverage for the curated public svg2ooxml API."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path


def _pyproject() -> dict:
    root = Path(__file__).resolve().parents[2]
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def test_public_module_exposes_drawingml_writer_surface() -> None:
    public = importlib.import_module("svg2ooxml.public")

    assert hasattr(public, "DrawingMLWriter")
    assert hasattr(public, "DrawingMLRenderResult")


def test_top_level_package_keeps_api_compat_namespace_lazy_import() -> None:
    svg2ooxml = importlib.import_module("svg2ooxml")

    api = svg2ooxml.api

    assert api.__name__ == "svg2ooxml.api"


def test_package_discovery_declares_converter_cli_and_tool_surfaces() -> None:
    package_find = _pyproject()["tool"]["setuptools"]["packages"]["find"]

    assert package_find["where"] == ["src", "."]
    assert package_find["include"] == ["svg2ooxml*", "figma2gslides*", "cli*"]
    assert package_find["namespaces"] is False


def test_figma2gslides_extra_declares_tool_runtime_dependencies() -> None:
    extras = _pyproject()["project"]["optional-dependencies"]
    figma_extra = extras["figma2gslides"]
    normalized = {dependency.split(">=", maxsplit=1)[0] for dependency in figma_extra}

    assert {
        "fastapi",
        "uvicorn[standard]",
        "python-multipart",
        "PyJWT",
        "cryptography",
        "google-cloud-firestore",
        "google-cloud-storage",
        "google-api-python-client",
        "google-auth",
        "google-auth-oauthlib",
    } <= normalized


def test_figma2gslides_top_level_import_is_lightweight_tool_marker() -> None:
    sys.modules.pop("figma2gslides.app", None)

    figma2gslides = importlib.import_module("figma2gslides")

    assert figma2gslides.TOOL_NAME == "figma2gslides"
    assert figma2gslides.TOOL_SURFACE == "svg2ooxml-tool"
    assert "figma2gslides.app" not in sys.modules
