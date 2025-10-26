"""Tests for smart font converter service wiring."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.services.font_converter import (
    BasicSmartFontConverter,
    SmartFontConverter,
    build_smart_font_converter,
)
from svg2ooxml.services.fonts.service import FontMatch, FontQuery


def test_build_smart_font_converter_returns_project_converter() -> None:
    converter = build_smart_font_converter(services={}, logger=None)
    assert isinstance(converter, SmartFontConverter)


def test_build_smart_font_converter_uses_svg2pptx_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "svg2pptx.core.converters.font.smart_converter"
    dummy_module = ModuleType(module_name)

    class DummySmartFontConverter:
        def __init__(self, services, policy) -> None:
            self.services = services
            self.policy = policy

        def convert(self, frame, context):
            return frame

    dummy_module.SmartFontConverter = DummySmartFontConverter

    package_names = [
        "svg2pptx",
        "svg2pptx.core",
        "svg2pptx.core.converters",
        "svg2pptx.core.converters.font",
    ]
    for name in package_names:
        if name not in sys.modules:
            sys.modules[name] = ModuleType(name)
    sys.modules[module_name] = dummy_module

    try:
        converter = build_smart_font_converter(services={}, logger=None)
        assert isinstance(converter, DummySmartFontConverter)
    finally:
        for name in [module_name, *package_names]:
            sys.modules.pop(name, None)


class DummyFontService:
    def find_font(self, query: FontQuery) -> FontMatch | None:
        return FontMatch(
            family=f"{query.family}-resolved",
            path=f"/fonts/{query.family.lower()}.ttf",
            weight=query.weight,
            style=query.style,
            found_via="dummy",
        )


class DummyServices:
    def __init__(self) -> None:
        self._font_service = DummyFontService()

    @property
    def font_service(self) -> DummyFontService:
        return self._font_service

    def resolve(self, name: str, default: object | None = None) -> object | None:
        if name == "font":
            return self._font_service
        return default


def test_smart_font_converter_enriches_metadata() -> None:
    services = DummyServices()
    converter = SmartFontConverter(services, policy=None)
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 10, 10),
        runs=[
            Run(text="Hello", font_family="Example", font_size_pt=12.0),
            Run(text="World", font_family="sans-serif", font_size_pt=12.0, italic=True),
        ],
        metadata={}
    )

    enriched = converter.convert(frame, context={})
    smart_meta = enriched.metadata.get("smart_font", {})
    assert smart_meta.get("total_runs") == 2
    assert smart_meta.get("matched_runs") == 2
    assert smart_meta.get("confidence") == 1.0
    assert smart_meta.get("runs")
