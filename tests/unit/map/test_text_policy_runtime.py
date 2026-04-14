"""Text policy integration behaviour within the IR converter."""

from svg2ooxml.core.ir import IRConverter
from svg2ooxml.ir.text import Run
from svg2ooxml.policy import PolicyContext
from svg2ooxml.policy.providers.text import TextPolicyProvider
from svg2ooxml.policy.targets import PolicyTarget
from svg2ooxml.policy.text_policy import _build_balanced_decision
from svg2ooxml.services import ConversionServices


def _build_policy_context(options: dict[str, object]) -> PolicyContext:
    provider = TextPolicyProvider()
    payload = provider.evaluate(PolicyTarget("text"), options)
    return PolicyContext(selections={"text": payload})


def _make_converter(quality: str, **overrides: object) -> IRConverter:
    policy_context = _build_policy_context({"quality": quality, **overrides})
    return IRConverter(
        services=ConversionServices(),
        policy_context=policy_context,
        policy_engine=None,
    )


def test_low_quality_strips_effects_and_applies_fallback() -> None:
    converter = _make_converter("low")
    run = Run(
        text="Hello",
        font_family="Futura PT",
        font_size_pt=24.0,
        bold=True,
        italic=True,
    )

    updated, metadata = converter.text_converter.apply_policy(run)

    assert updated.bold is False
    assert updated.italic is False
    assert updated.font_family == "Arial"
    assert metadata["effects_stripped"] is True
    assert metadata["font_fallback"] == "Arial"
    assert metadata["glyph_fallback"] == "raster"
    assert metadata["prefer_vector_fallback"] is False


def test_balanced_policy_preserves_effects_without_claiming_outline_fallback() -> None:
    converter = _make_converter("balanced")
    run = Run(
        text="Outline",
        font_family="Handwritten",
        font_size_pt=18.0,
        underline=True,
    )

    updated, metadata = converter.text_converter.apply_policy(run)

    assert updated.underline is True
    assert updated.font_family == "Handwritten"
    assert "rendering_behavior" not in metadata
    assert metadata["wordart_detection"]["enabled"] is True
    assert metadata["wordart_detection"]["confidence_threshold"] == _build_balanced_decision().wordart.confidence_threshold
    assert metadata["prefer_vector_fallback"] is True
