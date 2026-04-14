from __future__ import annotations

from pathlib import Path

import pytest

from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE
from svg2ooxml.services.fonts.svg_font_converter import convert_svg_font


@pytest.mark.skipif(not FONTFORGE_AVAILABLE, reason="FontForge not available")
def test_convert_svg_font_supports_legacy_non_namespaced_font_files() -> None:
    data = Path("tests/resources/FreeSerif.svg").read_bytes()

    converted = convert_svg_font(data, font_id="FreeSerif")

    assert converted is not None
    assert converted[:4] in (b"\x00\x01\x00\x00", b"true")


@pytest.mark.skipif(not FONTFORGE_AVAILABLE, reason="FontForge not available")
def test_convert_svg_font_keeps_namespaced_font_files_working() -> None:
    data = Path("tests/resources/SVGFreeSans.svg").read_bytes()

    converted = convert_svg_font(data, font_id="ascii")

    assert converted is not None
    assert converted[:4] in (b"\x00\x01\x00\x00", b"true")
