"""Tests for the converter pipeline orchestration."""

from typing import Any

from svg2ooxml.core.converter import Converter
from svg2ooxml.core.pipeline.pipeline import DEFAULT_STAGE_NAMES, ConversionPipeline
from svg2ooxml.core.resvg.normalizer import NormalizationResult
from svg2ooxml.core.resvg.parser.options import Options


def test_converter_returns_success_with_default_stages(tmp_path) -> None:
    converter = Converter()

    svg_path = tmp_path / "input.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'><rect width='1' height='1'/></svg>")

    result = converter.convert(str(svg_path), "output.pptx")

    assert result.success is True
    assert tuple(result.steps_ran) == DEFAULT_STAGE_NAMES


def test_converter_uses_injected_pipeline(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_normalize(path: str, *, options: Options | None = None) -> NormalizationResult:
        captured["path"] = path
        captured["options"] = options
        return NormalizationResult(document=None, tree=None)

    monkeypatch.setattr("svg2ooxml.core.converter.normalize_svg_file", fake_normalize)

    stages = ("parse_svg", "write_package")
    pipeline = ConversionPipeline(stages)
    options = Options(font_family="Unit Test Sans")

    converter = Converter(pipeline=pipeline)
    result = converter.convert("memory.svg", "memory.pptx", options=options)

    assert result.success is True
    assert tuple(result.steps_ran) == stages
    assert result.normalized is not None
    assert captured["path"] == "memory.svg"
    assert captured["options"] is options
