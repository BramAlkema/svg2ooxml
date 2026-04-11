from __future__ import annotations

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer


def test_render_svg_applies_color_transform_stack_policy_overrides() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">
      <defs>
        <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#356CFF"/>
          <stop offset="35%" stop-color="#6A4C93"/>
          <stop offset="68%" stop-color="#06D6A0"/>
          <stop offset="100%" stop-color="#FFD166"/>
        </linearGradient>
        <filter id="fx" x="-10%" y="-10%" width="120%" height="120%">
          <feColorMatrix type="saturate" values="0.55" result="sat"/>
          <feColorMatrix type="hueRotate" in="sat" values="135" result="hue"/>
          <feComponentTransfer in="hue">
            <feFuncA type="linear" slope="0.55" intercept="0"/>
          </feComponentTransfer>
        </filter>
      </defs>
      <rect x="40" y="60" width="280" height="180" rx="30" fill="url(#grad)"/>
      <rect x="440" y="60" width="280" height="180" rx="30" fill="url(#grad)" filter="url(#fx)"/>
    </svg>
    """

    exporter = SvgToPptxExporter(slide_size_mode="same")
    tracer = ConversionTracer()
    render_result, _ = (
        exporter._render_svg(  # type: ignore[attr-defined]
            svg,
            tracer,
            policy_overrides={
                "filter": {
                    "strategy": "native",
                    "enable_effect_dag": True,
                    "enable_native_color_transforms": True,
                    "enable_blip_effect_enrichment": True,
                }
            },
        )
    )

    assert '<a:satMod val="55000"/>' in render_result.slide_xml
    assert '<a:hueOff val="8100000"/>' in render_result.slide_xml
    assert '<a:alphaModFix amt="55000"/>' in render_result.slide_xml
