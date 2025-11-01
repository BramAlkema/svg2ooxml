from __future__ import annotations

import dataclasses
from typing import Any

import pytest

pytest.importorskip("skia")

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.ir import convert_parser_output
from svg2ooxml.services import configure_services
from svg2ooxml.render import render
from svg2ooxml.core.resvg import normalize_svg_string


@dataclasses.dataclass(slots=True)
class PipelineHarness:
    svg_markup: str
    filter_strategy: str | None = "resvg"

    def render_scene(self) -> tuple[Any, Any, ConversionTracer]:
        normalised = normalize_svg_string(self.svg_markup)
        tree = normalised.tree
        surface = render(tree)
        services = configure_services(filter_strategy=self.filter_strategy)
        services.register("graphic_surface", surface)
        tracer = ConversionTracer()
        parse_result = normalised.parse_result
        scene = convert_parser_output(parse_result, services=services, tracer=tracer)
        return surface, scene, tracer


def _export_svg(svg: str, strategy: str | None = "resvg") -> ConversionTracer:
    exporter = SvgToPptxExporter(filter_strategy=strategy)
    tracer = ConversionTracer()
    result, _ = exporter._render_svg(svg, tracer)  # type: ignore[attr-defined]
    assert result is not None
    return tracer.report()


SIMPLE_FILTER = """
<svg xmlns='http://www.w3.org/2000/svg' width='80' height='60'>
  <defs>
    <filter id='blur'>
      <feGaussianBlur stdDeviation='4'/>
    </filter>
  </defs>
  <rect id='rect' x='10' y='10' width='40' height='20' fill='#f06' filter='url(#blur)'/>
</svg>
""".strip()


SIMPLE_MASK = """
<svg xmlns='http://www.w3.org/2000/svg' width='80' height='60'>
  <defs>
    <mask id='fade'>
      <linearGradient id='grad' gradientUnits='objectBoundingBox'>
        <stop offset='0%' stop-color='white'/>
        <stop offset='100%' stop-color='black'/>
      </linearGradient>
      <rect x='0' y='0' width='80' height='60' fill='url(#grad)'/>
    </mask>
  </defs>
  <rect id='masked' x='0' y='0' width='80' height='60' fill='#2b8cbe' mask='url(#fade)'/>
</svg>
""".strip()


SIMPLE_CLIP = """
<svg xmlns='http://www.w3.org/2000/svg' width='80' height='60'>
  <defs>
    <clipPath id='cutout'>
      <circle cx='40' cy='30' r='20'/>
    </clipPath>
  </defs>
  <rect x='0' y='0' width='80' height='60' fill='#3182bd' clip-path='url(#cutout)'/>
</svg>
""".strip()


@pytest.mark.parametrize(
    "svg_markup",
    [SIMPLE_FILTER, SIMPLE_MASK, SIMPLE_CLIP],
)
def test_pipeline_resvg_exporter(svg_markup: str) -> None:
    report = _export_svg(svg_markup, strategy="resvg")
    stages = [event.action for event in report.stage_events if event.stage == "filter"]
    assert "resvg_success" in stages


@pytest.mark.parametrize(
    "svg_markup",
    [SIMPLE_FILTER],
)
def test_pipeline_legacy_strategy(svg_markup: str) -> None:
    report = _export_svg(svg_markup, strategy="legacy")
    stages = [event.action for event in report.stage_events if event.stage == "filter"]
    assert "resvg_attempt" not in stages


@pytest.mark.parametrize(
    "svg_markup",
    [SIMPLE_FILTER, SIMPLE_MASK, SIMPLE_CLIP],
)
def test_render_pipeline_surface(svg_markup: str) -> None:
    harness = PipelineHarness(svg_markup)
    surface, scene, tracer = harness.render_scene()
    assert surface.width > 0 and surface.height > 0
    assert scene is not None
    report = tracer.report()
    assert report.paint_totals is not None
