from __future__ import annotations

from svg2ooxml.api.models import RequestedFont


def test_requested_font_accepts_string() -> None:
    font = RequestedFont.model_validate("Inter")
    assert font.family == "Inter"
    assert font.fallback == []
    assert font.source_url is None


def test_requested_font_coerces_fallback_iterable() -> None:
    payload = {"family": "Roboto", "fallback": ("Arial", "Helvetica")}
    font = RequestedFont.model_validate(payload)
    assert font.fallback == ["Arial", "Helvetica"]
