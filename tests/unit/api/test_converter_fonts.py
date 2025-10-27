from __future__ import annotations

from svg2ooxml.api.models import RequestedFont
from svg2ooxml.api.services.converter import collect_font_diagnostics
from svg2ooxml.services.fonts import FontMatch


class DummyFontService:
    def __init__(self, mapping):
        self.mapping = mapping

    def clear_cache(self) -> None:
        pass

    def find_font(self, query):
        return self.mapping.get(query.family)


def test_collect_font_diagnostics_reports_missing_and_embedded() -> None:
    font = RequestedFont.model_validate("Example Sans")
    match = FontMatch(
        family="Example Sans",
        path="/tmp/example-sans.ttf",
        weight=400,
        style="normal",
        found_via="test",
        metadata={"source": "stub"},
    )
    service = DummyFontService({"Example Sans": match})
    diagnostics = collect_font_diagnostics(service, [font])

    assert diagnostics.embedded_fonts[0]["family"] == "Example Sans"
    assert diagnostics.missing_fonts == []


def test_collect_font_diagnostics_handles_missing_fonts() -> None:
    fonts = [RequestedFont.model_validate("Missing Font")]
    service = DummyFontService({})
    diagnostics = collect_font_diagnostics(service, fonts)
    assert diagnostics.missing_fonts == ["Missing Font"]
