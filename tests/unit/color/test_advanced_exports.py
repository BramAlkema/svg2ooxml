"""Basic coverage for the public advanced colour exports."""

from __future__ import annotations

import importlib

import pytest


def test_advanced_module_exposes_expected_symbols() -> None:
    engine = importlib.import_module("svg2ooxml.color.advanced.engine")

    assert hasattr(engine, "AdvancedColor")
    assert hasattr(engine, "require_color_engine")
    assert hasattr(engine, "COLOR_ENGINE_AVAILABLE")

    if engine.COLOR_ENGINE_AVAILABLE:
        colour = engine.AdvancedColor("#336699")
        assert colour.hex(include_hash=True) == "#336699"
    else:
        with pytest.raises(RuntimeError):
            engine.require_color_engine()
        try:
            instance = engine.AdvancedColor("#000000")
        except RuntimeError:
            return
        assert hasattr(instance, "rgba")
        assert hasattr(instance, "alpha")
