"""Tests for the placeholder converter."""

from svg2ooxml.core.converter import Converter
from svg2ooxml.core.pipeline import DEFAULT_STAGE_NAMES


def test_converter_returns_success_with_default_stages(tmp_path) -> None:
    converter = Converter()

    svg_path = tmp_path / "input.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'><rect width='1' height='1'/></svg>")

    result = converter.convert(str(svg_path), "output.pptx")

    assert result.success is True
    assert tuple(result.steps_ran) == DEFAULT_STAGE_NAMES
