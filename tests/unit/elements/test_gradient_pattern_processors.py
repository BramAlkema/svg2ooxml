from __future__ import annotations

from lxml import etree as ET

from svg2ooxml.color.bridge import ADVANCED_COLOR_ENGINE_AVAILABLE
from svg2ooxml.elements.gradient_processor import GradientProcessor
from svg2ooxml.elements.pattern_processor import PatternProcessor
from svg2ooxml.services import ConversionServices


def _make_services() -> ConversionServices:
    services = ConversionServices()
    services.register("gradient", {})
    services.register("pattern", {})
    return services


def test_gradient_processor_color_statistics() -> None:
    services = _make_services()
    processor = GradientProcessor(services)

    gradient = ET.fromstring(
        """
        <linearGradient>
            <stop offset="0%" stop-color="#ff0000" />
            <stop offset="100%" stop-color="rgb(0,128,0)" />
        </linearGradient>
        """
    )

    analysis = processor.analyze_gradient_element(gradient, context=None)

    assert analysis.colors_used == ["#FF0000", "#008000"]
    assert analysis.color_statistics["unique"] == 2
    assert analysis.color_statistics["complexity"] > 0
    assert analysis.color_statistics["recommended_space"] in {"srgb", "linear_rgb"}
    if ADVANCED_COLOR_ENGINE_AVAILABLE and analysis.color_statistics.get("advanced_available"):
        assert "hue_spread" in analysis.color_statistics


def test_pattern_processor_palette_summary() -> None:
    services = _make_services()
    processor = PatternProcessor(services)

    pattern = ET.fromstring(
        """
        <pattern patternUnits="userSpaceOnUse" width="10" height="10">
            <rect width="5" height="5" fill="#112233" />
            <rect x="5" width="5" height="5" fill="rgba(200, 40, 10, 0.5)" />
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern, context=None)

    assert analysis.colors_used == ["#112233", "#C8280A"]
    assert analysis.color_statistics is not None
    assert analysis.color_statistics["has_transparency"] is True
    assert analysis.color_statistics["recommended_space"] in {"srgb", "linear_rgb"}
