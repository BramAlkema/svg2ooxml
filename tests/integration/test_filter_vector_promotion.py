from __future__ import annotations

from pathlib import Path

import pytest

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def _convert(svg_text: str, tmp_path: Path, strategy: str) -> dict[str, object]:
    exporter = SvgToPptxExporter(filter_strategy=strategy)
    output_path = tmp_path / f"{strategy}.pptx"
    result = exporter.convert_string(svg_text, output_path)
    assert output_path.exists()
    return result.trace_report or {}


@pytest.mark.parametrize("svg_name", ["lighting_specular.svg", "lighting_point.svg"])
def test_resvg_vector_promotion_records_metrics(tmp_path: Path, svg_name: str) -> None:
    svg_markup = (ASSETS_DIR / svg_name).read_text(encoding="utf-8")

    resvg_report = _convert(svg_markup, tmp_path, "resvg")
    legacy_report = _convert(svg_markup, tmp_path, "legacy")

    resvg_metrics = resvg_report.get("resvg_metrics", {})
    assert resvg_metrics.get("promotions", 0) >= 1
    assert resvg_metrics.get("lighting_promotions", 0) >= 1

    legacy_metrics = legacy_report.get("resvg_metrics", {})
    assert legacy_metrics.get("promotions", 0) == 0
