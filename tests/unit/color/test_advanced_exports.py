"""Basic coverage for the public advanced colour exports."""

from __future__ import annotations

import importlib

import pytest


def test_advanced_module_exposes_expected_symbols() -> None:
    advanced = importlib.import_module("svg2ooxml.color.advanced")

    assert hasattr(advanced, "AdvancedColor")
    assert hasattr(advanced, "require_color_engine")
    assert hasattr(advanced, "COLOR_ENGINE_AVAILABLE")

    if advanced.COLOR_ENGINE_AVAILABLE:
        colour = advanced.AdvancedColor("#336699")
        assert colour.hex(include_hash=True) == "#336699"
    else:
        with pytest.raises(RuntimeError):
            advanced.require_color_engine()
        try:
            instance = advanced.AdvancedColor("#000000")
        except RuntimeError:
            return
        assert hasattr(instance, "rgba")
        assert hasattr(instance, "alpha")
