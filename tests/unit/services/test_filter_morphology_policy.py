"""Policy-aware tests for morphology primitive."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.units import px_to_emu
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult
from tests.unit.filters.policy import assert_fallback


def _resolve_with_policy(markup: str, policy: dict[str, object]) -> list[FilterEffectResult]:
    service = FilterService()
    element = etree.fromstring(markup)
    filter_id = element.get("id", "f")
    service.register_filter(filter_id, element)
    return service.resolve_effects(filter_id, context={"policy": policy})


def test_morphology_dilate_clamps_radius_and_alpha_via_policy() -> None:
    results = _resolve_with_policy(
        "<filter id='f'><feMorphology operator='dilate' radius='20' style='opacity:0.9'/></filter>",
        {"max_glow_radius": 10, "max_glow_alpha": 0.6},
    )
    assert results
    effect = results[0]
    assert effect.metadata["radius_max"] == 20.0
    assert effect.metadata["radius_effective"] == 10.0
    assert effect.metadata["clamped_radius"] == 10.0
    assert effect.metadata["radius_emu"] == int(px_to_emu(10))
    assert effect.metadata["alpha"] == 0.6
    assert effect.metadata.get("alpha_clamped") is True
    assert effect.metadata["policy"]["max_glow_radius"] == 10.0
    assert effect.metadata["policy"]["max_glow_alpha"] == 0.6


def test_morphology_dilate_respects_colour_preference_policy() -> None:
    svg = (
        "<filter id='f'>"
        "  <feFlood flood-color='#ABCDEF' flood-opacity='0.3' result='flood'/>"
        "  <feMorphology operator='dilate' radius='5' style='color:#123456' in='flood'/>"
        "</filter>"
    )
    results = _resolve_with_policy(svg, {"preferred_glow_strategy": "flood"})
    assert results
    effect = results[1]
    assert_fallback(effect, modern=None)
    assert effect.metadata.get("color") == "ABCDEF"
    assert str(effect.metadata.get("color_strategy", "")).startswith("pipeline:flood_color")
